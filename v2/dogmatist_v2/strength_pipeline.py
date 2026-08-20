from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .strength_lab import StrengthLabPlan, TrainingBatchBudget
from .strength_store import HardPositionEvidence, StrengthStore


@dataclass(frozen=True)
class DeepSearchTeacherRequest:
    position_key: str
    fen: str
    opening_bucket: str
    search_multiplier: float
    source_generation: int | None


@dataclass(frozen=True)
class StrengthRoundRecipe:
    requested: TrainingBatchBudget
    natural_selfplay_examples: int
    hard_positions: tuple[HardPositionEvidence, ...]
    specialist_examples: int
    teacher_requests: tuple[DeepSearchTeacherRequest, ...]
    backfilled_examples: int

    @property
    def effective_total(self) -> int:
        return (
            self.natural_selfplay_examples
            + len(self.hard_positions)
            + self.specialist_examples
            + len(self.teacher_requests)
        )

    def ui_payload(self) -> dict[str, object]:
        return {
            "requested": self.requested.as_dict(),
            "effective": {
                "natural_selfplay": self.natural_selfplay_examples,
                "hard_positions": len(self.hard_positions),
                "specialist_sparring": self.specialist_examples,
                "deep_search_teacher": len(self.teacher_requests),
                "total": self.effective_total,
            },
            "backfilled_examples": self.backfilled_examples,
            "teacher_search_multiplier": (
                self.teacher_requests[0].search_multiplier if self.teacher_requests else None
            ),
        }


class StrengthPipelinePlanner:
    """Turn the Strength Lab policy into work the production trainer can execute.

    The planner never invents hard positions or specialists. Missing targeted
    material is conservatively backfilled with ordinary self-play so a sparse
    evidence pool cannot stall the overnight run.
    """

    def __init__(self, store: StrengthStore) -> None:
        self.store = store

    def build_recipe(
        self,
        plan: StrengthLabPlan,
        *,
        total_examples: int,
        available_specialist_examples: int = 0,
        hard_position_bucket_cap: int = 8,
    ) -> StrengthRoundRecipe:
        if available_specialist_examples < 0:
            raise ValueError("available_specialist_examples must be non-negative")
        requested = plan.batch_budget(total_examples)

        hard_pool = self.store.sample_hard_positions(
            requested.hard_positions + requested.deep_search_teacher,
            per_bucket_cap=hard_position_bucket_cap,
        )
        hard_rows = hard_pool[: requested.hard_positions]

        remaining_for_teacher = hard_pool[requested.hard_positions :]
        teacher_rows = remaining_for_teacher[: requested.deep_search_teacher]
        teacher_requests = tuple(
            DeepSearchTeacherRequest(
                position_key=row.position_key,
                fen=row.fen,
                opening_bucket=row.opening_bucket,
                search_multiplier=plan.teacher_search_multiplier,
                source_generation=row.source_generation,
            )
            for row in teacher_rows
        )

        specialist_examples = min(requested.specialist_sparring, available_specialist_examples)
        missing_hard = requested.hard_positions - len(hard_rows)
        missing_teacher = requested.deep_search_teacher - len(teacher_requests)
        missing_specialist = requested.specialist_sparring - specialist_examples
        backfill = missing_hard + missing_teacher + missing_specialist

        natural = requested.natural_selfplay + backfill
        recipe = StrengthRoundRecipe(
            requested=requested,
            natural_selfplay_examples=natural,
            hard_positions=tuple(hard_rows),
            specialist_examples=specialist_examples,
            teacher_requests=teacher_requests,
            backfilled_examples=backfill,
        )
        if recipe.effective_total != total_examples:
            raise AssertionError("Strength Lab recipe must preserve the requested total")
        return recipe


@dataclass(frozen=True)
class EngineABTrialPlan:
    """Paired engine-revision experiment on frozen model weights."""

    baseline_revision_id: str
    candidate_revision_id: str
    frozen_checkpoint: str
    start_fens: tuple[str, ...]

    @property
    def paired_games(self) -> int:
        return len(self.start_fens) * 2

    def __post_init__(self) -> None:
        if not self.baseline_revision_id or not self.candidate_revision_id:
            raise ValueError("engine revision ids must be non-empty")
        if self.baseline_revision_id == self.candidate_revision_id:
            raise ValueError("candidate engine revision must differ from baseline")
        if not self.frozen_checkpoint:
            raise ValueError("A/B engine trials require a frozen model checkpoint")
        if not self.start_fens:
            raise ValueError("A/B engine trials require paired start positions")

    def game_specs(self) -> tuple[dict[str, str], ...]:
        games: list[dict[str, str]] = []
        for index, fen in enumerate(self.start_fens):
            pair_id = f"engine-ab-{index}"
            games.append(
                {
                    "pair_id": pair_id,
                    "fen": fen,
                    "white_revision": self.candidate_revision_id,
                    "black_revision": self.baseline_revision_id,
                    "checkpoint": self.frozen_checkpoint,
                }
            )
            games.append(
                {
                    "pair_id": pair_id,
                    "fen": fen,
                    "white_revision": self.baseline_revision_id,
                    "black_revision": self.candidate_revision_id,
                    "checkpoint": self.frozen_checkpoint,
                }
            )
        return tuple(games)
