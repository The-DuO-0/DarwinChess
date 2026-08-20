from contextlib import contextmanager
from types import SimpleNamespace

from dogmatist_v2.live_cycle_override import LiveStrengthCycleOverride


class FakeRuntime:
    def __init__(self):
        self.events = []

    def selfplay(self, games=None):
        self.events.append(("selfplay", games))
        return ["g-a", "g-b"]

    def train_population(self, *, round_id, total_steps=None):
        self.events.append(("train", round_id, total_steps))
        return {"trained": True, "round_id": round_id}


class FakeCoordinator:
    def __init__(self, runtime, *, fail=False):
        self.runtime = runtime
        self.fail = fail
        self.pretraining_calls = []
        self.override_entries = 0

    def run_pretraining_stage(self, game_ids, **kwargs):
        self.pretraining_calls.append((tuple(game_ids), kwargs))
        if self.fail:
            raise RuntimeError("simulated Strength Lab adapter error")
        return SimpleNamespace(recipe="recipe-7", ui_payload=lambda: {"ok": True})

    @contextmanager
    def training_override(self, recipe, *, sampler=None):
        assert recipe == "recipe-7"
        self.override_entries += 1
        yield


def test_cycle_hook_captures_selfplay_then_wraps_unchanged_population_training():
    runtime = FakeRuntime()
    coordinator = FakeCoordinator(runtime)
    original_selfplay = runtime.selfplay.__func__
    original_train = runtime.train_population.__func__
    reports = []

    with LiveStrengthCycleOverride(
        coordinator,
        targeted_examples=48,
        teacher_request_cap=5,
        persist_teacher=True,
        report_callback=reports.append,
    ) as hook:
        assert runtime.selfplay(2) == ["g-a", "g-b"]
        result = runtime.train_population(round_id=7, total_steps=100)
        assert result["trained"] is True
        assert hook.latest_game_ids == ("g-a", "g-b")
        assert coordinator.override_entries == 1
        assert coordinator.pretraining_calls[0][0] == ("g-a", "g-b")
        kwargs = coordinator.pretraining_calls[0][1]
        assert kwargs["round_index"] == 7
        assert kwargs["targeted_examples"] == 48
        assert kwargs["teacher_request_cap"] == 5
        assert kwargs["persist_teacher"] is True
        assert len(reports) == 1

    assert runtime.selfplay.__func__ is original_selfplay
    assert runtime.train_population.__func__ is original_train


def test_cycle_hook_fails_open_to_original_training_path():
    runtime = FakeRuntime()
    coordinator = FakeCoordinator(runtime, fail=True)
    errors = []
    with LiveStrengthCycleOverride(coordinator, fail_open=True, error_callback=errors.append) as hook:
        runtime.selfplay()
        result = runtime.train_population(round_id=3, total_steps=40)
        assert result == {"trained": True, "round_id": 3}
        assert isinstance(hook.last_error, RuntimeError)
        assert len(errors) == 1
        assert coordinator.override_entries == 0
        assert ("train", 3, 40) in runtime.events


def test_cycle_hook_can_be_strict_for_mac_dry_run_validation():
    runtime = FakeRuntime()
    coordinator = FakeCoordinator(runtime, fail=True)
    try:
        with LiveStrengthCycleOverride(coordinator, fail_open=False):
            runtime.selfplay()
            runtime.train_population(round_id=1)
    except RuntimeError as exc:
        assert "simulated" in str(exc)
    else:
        raise AssertionError("strict dry-run mode must surface adapter failures")
