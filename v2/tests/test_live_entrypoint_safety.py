from pathlib import Path

import pytest

from dogmatist_v2.live_entrypoint import (
    LiveEvolutionOptions,
    _copy_validation_parallel_games,
    _copy_validation_runtime_overrides,
    run_live_evolution,
)


class FakeRuntime:
    def __init__(self, root):
        self.paths = {"root": Path(root)}
        self.config = {"runtime": {"league_parallel_games": 3}, "league": {}}
        self.memory = object()

    def evolve_cycle(self):
        return {"champion_before": 15, "champion_after": 15}


def test_copy_validation_temporarily_forces_two_league_workers_by_default(monkeypatch):
    monkeypatch.delenv("DOGMATIST_V2_COPY_LEAGUE_PARALLEL", raising=False)
    runtime = FakeRuntime("/tmp/example")
    assert runtime.config["runtime"]["league_parallel_games"] == 3
    with _copy_validation_runtime_overrides(runtime, True):
        assert runtime.config["runtime"]["league_parallel_games"] == 2
    assert runtime.config["runtime"]["league_parallel_games"] == 3


def test_copy_validation_can_explicitly_test_three_league_workers(monkeypatch):
    monkeypatch.setenv("DOGMATIST_V2_COPY_LEAGUE_PARALLEL", "3")
    runtime = FakeRuntime("/tmp/example")
    with _copy_validation_runtime_overrides(runtime, True):
        assert runtime.config["runtime"]["league_parallel_games"] == 3
    assert runtime.config["runtime"]["league_parallel_games"] == 3
    assert _copy_validation_parallel_games() == 3


def test_copy_validation_rejects_invalid_parallel_width(monkeypatch):
    monkeypatch.setenv("DOGMATIST_V2_COPY_LEAGUE_PARALLEL", "4")
    with pytest.raises(ValueError, match="must be 2 or 3"):
        _copy_validation_parallel_games()


def test_copy_validation_refuses_runtime_that_does_not_use_isolated_home(tmp_path, monkeypatch):
    isolated_home = tmp_path / "validation-home"
    expected = isolated_home / ".darwinchess"
    wrong = tmp_path / "some-other-state"
    wrong.mkdir()
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("DOGMATIST_V2_COPY_VALIDATION", "1")

    runtime = FakeRuntime(wrong)
    with pytest.raises(RuntimeError, match="state root does not match isolated HOME"):
        run_live_evolution(
            runtime,
            cycles=0,
            options=LiveEvolutionOptions(
                enable_parallel_league=False,
                enable_fixed_reference=False,
            ),
            progress=lambda _: None,
        )
    assert expected != wrong
