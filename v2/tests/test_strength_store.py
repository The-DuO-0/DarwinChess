from datetime import datetime, timezone

import pytest

from dogmatist_v2.strength_lab import (
    EngineRevisionGate,
    EngineTrialEvidence,
    RoundStrengthEvidence,
    StrengthLabController,
    StrengthMode,
)
from dogmatist_v2.strength_store import HardPositionEvidence, StrengthStore


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def test_strength_round_history_drives_plateau_plan(tmp_path):
    path = tmp_path / "strength.sqlite3"
    with StrengthStore(path) as store:
        for index, score in enumerate((0.51, 0.515, 0.52, 0.522), start=1):
            store.record_round(
                RoundStrengthEvidence(index, 15, False, score, 8),
                mode=StrengthMode.NORMAL,
                recorded_at=NOW,
            )
        history = store.round_history()
        plan = StrengthLabController().plan(history)
        assert plan.mode is StrengthMode.PLATEAU
        budget = plan.batch_budget(100)
        assert budget.total == 100
        assert budget.hard_positions == 30
        assert budget.deep_search_teacher == 15


def test_hard_positions_deduplicate_and_bucket_cap(tmp_path):
    path = tmp_path / "strength.sqlite3"
    fen = "8/8/8/8/8/8/7k/K7 w - - 0 1"
    same_board_later = "8/8/8/8/8/8/7k/K7 w - - 17 42"
    with StrengthStore(path) as store:
        store.upsert_hard_position(
            HardPositionEvidence(fen, "endgame", 15, "arena_loss", 0.8, 0.2, 0.5, 1),
            observed_at=NOW,
            max_per_bucket=2,
        )
        store.upsert_hard_position(
            HardPositionEvidence(same_board_later, "endgame", 15, "repeat", 0.9, 0.3, 0.6, 2),
            observed_at=NOW,
            max_per_bucket=2,
        )
        assert store.hard_position_count() == 1

        store.upsert_hard_position(
            HardPositionEvidence("8/8/8/8/8/8/6k1/K7 w - - 0 1", "endgame", 15, "x", 0.1, 0.1, 0.1, 2),
            observed_at=NOW,
            max_per_bucket=2,
        )
        store.upsert_hard_position(
            HardPositionEvidence("8/8/8/8/8/8/5k2/K7 w - - 0 1", "endgame", 15, "x", 1.0, 1.0, 1.0, 2),
            observed_at=NOW,
            max_per_bucket=2,
        )
        assert store.hard_position_count() == 2
        sample = store.sample_hard_positions(2, per_bucket_cap=2)
        assert len(sample) == 2
        assert sample[0].severity >= sample[1].severity


def test_sampling_caps_one_opening_bucket(tmp_path):
    path = tmp_path / "strength.sqlite3"
    with StrengthStore(path) as store:
        for index in range(4):
            store.upsert_hard_position(
                HardPositionEvidence(
                    f"8/8/8/8/8/8/{index + 1}k6/K7 w - - 0 1",
                    "A",
                    15,
                    "selfplay",
                    1.0 - index * 0.1,
                    0.4,
                    0.5,
                    index,
                ),
                observed_at=NOW,
                max_per_bucket=10,
            )
        store.upsert_hard_position(
            HardPositionEvidence("8/8/8/8/8/7k/8/K7 w - - 0 1", "B", 15, "selfplay", 0.5, 0.5, 0.5, 1),
            observed_at=NOW,
            max_per_bucket=10,
        )
        sampled = store.sample_hard_positions(4, per_bucket_cap=2)
        buckets = [row.opening_bucket for row in sampled]
        assert buckets.count("A") <= 2
        assert "B" in buckets


def test_opening_bucket_stats_and_filtered_sampling(tmp_path):
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        for index in range(3):
            store.upsert_hard_position(
                HardPositionEvidence(
                    f"queen-gambit-{index} w - - 0 1",
                    "Queen's Gambit",
                    54,
                    "selfplay_opening",
                    0.7,
                    0.1,
                    0.5,
                    18,
                ),
                observed_at=NOW,
            )
        store.upsert_hard_position(
            HardPositionEvidence("reti-0 w - - 0 1", "Reti", 54, "selfplay", 0.3, 0.1, 0.2, 18),
            observed_at=NOW,
        )
        focus = store.sample_hard_positions(
            8,
            per_bucket_cap=8,
            opening_buckets=("Queen's Gambit",),
        )
        assert focus
        assert {row.opening_bucket for row in focus} == {"Queen's Gambit"}
        stats = {row["opening_bucket"]: row for row in store.opening_bucket_stats()}
        assert stats["Queen's Gambit"]["hard_positions"] == 3
        assert stats["Queen's Gambit"]["max_priority"] > stats["Reti"]["max_priority"]


def test_engine_revision_is_adopted_only_after_gate_accepts(tmp_path):
    path = tmp_path / "strength.sqlite3"
    gate = EngineRevisionGate()
    with StrengthStore(path) as store:
        store.register_engine_revision(
            "search-r1",
            parent_revision_id=None,
            description="baseline",
            created_at=NOW,
            status="active",
        )
        store.register_engine_revision(
            "search-r2",
            parent_revision_id="search-r1",
            description="candidate search change",
            created_at=NOW,
        )
        evidence = EngineTrialEvidence("search-r2", 16, 0.58, 0.01, 1.20)
        decision = gate.decide(evidence)
        assert decision.action.value == "accept"
        store.record_engine_trial(
            evidence,
            baseline_revision_id="search-r1",
            decision=decision,
            recorded_at=NOW,
        )
        store.adopt_engine_revision("search-r2", adopted_at=NOW)
        assert store.active_engine_revision() == "search-r2"


def test_engine_revision_cannot_skip_or_bypass_gate(tmp_path):
    path = tmp_path / "strength.sqlite3"
    gate = EngineRevisionGate()
    with StrengthStore(path) as store:
        store.register_engine_revision(
            "search-r1",
            parent_revision_id=None,
            description="baseline",
            created_at=NOW,
            status="active",
        )
        store.register_engine_revision(
            "search-bad",
            parent_revision_id="search-r1",
            description="too expensive",
            created_at=NOW,
        )
        with pytest.raises(RuntimeError, match="no recorded A/B gate evidence"):
            store.adopt_engine_revision("search-bad", adopted_at=NOW)

        evidence = EngineTrialEvidence("search-bad", 16, 0.60, 0.02, 1.90)
        decision = gate.decide(evidence)
        assert decision.action.value == "reject"
        store.record_engine_trial(
            evidence,
            baseline_revision_id="search-r1",
            decision=decision,
            recorded_at=NOW,
        )
        with pytest.raises(RuntimeError, match="latest gate=reject"):
            store.adopt_engine_revision("search-bad", adopted_at=NOW)
        assert store.active_engine_revision() == "search-r1"
