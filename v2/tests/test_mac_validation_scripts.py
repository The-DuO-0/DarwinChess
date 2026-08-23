import importlib.util
from pathlib import Path
import sys

from dogmatist_v2.validation_telemetry import ValidationTelemetry


V2_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = V2_ROOT / "integration" / "production_overlay"


def _load(name, filename):
    path = OVERLAY / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def test_prepare_script_builds_dot_darwinchess_under_empty_validation_home(tmp_path):
    prepare = _load("dogmatist_prepare_validation", "prepare_mac_validation.py")
    live = tmp_path / "live" / ".darwinchess"
    home = tmp_path / "validation-home"
    source, destination = prepare.resolve_validation_paths(live, home)
    assert source == live.resolve()
    assert destination == (home / ".darwinchess").resolve()


def test_prepare_script_rejects_nonempty_validation_home(tmp_path):
    prepare = _load("dogmatist_prepare_validation_nonempty", "prepare_mac_validation.py")
    live = tmp_path / "live" / ".darwinchess"
    home = tmp_path / "validation-home"
    home.mkdir()
    (home / "unexpected.txt").write_text("x", encoding="utf-8")
    try:
        prepare.resolve_validation_paths(live, home)
    except FileExistsError:
        pass
    else:
        raise AssertionError("non-empty validation home should be rejected")


def test_validation_console_compacts_parallel_league_json():
    runmod = _load("dogmatist_run_validation_console", "run_copied_state.py")
    renderer = runmod.ValidationConsoleRenderer(interval_seconds=999.0)
    line = renderer.render({
        "phase": "league",
        "league": {
            "played": 0,
            "total": 8,
            "active_games": [
                {
                    "white_id": "58",
                    "black_id": "54",
                    "opening": "Reti",
                    "plies": 25,
                    "runtime_seconds": 81.2,
                },
                {
                    "white_id": "54",
                    "black_id": "58",
                    "opening": "Reti",
                    "plies": 67,
                    "runtime_seconds": 81.2,
                },
            ],
            "failed_games": [],
            "timed_out_games": [],
        },
    })
    assert line is not None
    assert "2 active" in line
    assert "G58W-G54B Reti ply25 01:21" in line
    assert "G54W-G58B Reti ply67 01:21" in line
    assert "DOGMATIST_UI" not in line


def test_validation_invariants_accept_explicit_three_worker_copy_run():
    runmod = _load("dogmatist_run_validation_invariants", "run_copied_state.py")
    telemetry = ValidationTelemetry(
        max_parallel_games=3,
        copy_validation={
            "enabled": True,
            "teacher_persistence": False,
            "league_parallel_games": 3,
        },
        watchdog={"budget_interrupts_games": False},
    )
    checks = runmod._validation_invariants(
        telemetry,
        expected_parallel_games=3,
        expect_budget_probe=False,
    )
    assert all(checks.values())


def test_validation_invariants_require_budget_probe_event_and_clean_finish():
    runmod = _load("dogmatist_run_validation_budget_probe", "run_copied_state.py")
    telemetry = ValidationTelemetry(
        max_parallel_games=2,
        copy_validation={
            "enabled": True,
            "teacher_persistence": False,
            "league_parallel_games": 2,
            "expire_on_league_start": True,
        },
        watchdog={"budget_interrupts_games": False},
        final_compute={"expired": True},
    )
    telemetry.phases["validation_budget_expired"] = 1
    checks = runmod._validation_invariants(
        telemetry,
        expected_parallel_games=2,
        expect_budget_probe=True,
    )
    assert all(checks.values())
