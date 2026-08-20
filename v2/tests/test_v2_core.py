from dogmatist_v2.league import Candidate, LeagueTable, MatchResult, select_survivors
from dogmatist_v2.resource import ResourceController, ResourceSample
from dogmatist_v2.specialists import SpecialistArchive


def test_league_and_elite_pool():
    matches = [
        MatchResult("champ", "a", "1-0"),
        MatchResult("a", "champ", "1-0"),
        MatchResult("a", "b", "1-0"),
        MatchResult("b", "a", "1/2-1/2"),
        MatchResult("a", "champ", "1/2-1/2"),
        MatchResult("champ", "a", "0-1"),
    ]
    table = LeagueTable.from_matches(matches)
    population = [Candidate("champ", "old"), Candidate("a", "champ"), Candidate("b", "champ")]
    survivors = select_survivors(population, table, champion_id="champ", elite_count=2, minimum_games=2)
    assert survivors[0].candidate_id == "champ"
    assert survivors[1].candidate_id == "a"


def test_specialist_can_survive_without_overall_promotion():
    matches = []
    for _ in range(4):
        matches.append(MatchResult("special", "other", "1-0", opening="B20"))
        matches.append(MatchResult("champ", "other", "1/2-1/2", opening="B20"))
    archive = SpecialistArchive()
    accepted = archive.update_from_matches(
        matches,
        reference_id="champ",
        minimum_games=4,
        minimum_advantage=0.1,
    )
    assert accepted
    assert accepted[0].candidate_id == "special"
    assert archive.donors_for("B20")[0].candidate_id == "special"


def test_resource_controller_never_adds_gpu_trainers():
    ctl = ResourceController(max_selfplay_workers=4, max_arena_workers=2)
    for _ in range(5):
        budget = ctl.update(ResourceSample(25, 30, "nominal"))
    assert budget.selfplay_workers == 4
    assert budget.trainer_slots == 1

    budget = ctl.update(ResourceSample(95, 88, "serious"))
    assert budget.selfplay_workers == 3
    assert budget.trainer_slots == 1
