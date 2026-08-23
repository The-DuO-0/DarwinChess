from datetime import datetime, timedelta, timezone
from pathlib import Path

from dogmatist_v2.archive import ArchiveEntry, ArchiveTier
from dogmatist_v2.chronicle_store import ChronicleStore
from dogmatist_v2.dynasty import ChampionReign, HistoricalEvent


UTC = timezone.utc


def test_archive_metadata_round_trip_without_loading_checkpoint(tmp_path):
    db = tmp_path / "chronicle.sqlite3"
    with ChronicleStore(db) as store:
        entry = ArchiveEntry(
            generation_id=31,
            tier=ArchiveTier.COLD,
            checkpoint_path=Path("archive/gen31.pt"),
            checkpoint_bytes=12345,
            specialist_score=1.7,
            reason="sicilian specialist",
        )
        store.upsert_archive_entry(entry, archived_at=datetime(2026, 8, 20, tzinfo=UTC))
        loaded = store.archive_entries()

    assert loaded == (entry,)


def test_champion_reign_and_event_are_durable(tmp_path):
    db = tmp_path / "chronicle.sqlite3"
    start = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)
    end = start + timedelta(hours=5)

    with ChronicleStore(db) as store:
        store.start_reign(ChampionReign(generation_id=15, started_at=start))
        store.increment_reign_activity(15, challengers=3, games=36)
        store.end_reign(
            15,
            ended_at=end,
            dethroned_by=23,
            replacement_reason="Gen23 passed promotion gate",
        )
        event_id = store.record_event(
            HistoricalEvent(
                event_id=None,
                occurred_at=end,
                kind="champion_dethroned",
                generation_id=15,
                related_generation_id=23,
                text="Gen15 reign ended after five hours.",
            ),
            evidence={"games": 36},
        )
        events = store.recent_events()

    assert event_id > 0
    assert len(events) == 1
    assert events[0]["kind"] == "champion_dethroned"
    assert events[0]["generation_id"] == 15
    assert events[0]["related_generation_id"] == 23


def test_specialist_trait_is_upserted(tmp_path):
    db = tmp_path / "chronicle.sqlite3"
    now = datetime(2026, 8, 20, tzinfo=UTC)
    with ChronicleStore(db) as store:
        store.record_trait(
            generation_id=31,
            trait_kind="opening",
            trait_key="sicilian",
            score=84.0,
            sample_games=20,
            evidence={"unit": "elo_delta"},
            updated_at=now,
        )
        store.record_trait(
            generation_id=31,
            trait_kind="opening",
            trait_key="sicilian",
            score=92.0,
            sample_games=40,
            evidence={"unit": "elo_delta"},
            updated_at=now + timedelta(minutes=10),
        )
        row = store._conn.execute(
            "SELECT score, sample_games FROM generation_traits WHERE generation_id=31"
        ).fetchone()

    assert row["score"] == 92.0
    assert row["sample_games"] == 40
