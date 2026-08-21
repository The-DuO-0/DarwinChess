import sqlite3

from dogmatist_v2.mac_preflight import validate_copied_state
from dogmatist_v2.state_snapshot import create_validation_snapshot


def _make_live_state(root):
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "gen15.pt"
    checkpoint.write_bytes(b"gen15")
    conn = sqlite3.connect(root / "darwinchess.sqlite3")
    try:
        conn.execute(
            "CREATE TABLE generations (id INTEGER PRIMARY KEY, checkpoint_path TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO generations(id, checkpoint_path, status) VALUES (?, ?, ?)",
            (15, str(checkpoint.resolve()), "champion"),
        )
        conn.commit()
    finally:
        conn.close()
    return checkpoint


def test_preflight_accepts_isolated_snapshot_without_creating_reference_dir(tmp_path):
    live = tmp_path / "live"
    _make_live_state(live)
    copied = tmp_path / "copy"
    create_validation_snapshot(live, copied)

    reference_dir = copied / "frozen_strength_reference"
    assert not reference_dir.exists()
    report = validate_copied_state(copied)
    assert report.ok
    assert not reference_dir.exists()
    names = {row.name: row for row in report.checks}
    assert names["live_state_isolation"].ok
    assert names["main_sqlite_integrity"].ok
    assert names["copied_champion_checkpoint"].ok
    assert names["frozen_reference"].ok


def test_preflight_rejects_copy_that_points_back_to_live_checkpoint(tmp_path):
    live = tmp_path / "live"
    live_checkpoint = _make_live_state(live)
    copied = tmp_path / "copy"
    create_validation_snapshot(live, copied)

    conn = sqlite3.connect(copied / "darwinchess.sqlite3")
    try:
        conn.execute(
            "UPDATE generations SET checkpoint_path=? WHERE id=15",
            (str(live_checkpoint.resolve()),),
        )
        conn.commit()
    finally:
        conn.close()

    report = validate_copied_state(copied)
    assert not report.ok
    names = {row.name: row for row in report.checks}
    assert not names["live_state_isolation"].ok
    assert not names["copied_champion_checkpoint"].ok
