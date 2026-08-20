from types import SimpleNamespace

from dogmatist_v2.live_compute import HeartbeatComputeClock
from dogmatist_v2.live_runner import LiveEvolutionRunner


class FakeTime:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class DummyPopulationArena:
    pass


class FakeMemory:
    def update_generation(self, *args, **kwargs):
        pass

    def add_insight(self, *args, **kwargs):
        pass


class FakeRuntime:
    def __init__(self, now):
        self.now = now
        self.memory = FakeMemory()
        self.cycles = 0

    def champion_info(self):
        return {"id": 15}

    def gate_challenger(self, challenger_id, challenger, *, games=None):
        return None

    def _harvest_specialist_experience(self, *args, **kwargs):
        return 0

    def evolve_cycle(self):
        self.cycles += 1
        self.now.advance(5.0)
        return {"cycle": self.cycles, "champion_before": 15, "champion_after": 15}


def _clock(now, budget):
    return HeartbeatComputeClock(
        budget,
        now=now,
        heartbeat_interval_seconds=1.0,
        suspension_threshold_seconds=10.0,
    )


def test_runner_stops_on_active_compute_budget_instead_of_production_wall_deadline():
    now = FakeTime()
    runtime = FakeRuntime(now)
    module = SimpleNamespace(PopulationArena=DummyPopulationArena)
    messages = []
    runner = LiveEvolutionRunner(runtime, _clock(now, 10.0), runtime_module=module)
    report = runner.run(progress=messages.append)
    assert report.cycles_completed == 2
    assert runtime.cycles == 2
    assert report.stop_reason == "compute_budget_exhausted"
    assert report.compute["elapsed_seconds"] == 10.0
    assert report.cycles[-1]["live_v2"]["compute"]["expired"] is True
    assert messages


def test_runner_honors_explicit_cycle_limit_before_compute_budget():
    now = FakeTime()
    runtime = FakeRuntime(now)
    module = SimpleNamespace(PopulationArena=DummyPopulationArena)
    report = LiveEvolutionRunner(runtime, _clock(now, 100.0), runtime_module=module).run(
        cycles=1,
        progress=lambda _: None,
    )
    assert report.cycles_completed == 1
    assert report.stop_reason == "cycles_complete"
    assert report.compute["remaining_seconds"] == 95.0
