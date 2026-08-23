from datetime import datetime, timezone
from pathlib import Path

import pytest

from dogmatist_v2.opening_diagnosis import (
    diagnose_openings,
    reset_copied_strength_state,
)
from dogmatist_v2.strength_store import HardPositionEvidence, StrengthStore


NOW = datetime(2026, 8, 22, 2, 0, tzinfo=timezone.utc)


def _seed_opening(
    store: StrengthStore,
    *,
    generation: int,
    bucket: str,
    count: int,
    severity: float,
    value_error: float,
) -> None:
    for index in range(count):
        store.upsert_hard_position(
            HardPositionEvidence(
                fen=f"{bucket}-{generation}-{index} w - - 0 1",
                opening_bucket=bucket,
                source_generation=generation,
                source_kind="selfplay_opening",
                severity=severity,
                uncertainty=0.0,
                value_error=value_error,
                round_index=18,
            ),
            observed_at=NOW,
            max_per_bucket=64,
        )


def test_diagnosis_filters_to_requested_generation_and_ranks_pressure(tmp_path):
    db = tmp_path / "strength_v2.sqlite3"
    with StrengthStore(db) as store:
        _seed_opening(
            store,
            generation=54,
            bucket="Queen's Gambit",
            count=5,
            severity=0.95,
            value_error=0.85,
        )
        _seed_opening(
            store,
            generation=54,
            bucket="Reti",
            count=3,
            severity=0.15,
            value_error=0.10,
        )
        _seed_opening(
            store,
            generation=62,
            bucket="Scandinavian",
            count=6,
            severity=1.0,
            value_error=1.0,
        )

    report = diagnose_openings(db, generation=54)
    assert report.ready
    assert report.rows[0].opening_bucket == "Queen's Gambit"
    assert report.rows[0].pressure > report.rows[1].pressure
    assert report.rows[0].status in {"WEAK", "WATCH"}
    assert "Scandinavian" not in {row.opening_bucket for row in report.rows}
    assert report.observed_generations == (54, 62)
    assert not report.clean_generation_only
    assert report.book_moves_injected is False
    assert report.novel_openings_allowed is True


def test_diagnosis_ignores_non_opening_rows(tmp_path):
    db = tmp_path / "strength_v2.sqlite3"
    with StrengthStore(db) as store:
        store.upsert_hard_position(
            HardPositionEvidence(
                fen="middle-54 w - - 0 1",
                opening_bucket="Queen's Gambit",
                source_generation=54,
                source_kind="selfplay",
                severity=1.0,
                uncertainty=1.0,
                value_error=1.0,
                round_index=18,
            ),
            observed_at=NOW,
        )

    report = diagnose_openings(db, generation=54)
    assert not report.ready
    assert report.rows == ()


def test_reset_copied_strength_state_only_touches_snapshot_db(tmp_path):
    snapshot = tmp_path / "validation" / ".darwinchess"
    snapshot.mkdir(parents=True)
    db = snapshot / "strength_v2.sqlite3"
    wal = snapshot / "strength_v2.sqlite3-wal"
    unrelated = snapshot / "darwinchess.sqlite3"
    db.write_bytes(b"db")
    wal.write_bytes(b"wal")
    unrelated.write_bytes(b"keep")

    removed = reset_copied_strength_state(snapshot)
    assert str(db.resolve()) in removed
    assert str(wal.resolve()) in removed
    assert not db.exists()
    assert not wal.exists()
    assert unrelated.read_bytes() == b"keep"


def test_reset_refuses_non_snapshot_directory(tmp_path):
    with pytest.raises(ValueError, match=".darwinchess"):
        reset_copied_strength_state(tmp_path)
