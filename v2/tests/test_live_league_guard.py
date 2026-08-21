from types import SimpleNamespace

from dogmatist_v2.live_league_guard import (
    DrainedArenaResult,
    LiveLeagueDrainOverride,
    LiveLeagueDrainState,
    build_budget_aware_population_arena,
)


class ExpireAfterFirstPairClock:
    def __init__(self):
        self.checks = 0

    @property
    def expired(self):
        self.checks += 1
        return self.checks >= 2


class AlwaysExpiredClock:
    @property
    def expired(self):
        return True


class FakePopulationArena:
    def __init__(self):
        self.seed_batches = []
        self.games = 0

    def _play_paired_set(
        self,
        round_id,
        table,
        first_generation,
        second_generation,
        first_searcher,
        second_searcher,
        seeds,
        depth,
        max_plies,
    ):
        self.seed_batches.append(list(seeds))
        self.games += len(seeds) * 2

    def _archive_specialists(self, round_id, table, champion_generation):
        return {"B20": 31}


def test_budget_guard_finishes_both_colors_then_stops_before_next_seed():
    state = LiveLeagueDrainState()
    wrapped = build_budget_aware_population_arena(
        FakePopulationArena,
        clock=ExpireAfterFirstPairClock(),
        state=state,
    )
    arena = wrapped()
    arena._play_paired_set(
        1,
        object(),
        21,
        15,
        object(),
        object(),
        ["opening-a", "opening-b", "opening-c"],
        2,
        220,
    )
    assert arena.seed_batches == [["opening-a"]]
    assert arena.games == 2
    assert state.pairs_started == 1
    assert state.pairs_completed == 1
    assert state.draining
    assert state.reason == "compute_budget_exhausted"
    assert arena._archive_specialists(1, object(), 15) == {}


def test_budget_wrapper_preserves_base_module_for_next_parallel_wrapper():
    original_module = FakePopulationArena.__module__
    wrapped = build_budget_aware_population_arena(
        FakePopulationArena,
        clock=AlwaysExpiredClock(),
        state=LiveLeagueDrainState(),
    )
    assert wrapped.__module__ == original_module
    assert wrapped.__module__ != "dogmatist_v2.live_league_guard"


class FakeMemory:
    def __init__(self):
        self.updated = []
        self.insights = []

    def update_generation(self, generation, **kwargs):
        self.updated.append((generation, kwargs))

    def add_insight(self, *args):
        self.insights.append(args)


class FakeRuntime:
    def __init__(self):
        self.memory = FakeMemory()
        self.gate_calls = 0
        self.harvest_calls = 0

    def champion_info(self):
        return {"id": 15}

    def gate_challenger(self, challenger_id, challenger, *, games=None):
        self.gate_calls += 1
        return "original-gate"

    def _harvest_specialist_experience(self, *args, **kwargs):
        self.harvest_calls += 1
        return 7


def test_live_override_blocks_final_gate_and_harvest_after_budget_drain_and_restores():
    runtime = FakeRuntime()
    module = SimpleNamespace(PopulationArena=FakePopulationArena)
    original_arena = module.PopulationArena
    original_gate_func = runtime.gate_challenger.__func__
    original_harvest_func = runtime._harvest_specialist_experience.__func__

    with LiveLeagueDrainOverride(
        runtime,
        AlwaysExpiredClock(),
        runtime_module=module,
    ) as guard:
        assert module.PopulationArena is not original_arena
        result = runtime.gate_challenger(22, object())
        assert isinstance(result, DrainedArenaResult)
        assert not result.promoted
        assert runtime.gate_calls == 0
        assert runtime._harvest_specialist_experience(object(), object()) == 0
        assert runtime.harvest_calls == 0
        assert guard.state.draining
        assert runtime.memory.updated[-1] == (22, {"status": "aborted"})
        assert runtime.memory.insights

    assert module.PopulationArena is original_arena
    assert runtime.gate_challenger.__func__ is original_gate_func
    assert runtime._harvest_specialist_experience.__func__ is original_harvest_func
    assert runtime.gate_challenger(22, object()) == "original-gate"
    assert runtime._harvest_specialist_experience(object(), object()) == 7
