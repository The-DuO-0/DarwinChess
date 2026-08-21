from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
from pathlib import Path
from typing import Any, Callable

from .fixed_reference import (
    FixedReferenceEvaluator,
    FixedReferenceResult,
    FrozenReferenceManager,
    FrozenStrengthReference,
)
from .live_game_watchdog import LiveGameWatchdogPolicy
from .strength_store import StrengthStore


@dataclass(frozen=True)
class LiveFixedReferenceReport:
    reference: FrozenStrengthReference
    result: FixedReferenceResult | None
    subject_generation: int | None
    skipped_reason: str | None = None

    def ui_payload(self) -> dict[str, object]:
        return {
            "reference": self.reference.as_dict(),
            "subject_generation": self.subject_generation,
            "result": self.result.ui_payload() if self.result is not None else None,
            "skipped_reason": self.skipped_reason,
        }


def _walk_values(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_values(child)


def _first_int_for_keys(value: Any, keys: tuple[str, ...]) -> int | None:
    wanted = {key.lower() for key in keys}
    for key, child in _walk_values(value):
        if key.lower() not in wanted:
            continue
        try:
            return int(child)
        except (TypeError, ValueError):
            continue
    return None


def _first_bool_for_keys(value: Any, keys: tuple[str, ...]) -> bool | None:
    wanted = {key.lower() for key in keys}
    for key, child in _walk_values(value):
        if key.lower() not in wanted:
            continue
        if isinstance(child, bool):
            return child
        if isinstance(child, (int, float)):
            return bool(child)
    return None


class LiveFixedReferenceCoordinator:
    """Measure each round's strongest available subject on one frozen ruler."""

    def __init__(
        self,
        runtime: Any,
        store: StrengthStore,
        clock: Any,
        *,
        reference_root: str | Path,
        pair_count: int = 2,
        watchdog_policy: LiveGameWatchdogPolicy | None = None,
        stop_requested: Callable[[], bool] | None = None,
        status_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if pair_count <= 0:
            raise ValueError("pair_count must be positive")
        self.runtime = runtime
        self.store = store
        self.clock = clock
        self.manager = FrozenReferenceManager(reference_root)
        self.pair_count = int(pair_count)
        self.watchdog_policy = watchdog_policy or LiveGameWatchdogPolicy()
        self.stop_requested = stop_requested or (lambda: False)
        self.status_callback = status_callback
        self.reference: FrozenStrengthReference | None = None
        self.last_report: LiveFixedReferenceReport | None = None

    @property
    def memory(self) -> Any:
        return self.runtime.memory

    def checkpoint_for_generation(self, generation: int) -> str:
        row = self.memory.get_generation(int(generation))
        if row is None:
            raise LookupError(f"unknown generation {generation}")
        path = str(row["checkpoint_path"])
        if not path:
            raise RuntimeError(f"generation {generation} has no checkpoint path")
        return path

    def ensure_reference(self) -> FrozenStrengthReference:
        existing = self.manager.load()
        if existing is not None:
            if not self.manager.verify(existing):
                raise RuntimeError("frozen strength reference checksum mismatch")
            self.reference = existing
            return existing

        champion = self.runtime.champion_info()
        generation = int(champion["id"])
        checkpoint = self.checkpoint_for_generation(generation)
        self.reference = self.manager.freeze(
            checkpoint,
            generation=generation,
            created_at=datetime.now(timezone.utc),
        )
        return self.reference

    def _subject_generation(self, raw_result: Any) -> int:
        # League winner is the most useful signal under a long-lived Champion: it
        # can improve for several rounds before finally being strong enough to win
        # the held-out promotion Arena.
        subject = _first_int_for_keys(
            raw_result,
            (
                "top_generation",
                "league_top_generation",
                "best_generation",
                "challenger_generation",
            ),
        )
        if subject is not None:
            return subject
        after = _first_int_for_keys(raw_result, ("champion_after", "champion_generation"))
        if after is not None:
            return after
        return int(self.runtime.champion_info()["id"])

    def _promoted(self, raw_result: Any) -> bool:
        explicit = _first_bool_for_keys(raw_result, ("promoted", "promotion"))
        if explicit is not None:
            return explicit
        before = _first_int_for_keys(raw_result, ("champion_before",))
        after = _first_int_for_keys(raw_result, ("champion_after",))
        return before is not None and after is not None and before != after

    def _openings(self, round_index: int) -> list[tuple[str, str]]:
        runtime_module = importlib.import_module(self.runtime.__class__.__module__)
        population_cls = getattr(runtime_module, "PopulationArena")
        population_module = importlib.import_module(population_cls.__module__)
        curriculum_cls = getattr(population_module, "OpeningCurriculum")
        base_seed = int(self.runtime.config.get("project", {}).get("seed", 0))
        # The frozen-reference opening set must be deterministic for a given round
        # and independent from whoever happens to be Champion.
        curriculum = curriculum_cls(seed=base_seed + 910_009 + int(round_index) * 97)
        rows = curriculum.arena_pairs(self.pair_count)
        return [(board.fen(), str(opening)) for board, opening in rows]

    def evaluate_cycle(self, raw_result: Any, *, round_index: int) -> LiveFixedReferenceReport:
        reference = self.reference or self.ensure_reference()
        if self.stop_requested():
            report = LiveFixedReferenceReport(reference, None, None, "safe_stop_requested")
            self.last_report = report
            return report
        if bool(self.clock.expired):
            report = LiveFixedReferenceReport(reference, None, None, "compute_budget_exhausted_before_reference")
            self.last_report = report
            return report

        subject = self._subject_generation(raw_result)
        subject_checkpoint = self.checkpoint_for_generation(subject)
        openings = self._openings(round_index)
        lcfg = self.runtime.config.get("league", {})
        depth = int(lcfg.get("depth", self.runtime.config.get("arena", {}).get("depth", self.runtime.config["search"]["depth"])))
        max_plies = int(lcfg.get("max_game_plies", self.runtime.config.get("arena", {}).get("max_game_plies", 220)))
        parallel = int(self.runtime.config.get("runtime", {}).get("league_parallel_games", 2) or 2)
        if parallel not in (2, 3):
            parallel = 2

        def emit(snapshot: dict[str, object]) -> None:
            if self.status_callback is not None:
                self.status_callback({"phase": "fixed_reference", "fixed_reference": snapshot})

        evaluator = FixedReferenceEvaluator(
            clock=self.clock,
            parallel_games=parallel,
            hard_game_timeout_seconds=self.watchdog_policy.emergency_game_seconds,
            stall_timeout_seconds=self.watchdog_policy.stall_seconds,
            kill_grace_seconds=self.watchdog_policy.kill_grace_seconds,
            status_callback=emit,
        )
        result = evaluator.evaluate(
            round_index=int(round_index),
            subject_generation=subject,
            subject_checkpoint=subject_checkpoint,
            reference=reference,
            config=self.runtime.config,
            openings=openings,
            depth=depth,
            max_plies=max_plies,
            torch_threads=1,
        )

        champion = int(self.runtime.champion_info()["id"])
        evidence = result.to_round_evidence(
            champion_generation=champion,
            promoted=self._promoted(raw_result),
        )
        mode = self.store.round_history(limit=1)
        # Record the mode the next Strength planning pass will derive from all
        # evidence including this row. This is metadata only; planning always reads
        # the actual round history again.
        from .strength_lab import StrengthLabController
        planned_mode = StrengthLabController().plan((*self.store.round_history(), evidence)).mode
        self.store.record_round(
            evidence,
            mode=planned_mode,
            recorded_at=datetime.now(timezone.utc),
        )
        report = LiveFixedReferenceReport(reference, result, subject, None)
        self.last_report = report
        return report


class LiveFixedReferenceCycleOverride:
    """Attach fixed-reference measurement after each real evolution cycle."""

    METHOD_NAMES = (
        "_population_evolve_cycle_unlocked",
        "_evolve_cycle_unlocked",
        "evolve_cycle",
    )

    def __init__(self, runtime: Any, coordinator: LiveFixedReferenceCoordinator) -> None:
        self.runtime = runtime
        self.coordinator = coordinator
        self._originals: dict[str, Any] = {}
        self._had_instance: dict[str, bool] = {}
        self._previous: dict[str, Any] = {}
        self._round_counter = 0

    def __enter__(self) -> "LiveFixedReferenceCycleOverride":
        attrs = getattr(self.runtime, "__dict__", {})
        for name in self.METHOD_NAMES:
            if not hasattr(self.runtime, name):
                continue
            original = getattr(self.runtime, name)
            self._originals[name] = original
            self._had_instance[name] = name in attrs
            if name in attrs:
                self._previous[name] = attrs[name]

            def make_wrapper(method: Any, method_name: str):
                def wrapped(*args: Any, **kwargs: Any) -> Any:
                    raw = method(*args, **kwargs)
                    # In a live runtime the runner calls one cycle method once. Do
                    # not double-measure if a public wrapper internally delegates to
                    # an already-wrapped private method.
                    marker = None
                    if isinstance(raw, dict):
                        marker = raw.get("_v2_fixed_reference_measured")
                    if not marker:
                        self._round_counter += 1
                        report = self.coordinator.evaluate_cycle(raw, round_index=self._round_counter)
                        if isinstance(raw, dict):
                            raw["_v2_fixed_reference_measured"] = True
                            raw["fixed_reference"] = report.ui_payload()
                    return raw
                wrapped.__name__ = f"v2_fixed_reference_{method_name}"
                return wrapped

            setattr(self.runtime, name, make_wrapper(original, name))
        return self

    def __exit__(self, *_: object) -> None:
        for name, original in self._originals.items():
            if self._had_instance.get(name, False):
                setattr(self.runtime, name, self._previous[name])
            else:
                try:
                    delattr(self.runtime, name)
                except AttributeError:
                    setattr(self.runtime, name, original)
        self._originals.clear()
        self._had_instance.clear()
        self._previous.clear()
