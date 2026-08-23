from datetime import datetime, timedelta, timezone
from pathlib import Path

from dogmatist_v2.archive import ArchiveTier
from dogmatist_v2.chronicle_store import ChronicleStore
from dogmatist_v2.dynasty import ChampionReign
from dogmatist_v2.opentree_promotion import PromotionDecision
from dogmatist_v2.promotion_bridge import ChampionCheckpoint, PromotionChronicleBridge
from dogmatist_v2.specialist_bridge import SpecialistCheckpoint, SpecialistChronicleBridge
from dogmatist_v2.specialists import OpeningBucket, SpecialistRecord
from dogmatist_v2.strength_bridge import PositionObservation, StrengthCapturePolicy, StrengthEvidenceBridge
from dogmatist_v2.strength_store import StrengthStore


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)


def test_confirmed_promotion_atomically_moves_champion_and_is_retry_safe(tmp_path):
    with ChronicleStore(tmp_path / "chronicle.sqlite3") as store:
        store.start_reign(ChampionReign(15, NOW - timedelta(hours=9)))
        bridge = PromotionChronicleBridge(store)
        decision = PromotionDecision("promote", 23, 15, "Arena and fixed-reference guard passed")
        applied = bridge.apply(
            decision,
            outgoing_checkpoint=ChampionCheckpoint(15, Path("archive/gen15.pt"), 1200),
            incoming_checkpoint=ChampionCheckpoint(23, Path("active/gen23.pt"), 1300),
            occurred_at=NOW,
            evidence={"arena_score": 0.61},
        )
        assert applied is True
        assert store.active_reign()["generation_id"] == 23
        entries = {row.generation_id: row for row in store.archive_entries()}
        assert entries[15].tier is ArchiveTier.IMMORTAL
        assert entries[15].protected
        assert entries[23].tier is ArchiveTier.ACTIVE
        assert bridge.apply(
            decision,
            outgoing_checkpoint=ChampionCheckpoint(15, Path("archive/gen15.pt"), 1200),
            incoming_checkpoint=ChampionCheckpoint(23, Path("active/gen23.pt"), 1300),
            occurred_at=NOW,
        ) is False
        assert len([row for row in store.recent_events() if row["kind"] == "champion_succession"]) == 1


def test_promotion_bridge_refuses_reject_or_mismatched_checkpoint(tmp_path):
    with ChronicleStore(tmp_path / "chronicle.sqlite3") as store:
        bridge = PromotionChronicleBridge(store)
        rejected = PromotionDecision("reject", 23, 15, "failed")
        try:
            bridge.apply(
                rejected,
                outgoing_checkpoint=ChampionCheckpoint(15, Path("gen15.pt"), 1),
                incoming_checkpoint=ChampionCheckpoint(23, Path("gen23.pt"), 1),
                occurred_at=NOW,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("reject decision must never mutate Chronicle")


def test_specialist_bridge_keeps_trait_and_only_colds_existing_body(tmp_path):
    records = [
        SpecialistRecord("Gen31", OpeningBucket("B20"), 12, 8.0, 8.0 / 12.0, 0.14),
        SpecialistRecord("Gen32", OpeningBucket("C45"), 10, 6.0, 0.60, 0.10),
    ]
    with ChronicleStore(tmp_path / "chronicle.sqlite3") as store:
        bridge = SpecialistChronicleBridge(store, minimum_preserve_advantage=0.08)
        preserved = bridge.apply(
            records,
            checkpoints={"Gen31": SpecialistCheckpoint(Path("archive/gen31.pt"), 900)},
            occurred_at=NOW,
        )
        assert preserved == (31,)
        traits = store.trait_records(trait_kind="opening")
        assert {row["generation_id"] for row in traits} == {31, 32}
        entries = {row.generation_id: row for row in store.archive_entries()}
        assert entries[31].tier is ArchiveTier.COLD
        assert entries[31].protected
        assert entries[32].tier is ArchiveTier.HISTORY_ONLY
        assert entries[32].checkpoint_path is None


def test_strength_evidence_bridge_only_keeps_high_value_positions(tmp_path):
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        bridge = StrengthEvidenceBridge(
            store,
            StrengthCapturePolicy(
                minimum_value_error=0.30,
                minimum_policy_uncertainty=0.70,
                minimum_loss_severity=0.80,
                max_positions_per_game=2,
            ),
        )
        observations = [
            PositionObservation("8/8/8/8/8/8/7k/K7 w - - 0 1", "end", 15, 7, 0.9, -1.0, 0.2),
            PositionObservation("8/8/8/8/8/6k1/8/K7 w - - 0 1", "end", 15, 7, 0.1, 0.0, 0.9),
            PositionObservation("8/8/8/8/8/5k2/8/K7 w - - 0 1", "end", 15, 7, 0.05, 0.0, 0.1),
        ]
        captured = bridge.ingest_game(observations, observed_at=NOW)
        assert len(captured) == 2
        assert store.hard_position_count() == 2
        assert max(row.value_error for row in captured) > 0.9
