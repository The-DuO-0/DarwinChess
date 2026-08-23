from __future__ import annotations

import argparse
import json
from pathlib import Path

from dogmatist_v2.mac_preflight import validate_copied_state
from dogmatist_v2.state_snapshot import create_validation_snapshot


def resolve_validation_paths(
    source_state: str | Path,
    validation_home: str | Path,
) -> tuple[Path, Path]:
    """Return live state + automatically nested validation `.darwinchess` path.

    The run harness isolates production path resolution by setting HOME to
    `validation_home`, so the copied state must live at exactly
    `validation_home/.darwinchess`. Building that layout here removes an easy
    foot-gun where a user manually chooses a snapshot directory the runtime would
    never resolve.
    """

    source = Path(source_state).expanduser().resolve()
    home = Path(validation_home).expanduser().resolve()
    destination = home / ".darwinchess"
    if home == source or destination == source:
        raise ValueError("validation home/state must differ from live state")
    if home.exists() and any(home.iterdir()):
        raise FileExistsError(
            f"validation_home must be new or empty so isolation is auditable: {home}"
        )
    return source, destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an isolated HOME/.darwinchess snapshot for DogMatist V2 Mac validation. "
            "This never starts training and never mutates the live source state."
        )
    )
    parser.add_argument("source_state", help="live state root, for example ~/.darwinchess")
    parser.add_argument(
        "validation_home",
        help=(
            "new EMPTY directory outside the live state; the snapshot is created "
            "automatically at <validation_home>/.darwinchess"
        ),
    )
    parser.add_argument(
        "--spawn-probe",
        action="store_true",
        help="also verify macOS/Python multiprocessing spawn before any chess run",
    )
    args = parser.parse_args(argv)

    source, destination = resolve_validation_paths(args.source_state, args.validation_home)
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = create_validation_snapshot(source, destination)
    report = validate_copied_state(destination, include_spawn_probe=bool(args.spawn_probe))

    payload = {
        "validation_home": str(destination.parent),
        "snapshot_state": str(destination),
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
