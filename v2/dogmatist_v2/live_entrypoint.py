from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .live_compute import HeartbeatComputeClock
from .live_runner import LiveEvolutionRunReport, LiveEvolutionRunner
from .live_runtime_overlay import LiveStrengthCoordinator
from .strength_store import StrengthStore


@dataclass(frozen=True)
class LiveEvolutionOptions:
    """Small production-facing option set for the V2 live overlay."""

    targeted_examples: int = 64
    teacher_request_cap: int = 8
    persist_teacher: bool = False
    enable_parallel_league: bool = True
    strength_fail_open: bool = True
    parallel_league_fail_open: bool = True
    handle_sigint: bool = True
    strength_db_name: str = "strength_v2.sqlite3"

    def __post_init__(self) -> None:
        if self.targeted_examples <= 0:
            raise ValueError("targeted_examples must be positive")
        if self.teacher_request_cap < 0:
            raise ValueError("teacher_request_cap must be non-negative")
        if not self.strength_db_name.strip():
            raise ValueError("strength_db_name must be non-empty")


def _cycle_only_clock(cycles: int) -> HeartbeatComputeClock:
    """Non-binding safety clock for explicit cycle-count runs.

    `run_normal.command` uses one explicit cycle and does not ask for a time limit.
    We still want heartbeat/safe-stop telemetry, so use a deliberately enormous
    budget (one year per requested cycle, minimum one year). The cycle counter is
    the actual stop condition.
    """

    years = max(1, int(cycles))
    return HeartbeatComputeClock(float(years) * 366.0 * 24.0 * 3600.0)


def run_live_evolution(
    runtime: Any,
    *,
    hours: float | None = None,
    cycles: int | None = None,
    options: LiveEvolutionOptions | None = None,
    progress: Callable[[str], None] = print,
    league_status_callback: Callable[[dict[str, object]], None] | None = None,
) -> LiveEvolutionRunReport:
    """Run the real DarwinRuntime through the tested V2 production overlay.

    The Strength Lab uses its own small SQLite database under the runtime state
    root. It does **not** migrate or alter the existing production schema. The
    current production replay/checkpoint database remains owned by MemoryStore.

    `persist_teacher` deliberately defaults to False until copied-state Mac
    validation has passed. Hard-position capture and recipe planning can therefore
    be exercised first without inserting new teacher replay rows.
    """

    if hours is not None and cycles is not None:
        raise ValueError("hours and cycles are mutually exclusive")
    if hours is not None and hours < 0:
        raise ValueError("hours must be non-negative")
    if cycles is not None and cycles < 0:
        raise ValueError("cycles must be non-negative")
    if hours is None and cycles is None:
        cycles = 1

    opts = options or LiveEvolutionOptions()
    paths = getattr(runtime, "paths", None)
    if not isinstance(paths, dict) or "root" not in paths:
        raise ValueError("runtime must expose paths['root'] for Strength Lab state")
    strength_path = Path(paths["root"]) / opts.strength_db_name

    if hours is not None:
        clock = HeartbeatComputeClock(float(hours) * 3600.0)
    else:
        clock = _cycle_only_clock(int(cycles or 1))

    with StrengthStore(strength_path) as store:
        coordinator = LiveStrengthCoordinator(runtime, store)
        runner = LiveEvolutionRunner(
            runtime,
            clock,
            strength_coordinator=coordinator,
            targeted_examples=opts.targeted_examples,
            teacher_request_cap=opts.teacher_request_cap,
            persist_teacher=opts.persist_teacher,
            strength_fail_open=opts.strength_fail_open,
            enable_parallel_league=opts.enable_parallel_league,
            parallel_league_fail_open=opts.parallel_league_fail_open,
            league_status_callback=league_status_callback,
            handle_sigint=opts.handle_sigint,
        )
        report = runner.run(cycles=cycles, progress=progress)

    progress(
        "[dog_matist][v2-live] "
        f"cycles={report.cycles_completed} stop={report.stop_reason} "
        f"compute={float(report.compute.get('elapsed_seconds', 0.0)):.1f}s"
    )
    return report
