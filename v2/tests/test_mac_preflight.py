from datetime import datetime, timezone
import sqlite3

from dogmatist_v2.fixed_reference import FrozenReferenceManager
from dogmatist_v2.mac_preflight import audit_copied_state_after_run, validate_copied_state
from dogmatist_v2.state_snapshot import create_validation_snapshot
from dogmatist_v2.strength_lab import RoundStrengthEvidence, StrengthMode
from dogmatist_v2.strength_store import StrengthStore


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
            "CREATE TABLE games (id TEXT PRIMARY KEY, source TEXT)"
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


def _simulate_successful_v2_copy_run(copied):
    conn = sqlite3.connect(copied / "darwinchess.sqlite3")
    try:
        conn.execute("INSERT INTO games(id, source) VALUES ('selfplay-1', 'selfplay')")
        conn.commit()
    finally:
        conn.close()

    champion = copied / "checkpoints" / "generation_15.pt"
    FrozenReferenceManager(copied / "frozen_strength_reference").freeze(
        champion,
        generation=15,
        created_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
    )
    with StrengthStore(copied / "strength_v2.sqlite3") as store:
        store.record_round(
            RoundStrengthEvidence(1, 15, False, 0.5, 4),
            mode=StrengthMode.NORMAL,
            recorded_at=datetime(2026, 8, 20, 12, 1, tzinfo=timezone.utc),
        )


def test_postflight_accepts_reference_and_no_teacher_rows(tmp_path):
    live = tmp_path / "live"
    _make_live_state(live)
    copied = tmp_path / "copy"
    create_validation_snapshot(live, copied)
    _simulate_successful_v2_copy_run(copied)

    report = audit_copied_state_after_run(copied)
    assert report.ok
    names = {row.name: row for row in report.checks}
    assert names["teacher_write_gate"].ok
    assert names["postrun_frozen_reference"].ok
    assert names["strength_round_history"].ok


def test_postflight_rejects_accidental_teacher_persistence_in_first_copy_run(tmp_path):
    live = tmp_path / "live"
    _make_live_state(live)
    copied = tmp_path / "copy"
    create_validation_snapshot(live, copied)
    _simulate_successful_v2_copy_run(copied)

    conn = sqlite3.connect(copied / "darwinchess.sqlite3")
    try:
        conn.execute("INSERT INTO games(id, source) VALUES ('teacher-1', 'strength_teacher')")
        conn.commit()
    finally:
        conn.close()

    report = audit_copied_state_after_run(copied, expect_teacher_persistence=False)
    assert not report.ok
    names = {row.name: row for row in report.checks}
    assert not names["teacher_write_gate"].ok
