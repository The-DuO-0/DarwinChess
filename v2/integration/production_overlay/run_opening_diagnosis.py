from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state
from dogmatist_v2.opening_diagnosis import (
    diagnose_openings,
    reset_copied_strength_state,
    write_opening_diagnosis,
)

from run_copied_state import _run_with_telemetry, build_plan


def build_diagnosis_plan(
    source_copy: str | Path,
    snapshot_state: str | Path,
    *,
    generation: int,
    mode: str = "normal",
    league_parallel_games: int = 2,
    keep_existing_strength: bool = False,
) -> dict[str, object]:
    snapshot = Path(snapshot_state).expanduser().resolve()
    manifest = load_snapshot_manifest(snapshot)
    champion = manifest.champion_generation
    if champion is None:
        raise RuntimeError("copied snapshot has no Champion generation")
    if int(champion) != int(generation):
        raise ValueError(
            f"opening diagnosis requested Gen{int(generation)}, but this snapshot starts with "
            f"Gen{int(champion)} as Champion. Create a fresh snapshot from the intended live Champion "
            "or pass that Champion generation explicitly."
        )

    plan = build_plan(
        source_copy,
        snapshot,
        mode=mode,
        cycles=1,
        hours=None,
        league_parallel_games=league_parallel_games,
        expire_on_league_start=False,
    )
    plan["opening_diagnosis"] = {
        "generation": int(generation),
        "snapshot_champion_generation": int(champion),
        "fresh_strength_db": not bool(keep_existing_strength),
        "strength_db_name": "strength_v2.sqlite3",
        "teacher_persistence": False,
        "cycles": 1,
        "book_moves_injected": False,
        "novel_openings_allowed": True,
    }
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one isolated copied-state Evolution cycle and produce a generation-specific "
            "opening diagnosis from dog_matist's own early-position evidence."
        )
    )
    parser.add_argument("source_copy", help="copied dog_matist source tree with V2 overlay installed")
    parser.add_argument("snapshot_state", help="fresh copied state path ending in /.darwinchess")
    parser.add_argument("--generation", type=int, default=54, help="starting Champion to diagnose (default: 54)")
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument("--league-parallel", type=int, choices=(2, 3), default=2)
    parser.add_argument(
        "--keep-existing-strength",
        action="store_true",
        help="advanced: keep copied strength_v2.sqlite3 instead of starting a clean diagnosis DB",
    )
    parser.add_argument("--verbose-ui", action="store_true")
    parser.add_argument(
        "--run",
        action="store_true",
        help="execute the copied-state chess cycle; without this flag only print the safety plan",
    )
    args = parser.parse_args(argv)

    try:
        plan = build_diagnosis_plan(
            args.source_copy,
            args.snapshot_state,
            generation=args.generation,
            mode=args.mode,
            league_parallel_games=args.league_parallel,
            keep_existing_strength=bool(args.keep_existing_strength),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"STOP: {exc}")
        return 2

    preflight = validate_copied_state(args.snapshot_state, include_spawn_probe=True)
    preview = {
        "preflight": preflight.as_dict(),
        "plan": plan,
        "will_run": bool(args.run),
        "important": (
            "The snapshot must start with the requested generation as Champion. When --run is used, "
            "only the copied snapshot's strength_v2.sqlite3 is reset by default. The live "
            "~/.darwinchess state is never referenced or modified."
        ),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    if not preflight.ok:
        print("\nSTOP: copied-state preflight failed; diagnosis was not launched.")
        return 2
    if not args.run:
        print("\nDRY RUN ONLY. Add --run after checking the copied source, Champion, and .darwinchess paths above.")
        return 0

    snapshot = Path(args.snapshot_state).expanduser().resolve()
    if not args.keep_existing_strength:
        removed = reset_copied_strength_state(snapshot)
        if removed:
            print("\n[opening-diagnosis] reset copied Strength Lab state:")
            for path in removed:
                print(f"  {path}")
        else:
            print("\n[opening-diagnosis] copied Strength Lab DB was already clean.")

    return_code, log_path, summary_path, telemetry, validation_passed = _run_with_telemetry(
        plan,
        verbose_ui=bool(args.verbose_ui),
    )

    strength_db = snapshot / "strength_v2.sqlite3"
    diagnosis = diagnose_openings(strength_db, generation=int(args.generation))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    diagnosis_path = summary_path.parent / f"opening_diagnosis_gen{int(args.generation)}_{stamp}.json"
    write_opening_diagnosis(diagnosis, diagnosis_path)

    print("\n" + diagnosis.format_text())
    print("\nOpening-diagnosis artifacts:")
    print(f"  run log:    {log_path}")
    print(f"  validation: {summary_path}")
    print(f"  diagnosis:  {diagnosis_path}")
    print(f"  validation: {'PASS' if validation_passed else 'FAIL'}")
    print(f"  evidence:   {'READY' if diagnosis.ready else 'INSUFFICIENT'}")

    if return_code != 0:
        return return_code
    if not validation_passed:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
