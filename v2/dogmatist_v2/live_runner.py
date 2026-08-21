from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import importlib
import json
import signal
import threading
from typing import Any, Callable, Iterator

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
    compute: dict[str, Any]
    cycles: tuple[dict[str, Any], ...]


class _RunClockView:
    """Clock facade that turns a user safe-stop request into drain admission stop."""

    def __init__(self, owner: "LiveEvolutionRunner") -> None:
        self.owner = owner

    @property
    def expired(self) -> bool:
        return self.owner._stop_requested or bool(self.owner.clock.expired)

    @property
    def stop_reason(self) -> str | None:
        if self.owner._stop_requested:
            return self.owner._requested_stop_reason or "user_stop"
        if bool(self.owner.clock.expired):
            return "compute_budget_exhausted"
        return None

    @property
    def elapsed_seconds(self) -> float:
        return float(self.owner.clock.elapsed_seconds)

    @property
    def remaining_seconds(self) -> float:
        return float(self.owner.clock.remaining_seconds)

    def snapshot(self) -> dict[str, Any]:
        payload = dict(self.owner.clock.snapshot())
        payload["safe_stop_requested"] = self.owner._stop_requested
        payload["safe_stop_reason"] = self.owner._requested_stop_reason
        return payload

    def __getattr__(self, name: str) -> Any:
        return getattr(self.owner.clock, name)


class LiveEvolutionRunner:
    """Production overlay for active-compute, Strength Lab and safe evaluation.

    The real DarwinRuntime exposes private unlocked cycle methods because its old
    ``evolve()`` holds one writer lock around the whole overnight run. When those
    methods are available, this runner deliberately preserves that same invariant:
    one Evolution writer lock for the entire run, not a gap between cycles.

    A first SIGINT is converted into a *safe-stop request* rather than an immediate
    KeyboardInterrupt. Existing League/Arena colour pairs drain, no new pair is
    admitted, and incomplete evidence cannot replace the champion. A second SIGINT
    raises KeyboardInterrupt as an emergency escape hatch.
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
        handle_sigint: bool = True,
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
        self.handle_sigint = bool(handle_sigint)
        self._stop_requested = False
        self._requested_stop_reason: str | None = None
        self._sigint_count = 0
        self._run_clock = _RunClockView(self)

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

    def request_stop(self, reason: str = "user_stop") -> None:
        if not self._stop_requested:
            self._stop_requested = True
            self._requested_stop_reason = str(reason or "user_stop")

    @contextmanager
    def _signal_context(self, progress: Callable[[str], None]) -> Iterator[None]:
        if (
            not self.handle_sigint
            or threading.current_thread() is not threading.main_thread()
        ):
            yield
            return

        previous = signal.getsignal(signal.SIGINT)

        def handler(_signum: int, _frame: Any) -> None:
            self._sigint_count += 1
            if self._sigint_count >= 2:
                raise KeyboardInterrupt
            self.request_stop("user_stop")
            message = (
                "[dog_matist][stage=safe-stop][detail=SIGINT received; "
                "finish current colour pair(s), then stop]"
            )
            progress(message)
            progress(
                "DOGMATIST_UI " + json.dumps({
                    "phase": "safe_stop_requested",
                    "reason": "user_stop",
                    "compute": self._run_clock.snapshot(),
                }, ensure_ascii=False)
            )

        signal.signal(signal.SIGINT, handler)
        try:
            yield
        finally:
            signal.signal(signal.SIGINT, previous)

    @contextmanager
    def _writer_cycle_context(self) -> Iterator[Callable[[], Any]]:
        """Preserve the live runtime's whole-run single-writer semantics.

        Pure-Python tests/fake runtimes do not ship the live lock module or
        unlocked cycle methods; those transparently fall back to ``evolve_cycle``.
        """

        has_unlocked = all(
            hasattr(self.runtime, name)
            for name in ("_population_evolve_cycle_unlocked", "_evolve_cycle_unlocked")
        )
        root = getattr(self.runtime, "paths", {}).get("root") if hasattr(self.runtime, "paths") else None
        if not has_unlocked or root is None:
            yield self.runtime.evolve_cycle
            return

        try:
            locks_module = importlib.import_module("darwinchess.locks")
            EvolutionLock = locks_module.EvolutionLock
        except Exception:
            yield self.runtime.evolve_cycle
            return

        with EvolutionLock(root):
            if hasattr(self.runtime, "_retire_stale_challengers"):
                self.runtime._retire_stale_challengers()

            def unlocked_cycle() -> Any:
                league_enabled = bool(
                    getattr(self.runtime, "config", {}).get("league", {}).get("enabled", True)
                )
                if league_enabled:
                    return self.runtime._population_evolve_cycle_unlocked()
                return self.runtime._evolve_cycle_unlocked()

            yield unlocked_cycle

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

        with self.clock, self._signal_context(progress), self._writer_cycle_context() as run_cycle:
            while True:
                if cycles is not None and len(completed) >= cycles:
                    stop_reason = "cycles_complete"
                    break
                if self._run_clock.expired:
                    stop_reason = self._run_clock.stop_reason or "compute_budget_exhausted"
                    break

                cycle_number = len(completed) + 1
                before = self._run_clock.snapshot()
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
                    self._run_clock,
                    runtime_module=self.runtime_module,
                ) as league_guard:
                    if self.enable_parallel_league:
                        parallel_context: Any = LiveParallelLeagueOverride(
                            self.runtime,
                            self._run_clock,
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
                        self._run_clock,
                        runtime_module=self.runtime_module,
                        state=arena_state,
                    ) as arena_guard:
                        raw = run_cycle()

                result = dict(raw) if isinstance(raw, dict) else {"result": raw}
                strength_report = getattr(strength_hook, "last_report", None)
                strength_error = getattr(strength_hook, "last_error", None)
                parallel_ui = getattr(parallel_hook, "latest_ui", None)
                result["live_v2"] = {
                    "compute": self._run_clock.snapshot(),
                    "league_drain": league_guard.state.ui_payload(),
                    "arena_drain": arena_guard.state.ui_payload(),
                    "parallel_league": parallel_ui,
                    "strength_lab": strength_report.ui_payload() if strength_report is not None else None,
                    "strength_error": str(strength_error) if strength_error is not None else None,
                }
                completed.append(result)
                progress(json.dumps(result, ensure_ascii=False, indent=2, default=str))

                final_compute = self._run_clock.snapshot()
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

                if league_guard.state.draining or arena_guard.state.draining or self._run_clock.expired:
                    stop_reason = (
                        league_guard.state.reason
                        or arena_guard.state.reason
                        or self._run_clock.stop_reason
                        or "compute_budget_exhausted"
                    )
                    break

        return LiveEvolutionRunReport(
            cycles_completed=len(completed),
            stop_reason=stop_reason,
            compute=self._run_clock.snapshot(),
            cycles=tuple(completed),
        )
