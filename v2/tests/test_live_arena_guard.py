from dataclasses import dataclass

from dogmatist_v2.live_arena_guard import LiveArenaDrainState, build_budget_aware_arena


class FakeClock:
    def __init__(self):
        self.expired = False


class OpeningCurriculum:
    def __init__(self, *args, **kwargs):
        pass

    def arena_pairs(self, count):
        return [(f"fen-{i}", f"opening-{i}") for i in range(count)]


@dataclass
class FakeArenaResult:
    games: int
    wins: int
    draws: int
    losses: int
    score: float
    wilson_lower: float
    promoted: bool


class FakeArena:
    def __init__(self, clock):
        self.clock = clock

    def compare(self):
        # This intentionally mirrors the important production shape: request one
        # opening, play both colours, then request the next opening.
        pairs = OpeningCurriculum(seed=1).arena_pairs(5)
        games = 0
        for _start, _opening in pairs:
            games += 2
            if games == 2:
                # Budget expires during/at the end of the first colour pair.
                self.clock.expired = True
        return FakeArenaResult(games, games, 0, 0, 1.0, 0.9, True)


def test_held_out_arena_finishes_current_pair_then_stops_and_cannot_promote():
    clock = FakeClock()
    state = LiveArenaDrainState()
    Wrapped = build_budget_aware_arena(FakeArena, clock=clock, state=state)
    result = Wrapped(clock).compare()

    assert result.games == 2
    assert result.promoted is False
    assert state.draining is True
    assert state.reason == "compute_budget_exhausted"
    assert state.pairs_started == 1
    assert state.pairs_completed == 1
    assert state.games_completed == 2


def test_arena_without_budget_expiry_keeps_original_result():
    clock = FakeClock()

    class NoExpireArena(FakeArena):
        def compare(self):
            pairs = OpeningCurriculum(seed=1).arena_pairs(2)
            games = sum(2 for _ in pairs)
            return FakeArenaResult(games, games, 0, 0, 1.0, 0.9, True)

    state = LiveArenaDrainState()
    Wrapped = build_budget_aware_arena(NoExpireArena, clock=clock, state=state)
    result = Wrapped(clock).compare()
    assert result.games == 4
    assert result.promoted is True
    assert state.draining is False
    assert state.pairs_completed == 2
