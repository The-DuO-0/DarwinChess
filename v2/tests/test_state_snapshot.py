import sqlite3
from pathlib import Path

import pytest

from dogmatist_v2.state_snapshot import create_validation_snapshot, validate_snapshot_isolation


def _seed_live(root: Path):
    root.mkdir(parents=True)
    checkpoints = root / "checkpoints"
    checkpoints.mkdir()
    g15 = checkpoints / "generation_15.pt"
    g16 = checkpoints / "generation_16.pt"
    g15.write_bytes(b"champion-weights")
    g16.write_bytes(b"candidate-weights")

    db = sqlite3.connect(root / "darwinchess.sqlite3")
    db.execute(
        """
        CREATE TABLE generations(
            id INTEGER PRIMARY KEY,
            checkpoint_path TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    db.execute("INSERT INTO generations VALUES(15, ?, 'champion')", (str(g15),))
    db.execute("INSERT INTO generations VALUES(16, ?, 'rejected')", (str(g16),))
    db.commit()
    db.close()
    return g15, g16


def test_snapshot_copies_checkpoints_and_rewrites_only_copied_database(tmp_path):
    live = tmp_path / "live"
    snapshot = tmp_path / "snapshot"
    original15, original16 = _seed_live(live)

    manifest = create_validation_snapshot(live, snapshot)
    assert manifest.champion_generation == 15
    assert len(manifest.checkpoints) == 2
    validate_snapshot_isolation(manifest)

    copied_db = sqlite3.connect(snapshot / "darwinchess.sqlite3")
    copied_rows = dict(copied_db.execute("SELECT id, checkpoint_path FROM generations"))
    copied_db.close()
    assert Path(copied_rows[15]).is_file()
    assert Path(copied_rows[16]).is_file()
    assert Path(copied_rows[15]).resolve().is_relative_to(snapshot.resolve())
    assert Path(copied_rows[16]).resolve().is_relative_to(snapshot.resolve())
    assert Path(copied_rows[15]).read_bytes() == b"champion-weights"

    # The live database still points to the original files.
    live_db = sqlite3.connect(live / "darwinchess.sqlite3")
    live_rows = dict(live_db.execute("SELECT id, checkpoint_path FROM generations"))
    live_db.close()
    assert Path(live_rows[15]).resolve() == original15.resolve()
    assert Path(live_rows[16]).resolve() == original16.resolve()


def test_snapshot_refuses_destination_inside_live_state(tmp_path):
    live = tmp_path / "live"
    _seed_live(live)
    with pytest.raises(ValueError):
        create_validation_snapshot(live, live / "unsafe-copy")


def test_restricted_snapshot_never_falls_back_to_live_rejected_checkpoint(tmp_path):
    live = tmp_path / "live"
    snapshot = tmp_path / "snapshot"
    _seed_live(live)
    manifest = create_validation_snapshot(live, snapshot, include_statuses={"champion"})
    validate_snapshot_isolation(manifest)

    db = sqlite3.connect(snapshot / "darwinchess.sqlite3")
    paths = dict(db.execute("SELECT id, checkpoint_path FROM generations"))
    db.close()
    assert Path(paths[15]).is_file()
    assert "unavailable" in Path(paths[16]).parts
    assert not Path(paths[16]).exists()
