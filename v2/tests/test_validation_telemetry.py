import json

from dogmatist_v2.validation_telemetry import ValidationTelemetry


def _line(payload):
    return "DOGMATIST_UI " + json.dumps(payload)


def test_validation_telemetry_tracks_budget_policy_league_and_reference():
    telemetry = ValidationTelemetry()
    assert telemetry.feed_line("ordinary log line") is False
    assert telemetry.feed_line(_line({
        "phase": "copy_validation",
        "copy_validation": {
            "enabled": True,
            "teacher_persistence": False,
            "league_parallel_games": 2,
        },
    }))
    telemetry.feed_line(_line({
        "phase": "watchdog_policy",
        "watchdog": {
            "budget_interrupts_games": False,
            "stall_seconds": 1800,
            "emergency_game_seconds": 7200,
        },
    }))
    telemetry.feed_line(_line({
        "phase": "league",
        "league": {
            "parallel_games": 2,
            "active_games": [
                {"game_id": "a:w", "runtime_seconds": 12.0},
                {"game_id": "a:b", "runtime_seconds": 9.0},
            ],
            "failed_games": [],
            "timed_out_games": [],
        },
    }))
    telemetry.feed_line(_line({
        "phase": "fixed_reference",
        "fixed_reference": {
            "subject_generation": 21,
            "active": {
                "parallel_games": 2,
                "active_games": [{"game_id": "ref:w", "runtime_seconds": 20.0}],
            },
        },
    }))
    telemetry.feed_line(_line({
        "phase": "cycle_complete",
        "compute": {"elapsed_seconds": 100.0, "expired": False},
        "fixed_reference": {
            "subject_generation": 21,
            "result": {"score": 0.625, "games": 4},
        },
    }))

    summary = telemetry.as_dict()
    assert summary["max_parallel_games"] == 2
    assert summary["max_live_games"] == 2
    assert summary["watchdog"]["budget_interrupts_games"] is False
    assert summary["copy_validation"]["teacher_persistence"] is False
    assert summary["fixed_reference"]["result"]["games"] == 4
    assert summary["final_compute"]["elapsed_seconds"] == 100.0
    assert summary["longest_observed_games"][0]["game_id"] == "ref:w"


def test_validation_telemetry_surfaces_watchdog_trips():
    telemetry = ValidationTelemetry()
    telemetry.feed_event({
        "phase": "league",
        "league": {
            "parallel_games": 2,
            "active_games": [],
            "failed_games": ["x:b"],
            "timed_out_games": ["x:w"],
        },
    })
    assert telemetry.failed_games == {"x:b"}
    assert telemetry.timed_out_games == {"x:w"}
