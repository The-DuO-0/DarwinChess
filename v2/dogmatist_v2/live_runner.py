from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import json
from typing import Any, Callable

from .live_arena_guard import LiveArenaDrainOverride, LiveArenaDrainState
from .live_compute import HeartbeatComputeClock
from .live_cycle_override import LiveStrengthCycleOverride
from .live_league_guard import LiveLeagueDrainOverride
from .live_parallel_population import LiveParallelLeagueOverride
from .live_runtime_overlay import LiveStrengthCoordinator


@dataclass(frozen=True)
class LiveEvolutionRunReport:
    cycles_completed: int
    stop_reason: str
    compute: dict[str, float | bool]
    cycles: tuple[dict[str, Any], ...]


class LiveEvolutionRunner:
    """Run the supplied DarwinRuntime on active-compute time instead of wall time.

    This is an overlay, not a replacement chess engine. It calls the production
    ``evolve_cycle()`` method so locking/checkpoint/training logic remains owned by
    the current dog_matist package, while narrow contexts add:

    - suspension-aware active compute accounting;
    - optional Strength Lab selfplay->replay integration;
    - real 2-3 process League games with watchdog terminate/kill;
    - League drain after already-started colour pairs;
    - the same pair-boundary stop inside the final held-out Arena.

    Incomplete League/Arena evidence cannot replace the champion.
    """

    def __init__(
        self,
        runtime: Any,
        clock: HeartbeatComputeClock,
        *,
        strength_coordinator: LiveStrengthCoordinator | None = None,
        runtime_module: Any | None = None,
        targeted_examples: int = 64,
        teacher_request_cap: int = 8,
        persist_teacher: bool = False,
        strength_fail_open: bool = True,
        enable_parallel_league: bool = True,
        parallel_league_fail_open: bool = True,
        league_status_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.runtime = runtime
        self.clock = clock
        self.strength_coordinator = strength_coordinator
        self.runtime_module = runtime_module
        self.targeted_examples = int(targeted_examples)
        self.teacher_request_cap = int(teacher_request_cap)
        self.persist_teacher = bool(persist_teacher)
        self.strength_fail_open = bool(strength_fail_open)
        self.enable_parallel_league = bool(enable_parallel_league)
        self.parallel_league_fail_open = bool(parallel_league_fail_open)
        self.league_status_callback = league_status_callback

    @classmethod
    def from_hours(
        cls,
        runtime: Any,
        hours: float,
        **kwargs: Any,
    ) -> "LiveEvolutionRunner":
        if hours < 0:
            raise ValueError("hours must be non-negative")
        clock = HeartbeatComputeClock(float(hours) * 3600.0)
        return cls(runtime, clock, **kwargs)

    def run(
        self,
        *,
        cycles: int | None = None,
        progress: Callable[[str], None] = print,
    ) -> LiveEvolutionRunReport:
        if cycles is not None and cycles < 0:
            raise ValueError("cycles must be non-negative")
        completed: list[dict[str, Any]] = []
        stop_reason = "cycles_complete" if cycles == 0 else "compute_budget_exhausted"

        with self.clock:
            while True:
                if cycles is not None and len(completed) >= cycles:
                    stop_reason = "cycles_complete"
                    break
                if self.clock.expired:
                    stop_reason = "compute_budget_exhausted"
                    break

                cycle_number = len(completed) + 1
                before = self.clock.snapshot()
                progress(
                    f"[dog_matist][stage=cycle][detail={cycle_number} "
                    f"compute={before['elapsed_seconds']:.1f}/{before['budget_seconds']:.1f}s]"
                )
                progress(
                    "DOGMATIST_UI " + json.dumps({
                        "phase": "cycle",
                        "cycle": cycle_number,
                        "compute": before,
                    }, ensure_ascii=False)
                )

                if self.strength_coordinator is None:
                    strength_context: Any = nullcontext()
                else:
                    strength_context = LiveStrengthCycleOverride(
                        self.strength_coordinator,
                        targeted_examples=self.targeted_examples,
                        teacher_request_cap=self.teacher_request_cap,
                        persist_teacher=self.persist_teacher,
                        fail_open=self.strength_fail_open,
                    )

                with strength_context as strength_hook, LiveLeagueDrainOverride(
                    self.runtime,
                    self.clock,
                    runtime_module=self.runtime_module,
                ) as league_guard:
                    if self.enable_parallel_league:
                        parallel_context: Any = LiveParallelLeagueOverride(
                            self.runtime,
                            self.clock,
                            runtime_module=self.runtime_module,
                            state=league_guard.state,
                            fail_open=self.parallel_league_fail_open,
                            status_callback=self.league_status_callback,
                        )
                    else:
                        parallel_context = nullcontext()

                    arena_state = LiveArenaDrainState(linked_state=league_guard.state)
                    with parallel_context as parallel_hook, LiveArenaDrainOverride(
                        self.runtime,
                        self.clock,
                        runtime_module=self.runtime_module,
                        state=arena_state,
                    ) as arena_guard:
                        raw = self.runtime.evolve_cycle()

                result = dict(raw) if isinstance(raw, dict) else {"result": raw}
                strength_report = getattr(strength_hook, "last_report", None)
                strength_error = getattr(strength_hook, "last_error", None)
                parallel_ui = getattr(parallel_hook, "latest_ui", None)
                result["live_v2"] = {
                    "compute": self.clock.snapshot(),
                    "league_drain": league_guard.state.ui_payload(),
                    "arena_drain": arena_guard.state.ui_payload(),
                    "parallel_league": parallel_ui,
                    "strength_lab": strength_report.ui_payload() if strength_report is not None else None,
                    "strength_error": str(strength_error) if strength_error is not None else None,
                }
                completed.append(result)
                progress(json.dumps(result, ensure_ascii=False, indent=2, default=str))

                final_compute = self.clock.snapshot()
                progress(
                    "DOGMATIST_UI " + json.dumps({
                        "phase": "cycle_complete",
                        "cycle": cycle_number,
                        "compute": final_compute,
                        "league_drain": league_guard.state.ui_payload(),
                        "arena_drain": arena_guard.state.ui_payload(),
                        "strength_lab": strength_report.ui_payload() if strength_report is not None else None,
                    }, ensure_ascii=False, default=str)
                )

                if league_guard.state.draining or arena_guard.state.draining or self.clock.expired:
                    stop_reason = league_guard.state.reason or arena_guard.state.reason or "compute_budget_exhausted"
                    break

        return LiveEvolutionRunReport(
            cycles_completed=len(completed),
            stop_reason=stop_reason,
            compute=self.clock.snapshot(),
            cycles=tuple(completed),
        )
