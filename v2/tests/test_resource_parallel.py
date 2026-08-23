import pytest

from dogmatist_v2.resource import ResourceController, ResourceSample


def test_league_concurrency_adapts_only_between_two_and_three_games():
    ctl = ResourceController(min_league_games=2, max_league_games=3)
    assert ctl.budget.league_games == 2

    for _ in range(5):
        budget = ctl.update(ResourceSample(20, 25, "nominal"))
    assert budget.league_games == 3

    for _ in range(5):
        budget = ctl.update(ResourceSample(96, 90, "serious"))
    assert budget.league_games == 2
    assert budget.trainer_slots == 1


def test_league_concurrency_rejects_unsafe_range():
    with pytest.raises(ValueError):
        ResourceController(min_league_games=1, max_league_games=3)
    with pytest.raises(ValueError):
        ResourceController(min_league_games=2, max_league_games=4)
