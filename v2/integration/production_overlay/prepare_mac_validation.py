from __future__ import annotations

import argparse
import json
from pathlib import Path

from dogmatist_v2.mac_preflight import validate_copied_state
from dogmatist_v2.state_snapshot import create_validation_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an isolated SQLite/checkpoint snapshot for DogMatist V2 Mac validation. "
            "This never starts training and never mutates the live source state."
        )
    )
    parser.add_argument("source_state", help="live state root, for example ~/.darwinchess")
    parser.add_argument("snapshot_state", help="new EMPTY directory outside the live state root")
    parser.add_argument(
        "--spawn-probe",
        action="store_true",
        help="also verify macOS/Python multiprocessing spawn before any chess run",
    )
    args = parser.parse_args(argv)

    source = Path(args.source_state).expanduser().resolve()
    destination = Path(args.snapshot_state).expanduser().resolve()
    manifest = create_validation_snapshot(source, destination)
    report = validate_copied_state(destination, include_spawn_probe=bool(args.spawn_probe))

    payload = {
        "snapshot": manifest.as_dict(),
        "preflight": report.as_dict(),
        "next_step": (
            "safe to overlay/test the SOURCE COPY against this SNAPSHOT COPY"
            if report.ok
            else "STOP: fix failed preflight checks before running Evolution"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
