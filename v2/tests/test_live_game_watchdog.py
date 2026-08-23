from dogmatist_v2.live_game_watchdog import (
    MIN_EMERGENCY_GAME_SECONDS,
    MIN_STALL_SECONDS,
    LiveGameWatchdogPolicy,
    install_live_game_watchdog_policy,
)
from dogmatist_v2.runtime import ColorPairing, ComputeBudgetClock, LeaguePairScheduler


class FakeTime:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class Runtime:
    def __init__(self):
        self.config = {
            "league": {
                "watchdog_stall_seconds": 123.0,
                "custom": "keep-me",
            }
        }


def test_production_watchdog_policy_is_extremely_conservative_and_restores_config():
    runtime = Runtime()
    policy = LiveGameWatchdogPolicy()
    assert policy.stall_seconds == 60 * 60
    assert policy.emergency_game_seconds == 24 * 60 * 60
    assert policy.ui_payload()["budget_interrupts_games"] is False

    with install_live_game_watchdog_policy(runtime, policy):
        league = runtime.config["league"]
        assert league["watchdog_stall_seconds"] == 60 * 60
        assert league["watchdog_hard_seconds"] == 24 * 60 * 60
        assert league["watchdog_budget_interrupts_games"] is False
        assert league["custom"] == "keep-me"

    assert runtime.config["league"] == {
        "watchdog_stall_seconds": 123.0,
        "custom": "keep-me",
    }


def test_stale_aggressive_config_cannot_lower_bug_only_floor():
    policy = LiveGameWatchdogPolicy(
        stall_seconds=30 * 60,
        emergency_game_seconds=2 * 60 * 60,
    )
    assert policy.stall_seconds == MIN_STALL_SECONDS
    assert policy.emergency_game_seconds == MIN_EMERGENCY_GAME_SECONDS


def test_compute_budget_expiry_never_times_out_an_active_game():
    now = FakeTime()
    clock = ComputeBudgetClock(10.0, now=now)
    policy = LiveGameWatchdogPolicy()
    league = LeaguePairScheduler(
        [ColorPairing("A", "champ", "challenger")],
        clock,
        parallel_games=2,
        hard_game_timeout_seconds=policy.emergency_game_seconds,
        stall_timeout_seconds=policy.stall_seconds,
    )
    started = league.poll_startable()
    assert {row.spec.game_id for row in started} == {"A:w", "A:b"}

    # Session budget expires while both games are still alive. This may request
    # drain, but it is not a watchdog condition and must not mark/kill either game.
    now.advance(11.0)
    trips = league.poll_watchdogs()
    assert trips == []
    assert league.draining is True
    assert {row.spec.game_id for row in league.active_games} == {"A:w", "A:b"}

    # Both games are allowed to finish naturally after the nominal run budget.
    league.complete("A:w", result="1-0")
    league.complete("A:b", result="0-1")
    assert league.safe_to_stop


def test_only_hour_long_no_progress_stall_trips_default_watchdog():
    now = FakeTime()
    clock = ComputeBudgetClock(100_000.0, now=now)
    policy = LiveGameWatchdogPolicy()
    league = LeaguePairScheduler(
        [ColorPairing("A", "champ", "challenger")],
        clock,
        parallel_games=2,
        hard_game_timeout_seconds=policy.emergency_game_seconds,
        stall_timeout_seconds=policy.stall_seconds,
    )
    league.poll_startable()
    league.report_progress("A:w", 10)

    now.advance(59 * 60)
    assert league.poll_watchdogs() == []
    now.advance(61)
    trips = league.poll_watchdogs()
    assert trips
    assert all(trip.reason == "no_move_progress_timeout" for trip in trips)
