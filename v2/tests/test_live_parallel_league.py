from queue import Empty, Queue

from dogmatist_v2.live_parallel_league import (
    LiveLeagueProcessPool,
    LiveLeagueWorkerResult,
    LiveLeagueWorkerTask,
    choose_live_league_parallelism,
    league_worker_threads,
)
from dogmatist_v2.runtime import ColorPairing


class FakeClock:
    def __init__(self):
        self.elapsed_seconds = 0.0
        self.expired = False


class FakeQueue:
    def __init__(self):
        self.q = Queue()

    def put(self, item):
        self.q.put(item)

    def get_nowait(self):
        try:
            return self.q.get_nowait()
        except Empty:
            raise

    def close(self):
        pass

    def join_thread(self):
        pass


class FakeProcess:
    _pid = 100

    def __init__(self, *, target, args, name, daemon):
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        FakeProcess._pid += 1
        self.pid = FakeProcess._pid
        self.exitcode = None
        self._alive = False

    def start(self):
        self._alive = True
        try:
            self.target(*self.args)
            self.exitcode = 0
        except Exception:
            self.exitcode = 1
            raise
        finally:
            self._alive = False

    def is_alive(self):
        return self._alive

    def terminate(self):
        self._alive = False
        self.exitcode = -15

    def kill(self):
        self._alive = False
        self.exitcode = -9

    def join(self, timeout=None):
        pass


class FakeContext:
    def Queue(self):
        return FakeQueue()

    def Process(self, **kwargs):
        return FakeProcess(**kwargs)


def _tasks(pairings):
    out = {}
    for pair in pairings:
        for spec in pair.games():
            out[spec.game_id] = LiveLeagueWorkerTask(
                game_id=spec.game_id,
                pairing_id=spec.pairing_id,
                leg=spec.leg,
                round_id=1,
                white_generation=int(spec.white_id),
                black_generation=int(spec.black_id),
                white_checkpoint="white.pt",
                black_checkpoint="black.pt",
                config={},
                start_fen="fen",
                opening_name=spec.opening or "unknown",
                depth=2,
                max_plies=50,
                seed=1,
                torch_threads=1,
            )
    return out


def _result(task):
    return LiveLeagueWorkerResult(
        game_id=task.game_id,
        pairing_id=task.pairing_id,
        leg=task.leg,
        white_generation=task.white_generation,
        black_generation=task.black_generation,
        opening_name=task.opening_name,
        result="1-0",
        termination="checkmate",
        pgn="",
        plies=20,
        metadata={},
        elapsed_s=1.0,
    )


def test_process_pool_executes_complete_colour_pairs():
    clock = FakeClock()
    pairings = [
        ColorPairing("a", "21", "15", "B20"),
        ColorPairing("b", "22", "15", "C50"),
    ]
    tasks = _tasks(pairings)

    def worker(task, queue):
        queue.put({"kind": "progress", "game_id": task.game_id, "plies": 7})
        queue.put({"kind": "finished", "game_id": task.game_id, "result": _result(task)})

    execution = LiveLeagueProcessPool(
        pairings,
        tasks,
        clock=clock,
        parallel_games=2,
        mp_context=FakeContext(),
        worker_target=worker,
        poll_interval_seconds=0.001,
    ).run()
    assert len(execution.results) == 4
    assert execution.failed_game_ids == ()
    assert execution.timed_out_game_ids == ()
    assert execution.draining is False


def test_budget_expiry_drains_reverse_leg_but_does_not_open_new_pair():
    clock = FakeClock()
    pairings = [
        ColorPairing("a", "21", "15", "B20"),
        ColorPairing("b", "22", "15", "C50"),
    ]
    tasks = _tasks(pairings)
    calls = []

    def worker(task, queue):
        calls.append(task.game_id)
        queue.put({"kind": "finished", "game_id": task.game_id, "result": _result(task)})
        if len(calls) == 1:
            clock.expired = True

    execution = LiveLeagueProcessPool(
        pairings,
        tasks,
        clock=clock,
        parallel_games=2,
        mp_context=FakeContext(),
        worker_target=worker,
        poll_interval_seconds=0.001,
    ).run()
    assert set(calls) == {"a:w", "a:b"}
    assert len(execution.results) == 2
    assert execution.draining is True
    assert execution.stop_reason == "compute_budget_exhausted"


def test_parallelism_uses_three_only_with_clear_headroom():
    class Runtime:
        config = {"runtime": {"torch_threads": 6}}
        _last_resource_budget = {
            "reason": "headroom available",
            "snapshot": {
                "cpu_count": 10,
                "load_percent": 40.0,
                "memory_percent": 60.0,
                "thermal_pressure": "nominal",
            },
        }

    runtime = Runtime()
    assert choose_live_league_parallelism(runtime) == 3
    assert league_worker_threads(runtime, 3) == 2
    runtime._last_resource_budget["snapshot"]["memory_percent"] = 80.0
    assert choose_live_league_parallelism(runtime) == 2
    assert league_worker_threads(runtime, 2) == 3


def test_worker_result_white_score():
    base = dict(
        game_id="g",
        pairing_id="p",
        leg=1,
        white_generation=1,
        black_generation=2,
        opening_name="B20",
        termination="normal",
        pgn="",
        plies=10,
        metadata={},
        elapsed_s=1.0,
    )
    assert LiveLeagueWorkerResult(result="1-0", **base).white_score == 1.0
    assert LiveLeagueWorkerResult(result="0-1", **base).white_score == 0.0
    assert LiveLeagueWorkerResult(result="1/2-1/2", **base).white_score == 0.5
