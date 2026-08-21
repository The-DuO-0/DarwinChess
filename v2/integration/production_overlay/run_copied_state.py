from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state
from dogmatist_v2.validation_telemetry import ValidationTelemetry


def build_plan(
    source_copy: str | Path,
    snapshot_state: str | Path,
    *,
    mode: str,
    cycles: int | None,
    hours: float | None,
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

    return {
        "source_copy": str(source),
        "snapshot_state": str(snapshot),
        "validation_home": str(validation_home),
        "live_source_state": str(live_source),
        "command": command,
        "environment": {
            "HOME": str(validation_home),
            "XDG_CONFIG_HOME": str(validation_home / ".config"),
            "XDG_CACHE_HOME": str(validation_home / ".cache"),
            "PYTHONNOUSERSITE": "1",
            "DOGMATIST_V2_COPY_VALIDATION": "1",
        },
        "safety": {
            "teacher_persistence_forced_off": True,
            "initial_league_parallel_games_forced": 2,
            "live_state_must_not_be_referenced": True,
            "run_budget_interrupts_healthy_games": False,
        },
    }


def _run_with_telemetry(plan: dict[str, object]) -> tuple[int, Path, Path, ValidationTelemetry]:
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
            print(line, end="")
            log.write(line)
            log.flush()
            telemetry.feed_line(line.rstrip("\n"))
        return_code = int(process.wait())

    postflight = validate_copied_state(plan["snapshot_state"], include_spawn_probe=False)
    summary = {
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "return_code": return_code,
        "plan": plan,
        "telemetry": telemetry.as_dict(),
        "postflight": postflight.as_dict(),
        "pass": return_code == 0 and postflight.ok and not telemetry.timed_out_games,
        "note": (
            "A watchdog timeout is treated as a validation failure to investigate; "
            "reaching the run budget while games continue normally is not a failure."
        ),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return return_code, log_path, summary_path, telemetry


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
    limit = parser.add_mutually_exclusive_group()
    limit.add_argument("--cycles", type=int, default=1)
    limit.add_argument("--hours", type=float)
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

    return_code, log_path, summary_path, telemetry = _run_with_telemetry(plan)
    print("\nCopied-state validation artifacts:")
    print(f"  log:     {log_path}")
    print(f"  summary: {summary_path}")
    if telemetry.timed_out_games:
        print(f"  WATCHDOG TRIPS: {sorted(telemetry.timed_out_games)}")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
