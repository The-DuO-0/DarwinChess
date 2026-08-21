from __future__ import annotations

from dataclasses import dataclass
import json
import multiprocessing as mp
from pathlib import Path
import sqlite3
from typing import Any

from .fixed_reference import FrozenReferenceManager
from .state_snapshot import (
    SnapshotCheckpoint,
    StateSnapshotManifest,
    validate_snapshot_isolation,
)


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class MacPreflightReport:
    snapshot_root: str
    checks: tuple[PreflightCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "snapshot_root": self.snapshot_root,
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
        }


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _integrity(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"missing SQLite database: {path}"
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        value = str(row[0]) if row else "missing result"
        return value.lower() == "ok", value
    finally:
        conn.close()


def load_snapshot_manifest(snapshot_root: str | Path) -> StateSnapshotManifest:
    root = Path(snapshot_root).expanduser().resolve()
    path = root / "SNAPSHOT_MANIFEST.json"
    if not path.is_file():
        raise FileNotFoundError(f"snapshot manifest not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    checkpoints = tuple(
        SnapshotCheckpoint(
            generation=int(row["generation"]),
            source=str(row["source"]),
            copied=str(row["copied"]),
            bytes=int(row["bytes"]),
            sha256=str(row["sha256"]),
        )
        for row in raw.get("checkpoints", [])
    )
    return StateSnapshotManifest(
        created_at=str(raw["created_at"]),
        source_root=str(raw["source_root"]),
        snapshot_root=str(raw["snapshot_root"]),
        database=str(raw["database"]),
        champion_generation=(
            int(raw["champion_generation"])
            if raw.get("champion_generation") is not None
            else None
        ),
        checkpoints=checkpoints,
        strength_store_copied=bool(raw.get("strength_store_copied", False)),
    )


def _spawn_probe_child(queue: Any) -> None:
    queue.put({"ok": True, "pid": mp.current_process().pid})


def run_spawn_probe(*, timeout_seconds: float = 10.0) -> PreflightCheck:
    """Verify the exact multiprocessing mode used by League on macOS can start."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(
        target=_spawn_probe_child,
        args=(queue,),
        name="dogmatist-v2-spawn-preflight",
        daemon=False,
    )
    try:
        process.start()
        process.join(timeout=timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
            return PreflightCheck("spawn_process", False, "spawn child did not exit before timeout")
        if process.exitcode != 0:
            return PreflightCheck("spawn_process", False, f"spawn child exit code {process.exitcode}")
        try:
            payload = queue.get(timeout=1.0)
        except Exception as exc:
            return PreflightCheck("spawn_process", False, f"spawn child returned no payload: {exc}")
        if not isinstance(payload, dict) or not payload.get("ok"):
            return PreflightCheck("spawn_process", False, f"unexpected child payload: {payload!r}")
        return PreflightCheck("spawn_process", True, f"spawn child pid={payload.get('pid')}")
    finally:
        try:
            queue.close()
            queue.join_thread()
        except Exception:
            pass


def validate_copied_state(
    snapshot_root: str | Path,
    *,
    db_name: str = "darwinchess.sqlite3",
    strength_db_name: str = "strength_v2.sqlite3",
    frozen_reference_dir_name: str = "frozen_strength_reference",
    include_spawn_probe: bool = False,
) -> MacPreflightReport:
    """Read-only preflight for the copied-state real-Mac validation gate.

    This function does not run training, mutate the copied database, create the
    reference directory, or touch the live source state. It verifies isolation and
    consistency before a single Evolution cycle is allowed to start.
    """

    root = Path(snapshot_root).expanduser().resolve()
    checks: list[PreflightCheck] = []

    try:
        manifest = load_snapshot_manifest(root)
        checks.append(PreflightCheck("snapshot_manifest", True, manifest.created_at))
    except Exception as exc:
        return MacPreflightReport(
            str(root),
            (PreflightCheck("snapshot_manifest", False, f"{type(exc).__name__}: {exc}"),),
        )

    try:
        validate_snapshot_isolation(manifest)
        checks.append(PreflightCheck("live_state_isolation", True, "no generation checkpoint resolves into live state"))
    except Exception as exc:
        checks.append(PreflightCheck("live_state_isolation", False, f"{type(exc).__name__}: {exc}"))

    if Path(manifest.snapshot_root).resolve() != root:
        checks.append(
            PreflightCheck(
                "manifest_root_match",
                False,
                f"manifest points to {manifest.snapshot_root}, requested {root}",
            )
        )
    else:
        checks.append(PreflightCheck("manifest_root_match", True, str(root)))

    main_db = root / db_name
    ok, detail = _integrity(main_db)
    checks.append(PreflightCheck("main_sqlite_integrity", ok, detail))

    champion_detail = "no champion row"
    champion_ok = False
    if main_db.is_file():
        conn = sqlite3.connect(f"file:{main_db.resolve()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT id, checkpoint_path FROM generations WHERE status='champion' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                generation = int(row[0])
                checkpoint = Path(str(row[1])).expanduser().resolve()
                champion_ok = checkpoint.is_file() and _inside(checkpoint, root)
                champion_detail = f"Gen{generation} -> {checkpoint}"
        except Exception as exc:
            champion_detail = f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()
    checks.append(PreflightCheck("copied_champion_checkpoint", champion_ok, champion_detail))

    missing = [row for row in manifest.checkpoints if not Path(row.copied).is_file()]
    escaped = [row for row in manifest.checkpoints if not _inside(Path(row.copied), root)]
    checkpoints_ok = not missing and not escaped and bool(manifest.checkpoints)
    checks.append(
        PreflightCheck(
            "copied_checkpoint_set",
            checkpoints_ok,
            f"{len(manifest.checkpoints)} copied; missing={len(missing)} escaped={len(escaped)}",
        )
    )

    strength_db = root / strength_db_name
    if strength_db.is_file():
        ok, detail = _integrity(strength_db)
        checks.append(PreflightCheck("strength_sqlite_integrity", ok, detail))
    else:
        checks.append(PreflightCheck("strength_sqlite_integrity", True, "not present yet; V2 may create it inside the copy"))

    reference_root = root / frozen_reference_dir_name
    manifest_path = reference_root / "reference.json"
    if not reference_root.exists():
        checks.append(
            PreflightCheck(
                "frozen_reference",
                True,
                "not created yet; first copied-state V2 run may freeze the copied champion",
            )
        )
    elif not manifest_path.is_file():
        checks.append(
            PreflightCheck(
                "frozen_reference",
                False,
                f"reference directory exists without manifest: {reference_root}",
            )
        )
    else:
        manager = FrozenReferenceManager(reference_root)
        reference = manager.load()
        if reference is None:
            checks.append(PreflightCheck("frozen_reference", False, "reference manifest could not be loaded"))
        else:
            ref_path = Path(reference.checkpoint_path).expanduser().resolve()
            checksum_ok = manager.verify(reference)
            reference_ok = _inside(ref_path, root) and checksum_ok
            checks.append(
                PreflightCheck(
                    "frozen_reference",
                    reference_ok,
                    f"Gen{reference.generation} -> {ref_path}; checksum={'ok' if checksum_ok else 'BAD'}",
                )
            )

    if include_spawn_probe:
        checks.append(run_spawn_probe())

    return MacPreflightReport(str(root), tuple(checks))
