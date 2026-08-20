from datetime import datetime, timezone

from dogmatist_v2.strength_lab import StrengthLabController
from dogmatist_v2.strength_pipeline import EngineABTrialPlan, StrengthPipelinePlanner
from dogmatist_v2.strength_store import HardPositionEvidence, StrengthStore


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _seed(store: StrengthStore, count: int) -> None:
    for index in range(count):
        store.upsert_hard_position(
            HardPositionEvidence(
                fen=f"8/8/8/8/8/8/{index + 1}k6/K7 w - - 0 1",
                opening_bucket="endgame" if index % 2 == 0 else "open-A",
                source_generation=15,
                source_kind="arena_loss",
                severity=1.0 - 0.03 * index,
                uncertainty=0.5,
                value_error=0.6,
                round_index=3,
            ),
            observed_at=NOW,
            max_per_bucket=64,
        )


def test_recipe_preserves_total_and_backfills_missing_targeted_data(tmp_path):
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        _seed(store, 5)
        plan = StrengthLabController().plan([])
        recipe = StrengthPipelinePlanner(store).build_recipe(
            plan,
            total_examples=100,
            available_specialist_examples=4,
        )
        assert recipe.effective_total == 100
        assert recipe.specialist_examples == 4
        assert recipe.backfilled_examples > 0
        assert recipe.natural_selfplay_examples > recipe.requested.natural_selfplay


def test_teacher_requests_use_deeper_search_multiplier(tmp_path):
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        _seed(store, 40)
        plan = StrengthLabController().plan([])
        recipe = StrengthPipelinePlanner(store).build_recipe(
            plan,
            total_examples=40,
            available_specialist_examples=40,
            hard_position_bucket_cap=20,
        )
        assert recipe.teacher_requests
        assert all(req.search_multiplier == 2.0 for req in recipe.teacher_requests)
        assert recipe.effective_total == 40


def test_engine_ab_trial_uses_same_fen_checkpoint_and_swaps_colours():
    trial = EngineABTrialPlan(
        baseline_revision_id="search-r1",
        candidate_revision_id="search-r2",
        frozen_checkpoint="gen15.pt",
        start_fens=("start-a", "start-b"),
    )
    games = trial.game_specs()
    assert trial.paired_games == 4
    assert games[0]["fen"] == games[1]["fen"] == "start-a"
    assert games[0]["checkpoint"] == games[1]["checkpoint"] == "gen15.pt"
    assert games[0]["white_revision"] == "search-r2"
    assert games[1]["white_revision"] == "search-r1"
