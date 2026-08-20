from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Callable, Iterable

from .strength_pipeline import DeepSearchTeacherRequest
from .strength_store import HardPositionEvidence, StrengthStore


@dataclass(frozen=True)
class CapturedHardPosition:
    evidence: HardPositionEvidence
    priority: float
    ply_index: int


@dataclass(frozen=True)
class TeacherSearchBudget:
    max_depth: int
    time_limit_s: float


@dataclass(frozen=True)
class TeacherReplayTarget:
    fen: str
    move_uci: str
    value_target: float
    policy_weight: float
    priority: float
    teacher_score_cp: float
    baseline_score_cp: float
    teacher_depth: int
    teacher_nodes: int
    teacher_elapsed_s: float


def cp_to_value(score_cp: float, *, cp_scale: float = 650.0) -> float:
    if cp_scale <= 0:
        raise ValueError("cp_scale must be positive")
    return math.tanh(float(score_cp) / cp_scale)


class LiveGameEvidenceBridge:
    """Convert the current dog_matist GameRecord into compact StrengthStore evidence.

    The production self-play code already stores FEN, final value target, played
    search score and best-search score in every replay example.  That is enough
    to mine useful hard positions without changing the live GameRecord schema.
    """

    def __init__(
        self,
        store: StrengthStore,
        *,
        cp_scale: float = 650.0,
        skip_opening_plies: int = 6,
        max_positions_per_game: int = 12,
        minimum_priority: float = 0.24,
    ) -> None:
        if cp_scale <= 0:
            raise ValueError("cp_scale must be positive")
        if skip_opening_plies < 0:
            raise ValueError("skip_opening_plies must be non-negative")
        if max_positions_per_game <= 0:
            raise ValueError("max_positions_per_game must be positive")
        self.store = store
        self.cp_scale = cp_scale
        self.skip_opening_plies = skip_opening_plies
        self.max_positions_per_game = max_positions_per_game
        self.minimum_priority = minimum_priority

    def candidates_from_record(
        self,
        record: Any,
        *,
        generation: int,
        round_index: int,
        source_kind: str = "selfplay",
    ) -> tuple[CapturedHardPosition, ...]:
        metadata = getattr(record, "metadata", {}) or {}
        opening = str(metadata.get("opening_name") or metadata.get("opening_family") or "unknown")
        rows: list[CapturedHardPosition] = []
        examples = list(getattr(record, "examples", ()) or ())
        for ply_index, example in enumerate(examples):
            if ply_index < self.skip_opening_plies:
                continue
            search_score = getattr(example, "search_score_cp", None)
            best_score = getattr(example, "best_score_cp", None)
            if search_score is None:
                continue
            value_target = float(getattr(example, "value_target", 0.0))
            predicted = cp_to_value(float(search_score), cp_scale=self.cp_scale)
            value_error = min(1.0, abs(predicted - value_target) / 2.0)
            severity = max(0.0, -value_target)
            if best_score is None:
                policy_surprise = 0.0
            else:
                policy_surprise = min(1.0, max(0.0, float(best_score) - float(search_score)) / 300.0)
            evidence = HardPositionEvidence(
                fen=str(getattr(example, "fen")),
                opening_bucket=opening,
                source_generation=generation,
                source_kind=source_kind,
                severity=severity,
                uncertainty=policy_surprise,
                value_error=value_error,
                round_index=round_index,
            )
            rows.append(CapturedHardPosition(evidence, evidence.priority, ply_index))
        rows.sort(key=lambda item: (item.priority, -item.ply_index), reverse=True)
        return tuple(row for row in rows if row.priority >= self.minimum_priority)[: self.max_positions_per_game]

    def persist_record(
        self,
        record: Any,
        *,
        generation: int,
        round_index: int,
        observed_at: Any,
        source_kind: str = "selfplay",
        max_per_bucket: int = 128,
    ) -> int:
        rows = self.candidates_from_record(
            record,
            generation=generation,
            round_index=round_index,
            source_kind=source_kind,
        )
        for row in rows:
            self.store.upsert_hard_position(
                row.evidence,
                observed_at=observed_at,
                max_per_bucket=max_per_bucket,
            )
        return len(rows)


class AlphaBetaTeacherAdapter:
    """Bounded deep-search self-teaching for the live iterative alpha-beta searcher.

    `search_multiplier` must not be interpreted as multiplying alpha-beta depth:
    depth grows exponentially.  Instead we allow at least one extra iterative-
    deepening ply while a wall-clock cap scales from the measured baseline search.
    """

    def __init__(
        self,
        *,
        cp_scale: float = 650.0,
        minimum_teacher_time_s: float = 0.03,
        maximum_teacher_time_s: float = 2.0,
    ) -> None:
        if cp_scale <= 0:
            raise ValueError("cp_scale must be positive")
        if minimum_teacher_time_s <= 0 or maximum_teacher_time_s < minimum_teacher_time_s:
            raise ValueError("invalid teacher time bounds")
        self.cp_scale = cp_scale
        self.minimum_teacher_time_s = minimum_teacher_time_s
        self.maximum_teacher_time_s = maximum_teacher_time_s

    def budget_for(
        self,
        request: DeepSearchTeacherRequest,
        *,
        base_depth: int,
        baseline_elapsed_s: float,
    ) -> TeacherSearchBudget:
        if base_depth <= 0:
            raise ValueError("base_depth must be positive")
        multiplier = max(1.0, float(request.search_multiplier))
        extra_depth = 1 if multiplier <= 3.0 else 2
        measured = max(self.minimum_teacher_time_s, float(baseline_elapsed_s))
        time_limit = min(self.maximum_teacher_time_s, measured * multiplier)
        time_limit = max(self.minimum_teacher_time_s, time_limit)
        return TeacherSearchBudget(base_depth + extra_depth, time_limit)

    def execute(
        self,
        request: DeepSearchTeacherRequest,
        *,
        searcher: Any,
        board_factory: Callable[[str], Any],
        base_depth: int,
        top_n: int = 5,
    ) -> TeacherReplayTarget | None:
        board = board_factory(request.fen)
        baseline = searcher.search(board, depth=base_depth, top_n=top_n)
        budget = self.budget_for(
            request,
            base_depth=base_depth,
            baseline_elapsed_s=float(getattr(baseline, "elapsed_s", 0.0)),
        )
        teacher = searcher.search(
            board,
            depth=budget.max_depth,
            time_limit_s=budget.time_limit_s,
            top_n=top_n,
        )
        move = getattr(teacher, "move", None)
        if move is None:
            return None
        move_uci = move.uci() if hasattr(move, "uci") else str(move)
        teacher_score = float(getattr(teacher, "score_cp", 0.0))
        baseline_score = float(getattr(baseline, "score_cp", 0.0))
        disagreement = abs(teacher_score - baseline_score)
        return TeacherReplayTarget(
            fen=request.fen,
            move_uci=move_uci,
            value_target=cp_to_value(teacher_score, cp_scale=self.cp_scale),
            policy_weight=1.25,
            priority=1.0 + min(2.0, disagreement / 250.0),
            teacher_score_cp=teacher_score,
            baseline_score_cp=baseline_score,
            teacher_depth=int(getattr(teacher, "depth", 0)),
            teacher_nodes=int(getattr(teacher, "nodes", 0)),
            teacher_elapsed_s=float(getattr(teacher, "elapsed_s", 0.0)),
        )
