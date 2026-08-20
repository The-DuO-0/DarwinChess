from dogmatist_v2.runtime import (
    ColorPairing,
    ComputeBudgetClock,
    GameState,
    LeaguePairScheduler,
)
from dogmatist_v2.strength_lab import RoundStrengthEvidence, StrengthLabController
from dogmatist_v2.ui_flow import EvolutionStage, build_evolution_flow_snapshot, encode_ui_event


class FakeTime:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_compute_budget_counts_active_runtime_not_paused_sleep():
    now = FakeTime()
    clock = ComputeBudgetClock(10 * 60 * 60, now=now)
    now.advance(60)
    clock.pause()
    now.advance(8 * 60 * 60)
    assert clock.elapsed_seconds == 60
    clock.resume()
    now.advance(120)
    assert clock.elapsed_seconds == 180
    assert clock.remaining_seconds == 10 * 60 * 60 - 180
    assert clock.snapshot()["wall_sleep_counts"] is False


def test_league_runs_three_games_but_drains_only_started_colour_pairs():
    now = FakeTime()
    clock = ComputeBudgetClock(1000, now=now)
    league = LeaguePairScheduler(
        [
            ColorPairing("A", "champ", "a"),
            ColorPairing("B", "champ", "b"),
            ColorPairing("C", "champ", "c"),
        ],
        clock,
        parallel_games=3,
        hard_game_timeout_seconds=500,
        stall_timeout_seconds=100,
    )

    started = league.poll_startable()
    assert [g.spec.game_id for g in started] == ["A:w", "A:b", "B:w"]
    league.request_drain("compute_budget_exhausted")

    league.complete("B:w", result="1/2-1/2")
    followup = league.poll_startable()
    assert [g.spec.game_id for g in followup] == ["B:b"]
    assert all(g.spec.pairing_id != "C" for g in league.active_games)

    for game_id in ["A:w", "A:b", "B:b"]:
        league.complete(game_id, result="1/2-1/2")
    assert league.poll_startable() == []
    assert league.safe_to_stop
    assert not league.all_pairings_complete


def test_budget_expiry_enters_safe_colour_pair_drain():
    now = FakeTime()
    clock = ComputeBudgetClock(10, now=now)
    league = LeaguePairScheduler(
        [ColorPairing("A", "champ", "a"), ColorPairing("B", "champ", "b")],
        clock,
        parallel_games=2,
    )
    started = league.poll_startable()
    assert [g.spec.game_id for g in started] == ["A:w", "A:b"]
    now.advance(11)
    league.complete("A:w", result="1-0")
    assert league.draining
    assert league.stop_reason == "compute_budget_exhausted"
    assert league.poll_startable() == []
    league.complete("A:b", result="0-1")
    assert league.safe_to_stop


def test_watchdog_marks_stalled_game_terminal():
    now = FakeTime()
    clock = ComputeBudgetClock(1000, now=now)
    league = LeaguePairScheduler(
        [ColorPairing("A", "champ", "a")],
        clock,
        parallel_games=2,
        hard_game_timeout_seconds=120,
        stall_timeout_seconds=20,
    )
    league.poll_startable()
    league.report_progress("A:w", 8)
    now.advance(19)
    assert league.poll_watchdogs() == []
    now.advance(2)
    trips = league.poll_watchdogs()
    assert {trip.game_id for trip in trips} == {"A:w", "A:b"}
    assert all(trip.reason == "no_move_progress_timeout" for trip in trips)
    timed_out = {g.spec.game_id: g for g in league.terminal_games}
    assert timed_out["A:w"].state is GameState.TIMED_OUT
    assert timed_out["A:w"].plies == 8


def test_ui_snapshot_exposes_flow_game_turn_runtime_and_strength_lab():
    now = FakeTime()
    clock = ComputeBudgetClock(100, now=now)
    league = LeaguePairScheduler([ColorPairing("A", "champ", "a")], clock, parallel_games=2)
    league.poll_startable()
    league.report_progress("A:w", 17)
    now.advance(12)
    plan = StrengthLabController().plan([
        RoundStrengthEvidence(1, 15, False, 0.60, 8),
        RoundStrengthEvidence(2, 15, False, 0.61, 8),
        RoundStrengthEvidence(3, 15, False, 0.61, 8),
        RoundStrengthEvidence(4, 15, False, 0.62, 8),
    ])
    snapshot = build_evolution_flow_snapshot(
        round_index=4,
        stage=EvolutionStage.LEAGUE,
        clock=clock,
        league=league,
        strength_lab_plan=plan,
    )
    payload = snapshot.as_dict()
    assert payload["flow"][3]["state"] == "current"
    assert payload["strength_lab"]["mode"] == "plateau"
    game = payload["league"]["active_games"][0]
    assert "plies" in game
    assert "completed_full_moves" in game
    assert "runtime_seconds" in game
    assert encode_ui_event(snapshot).startswith("DOGMATIST_UI ")
