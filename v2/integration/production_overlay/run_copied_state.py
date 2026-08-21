from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from dogmatist_v2.mac_preflight import (
    audit_copied_state_after_run,
    load_snapshot_manifest,
    validate_copied_state,
)
from dogmatist_v2.validation_telemetry import ValidationTelemetry


class ValidationConsoleRenderer:
    """Render compact human progress while raw DOGMATIST_UI stays in the log."""

    def __init__(self, *, interval_seconds: float = 5.0) -> None:
        self.interval_seconds = float(interval_seconds)
        self._last_emit: dict[str, float] = {}
        self._last_signature: dict[str, tuple[object, ...]] = {}

    @staticmethod
    def _fmt_runtime(seconds: object) -> str:
        try:
            value = max(0, int(float(seconds or 0.0)))
        except (TypeError, ValueError):
            value = 0
        return f"{value // 60:02d}:{value % 60:02d}"

    def _due(self, channel: str, signature: tuple[object, ...]) -> bool:
        now = time.monotonic()
        changed = self._last_signature.get(channel) != signature
        due = now - self._last_emit.get(channel, 0.0) >= self.interval_seconds
        if changed or due:
            self._last_signature[channel] = signature
            self._last_emit[channel] = now
            return True
        return False

    def render(self, payload: dict[str, object]) -> str | None:
        phase = str(payload.get("phase") or "")
        if phase == "copy_validation":
            copy = payload.get("copy_validation")
            if isinstance(copy, dict):
                suffix = " · budget-drain probe" if copy.get("expire_on_league_start") else ""
                return (
                    "[validation] isolated copy · teacher OFF · "
                    f"League {copy.get('league_parallel_games', '?')} parallel{suffix}"
                )

        if phase == "validation_budget_expired":
            active = int(payload.get("active_games_at_expiry", 0) or 0)
            return (
                f"[validation][budget] admission budget expired with {active} active League game(s); "
                "they must finish naturally"
            )

        if phase == "league":
            league = payload.get("league")
            if not isinstance(league, dict):
                return None
            active = league.get("active_games")
            active_rows = active if isinstance(active, list) else []
            failed = tuple(league.get("failed_games") or ())
            timed_out = tuple(league.get("timed_out_games") or ())
            played = int(league.get("played", 0) or 0)
            total = int(league.get("total", 0) or 0)
            signature = (len(active_rows), played, failed, timed_out)
            if not self._due("league", signature):
                return None
            games: list[str] = []
            for row in active_rows[:3]:
                if not isinstance(row, dict):
                    continue
                white = str(row.get("white_id") or "?")
                black = str(row.get("black_id") or "?")
                opening = str(row.get("opening") or "?")
                plies = int(row.get("plies", 0) or 0)
                runtime = self._fmt_runtime(row.get("runtime_seconds"))
                games.append(f"G{white}W-G{black}B {opening} ply{plies} {runtime}")
            suffix = " | ".join(games) if games else "waiting for next pair"
            flags = ""
            if failed or timed_out:
                flags = f" · failed={len(failed)} timeout={len(timed_out)}"
            return (
                f"[validation][league] {len(active_rows)} active · {played}/{total} finished"
                f"{flags} · {suffix}"
            )

        if phase.startswith("fixed_reference"):
            fixed = payload.get("fixed_reference")
            if not isinstance(fixed, dict):
                return None
            active = fixed.get("active")
            if not isinstance(active, dict):
                return None
            active_rows = active.get("active_games")
            rows = active_rows if isinstance(active_rows, list) else []
            signature = (
                len(rows),
                tuple(active.get("failed_games") or ()),
                tuple(active.get("timed_out_games") or ()),
            )
            if not self._due("fixed_reference", signature):
                return None
            games: list[str] = []
            for row in rows[:3]:
                if not isinstance(row, dict):
                    continue
                games.append(
                    f"{row.get('white_id', '?')}W-{row.get('black_id', '?')}B "
                    f"ply{int(row.get('plies', 0) or 0)} {self._fmt_runtime(row.get('runtime_seconds'))}"
                )
            return "[validation][reference] " + (" | ".join(games) if games else "pair complete")

        return None


def build_plan(
    source_copy: str | Path,
    snapshot_state: str | Path,
    *,
    mode: str,
    cycles: int | None,
    hours: float | None,
    league_parallel_games: int = 2,
    expire_on_league_start: bool = False,
) -> dict[str, object]:
    source = Path(source_copy).expanduser().resolve()
    snapshot = Path(snapshot_state).expanduser().resolve()
    if snapshot.name != ".darwinchess":
        raise ValueError(
            "snapshot_state must be a .darwinchess directory; its parent becomes an isolated HOME"
        )
    if not (source / "pyproject.toml").is_file():
        raise FileNotFoundError(f"source copy does not look like dog_matist: {source}")
    executable = source / ".venv" / "bin" / "darwinchess"
    if not executable.is_file():
        raise FileNotFoundError(
            f"copied source venv entrypoint not found: {executable}; install the source COPY first"
        )
    if cycles is not None and hours is not None:
        raise ValueError("cycles and hours are mutually exclusive")
    if cycles is None and hours is None:
        cycles = 1
    if cycles is not None and cycles <= 0:
        raise ValueError("cycles must be positive")
    if hours is not None and hours <= 0:
        raise ValueError("hours must be positive")
    if int(league_parallel_games) not in (2, 3):
        raise ValueError("league_parallel_games must be 2 or 3")

    manifest = load_snapshot_manifest(snapshot)
    validation_home = snapshot.parent
    live_source = Path(manifest.source_root).expanduser().resolve()
    if snapshot == live_source:
        raise RuntimeError("refusing to run against the live state root")

    command = [str(executable), "--mode", mode, "evolve"]
    if hours is not None:
        command += ["--hours", str(float(hours))]
    else:
        command += ["--cycles", str(int(cycles or 1))]

    environment = {
        "HOME": str(validation_home),
        "XDG_CONFIG_HOME": str(validation_home / ".config"),
        "XDG_CACHE_HOME": str(validation_home / ".cache"),
        "PYTHONNOUSERSITE": "1",
        "DOGMATIST_V2_COPY_VALIDATION": "1",
        "DOGMATIST_V2_COPY_LEAGUE_PARALLEL": str(int(league_parallel_games)),
    }
    if expire_on_league_start:
        environment["DOGMATIST_V2_COPY_EXPIRE_ON_LEAGUE_START"] = "1"

    return {
        "source_copy": str(source),
        "snapshot_state": str(snapshot),
        "validation_home": str(validation_home),
        "live_source_state": str(live_source),
        "command": command,
        "environment": environment,
        "safety": {
            "teacher_persistence_forced_off": True,
            "league_parallel_games": int(league_parallel_games),
            "live_state_must_not_be_referenced": True,
            "run_budget_interrupts_healthy_games": False,
            "expire_on_league_start": bool(expire_on_league_start),
        },
    }


def _validation_invariants(
    telemetry: ValidationTelemetry,
    *,
    expected_parallel_games: int,
    expect_budget_probe: bool,
) -> dict[str, bool]:
    copy = telemetry.copy_validation or {}
    watchdog = telemetry.watchdog or {}
    invariants = {
        "copy_validation_event_seen": bool(copy.get("enabled")),
        "teacher_persistence_off": copy.get("teacher_persistence") is False,
        "copy_parallelism_matches_plan": int(copy.get("league_parallel_games", 0) or 0) == int(expected_parallel_games),
        "parallelism_does_not_exceed_plan": telemetry.max_parallel_games <= int(expected_parallel_games),
        "run_budget_does_not_interrupt_games": watchdog.get("budget_interrupts_games") is False,
        "no_watchdog_trip": not telemetry.timed_out_games,
    }
    if expect_budget_probe:
        invariants["budget_probe_event_seen"] = telemetry.phases.get("validation_budget_expired", 0) >= 1
        invariants["budget_probe_finished_without_worker_failure"] = not telemetry.failed_games
        invariants["budget_probe_final_clock_expired"] = bool((telemetry.final_compute or {}).get("expired"))
    return invariants


def _run_with_telemetry(
    plan: dict[str, object],
    *,
    verbose_ui: bool = False,
) -> tuple[int, Path, Path, ValidationTelemetry, bool]:
    validation_home = Path(str(plan["validation_home"]))
    report_dir = validation_home / "dogmatist_v2_validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = report_dir / f"validation_{stamp}.log"
    summary_path = report_dir / f"validation_{stamp}.json"

    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in plan["environment"].items()})
    source = Path(str(plan["source_copy"]))
    command = [str(x) for x in plan["command"]]
    telemetry = ValidationTelemetry()
    renderer = ValidationConsoleRenderer()

    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=source,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            stripped = line.rstrip("\n")
            is_ui = telemetry.feed_line(stripped)
            if not is_ui or verbose_ui:
                print(line, end="")
                continue
            try:
                payload = json.loads(stripped[len("DOGMATIST_UI "):])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(payload, dict):
                compact = renderer.render(payload)
                if compact:
                    print(compact, flush=True)
        return_code = int(process.wait())

    postflight = audit_copied_state_after_run(
        plan["snapshot_state"],
        expect_teacher_persistence=False,
        require_frozen_reference=True,
    )
    safety = plan.get("safety", {})
    expected_parallel = int(safety.get("league_parallel_games", 2)) if isinstance(safety, dict) else 2
    expect_budget_probe = bool(safety.get("expire_on_league_start", False)) if isinstance(safety, dict) else False
    invariants = _validation_invariants(
        telemetry,
        expected_parallel_games=expected_parallel,
        expect_budget_probe=expect_budget_probe,
    )
    passed = return_code == 0 and postflight.ok and all(invariants.values())
    summary = {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "return_code": return_code,
        "plan": plan,
        "telemetry": telemetry.as_dict(),
        "runtime_invariants": invariants,
        "postflight": postflight.as_dict(),
        "pass": passed,
        "note": (
            "A watchdog timeout is a validation failure to investigate; reaching the run budget while "
            "healthy games continue normally is explicitly not a failure. Teacher replay must remain "
            "absent and all checkpoint/reference paths must remain inside the copied state. Raw "
            "DOGMATIST_UI events remain in the validation log even when the console uses compact output."
        ),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return return_code, log_path, summary_path, telemetry, passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run DogMatist V2 against a copied .darwinchess state under an isolated HOME. "
            "Default behavior is dry-run; --run is required to execute chess work."
        )
    )
    parser.add_argument("source_copy", help="copied dog_matist source tree with overlay installed")
    parser.add_argument("snapshot_state", help="copied state path ending in /.darwinchess")
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument(
        "--league-parallel",
        type=int,
        choices=(2, 3),
        default=2,
        help="copied-state League worker count; 2 is conservative, 3 is an explicit stress test",
    )
    parser.add_argument(
        "--expire-on-league-start",
        action="store_true",
        help=(
            "copied-state safety probe: force the admission budget to expire only after real League "
            "workers are already active; active games must finish naturally"
        ),
    )
    limit = parser.add_mutually_exclusive_group()
    limit.add_argument("--cycles", type=int, default=1)
    limit.add_argument("--hours", type=float)
    parser.add_argument(
        "--verbose-ui",
        action="store_true",
        help="print raw DOGMATIST_UI JSON to the terminal; it is always preserved in the log",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="actually launch the copied-state Evolution run; without this flag only print safety checks",
    )
    args = parser.parse_args(argv)

    cycles = None if args.hours is not None else args.cycles
    plan = build_plan(
        args.source_copy,
        args.snapshot_state,
        mode=args.mode,
        cycles=cycles,
        hours=args.hours,
        league_parallel_games=args.league_parallel,
        expire_on_league_start=bool(args.expire_on_league_start),
    )
    preflight = validate_copied_state(args.snapshot_state, include_spawn_probe=True)
    payload = {"preflight": preflight.as_dict(), "plan": plan, "will_run": bool(args.run)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not preflight.ok:
        print("\nSTOP: copied-state preflight failed; Evolution was not launched.")
        return 2
    if not args.run:
        print("\nDRY RUN ONLY. Add --run only after reviewing the isolated HOME and checkpoint paths above.")
        return 0

    return_code, log_path, summary_path, telemetry, passed = _run_with_telemetry(
        plan,
        verbose_ui=bool(args.verbose_ui),
    )
    print("\nCopied-state validation artifacts:")
    print(f"  log:     {log_path}")
    print(f"  summary: {summary_path}")
    if telemetry.timed_out_games:
        print(f"  WATCHDOG TRIPS: {sorted(telemetry.timed_out_games)}")
    print(f"  validation: {'PASS' if passed else 'FAIL'}")
    return return_code if return_code != 0 else (0 if passed else 3)


if __name__ == "__main__":
    raise SystemExit(main())
