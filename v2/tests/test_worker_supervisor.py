from dogmatist_v2.runtime import WatchdogTrip
from dogmatist_v2.worker_supervisor import LeagueWorkerSupervisor


class FakeWorker:
    def __init__(self, *, survives_terminate=False):
        self.alive = True
        self.survives_terminate = survives_terminate
        self.terminate_calls = 0
        self.kill_calls = 0
        self.join_calls = []

    def terminate(self):
        self.terminate_calls += 1
        if not self.survives_terminate:
            self.alive = False

    def kill(self):
        self.kill_calls += 1
        self.alive = False

    def join(self, timeout=None):
        self.join_calls.append(timeout)

    def is_alive(self):
        return self.alive


def test_watchdog_terminates_worker_and_releases_slot():
    supervisor = LeagueWorkerSupervisor(terminate_grace_seconds=0.5)
    worker = FakeWorker()
    supervisor.register("A:w", worker)
    result = supervisor.enforce((WatchdogTrip("A:w", "no_move_progress_timeout", 30.0, 12),))
    assert result[0].game_id == "A:w"
    assert result[0].escalated_to_kill is False
    assert worker.terminate_calls == 1
    assert worker.kill_calls == 0
    assert not supervisor.has_worker("A:w")


def test_watchdog_escalates_to_kill_if_terminate_does_not_work():
    supervisor = LeagueWorkerSupervisor(terminate_grace_seconds=0.25)
    worker = FakeWorker(survives_terminate=True)
    supervisor.register("A:b", worker)
    result = supervisor.enforce((WatchdogTrip("A:b", "hard_game_timeout", 1200.0, 80),))
    assert result[0].escalated_to_kill is True
    assert worker.terminate_calls == 1
    assert worker.kill_calls == 1
    assert worker.alive is False


def test_normal_budget_drain_does_not_require_terminate_all():
    supervisor = LeagueWorkerSupervisor()
    worker = FakeWorker()
    supervisor.register("A:w", worker)
    supervisor.release("A:w")
    assert worker.terminate_calls == 0
    assert supervisor.terminate_all() == ()
