from datetime import datetime, timezone
from queue import Empty, Queue

from dogmatist_v2.fixed_reference import FixedReferenceEvaluator, FrozenReferenceManager
from dogmatist_v2.live_parallel_league import LiveLeagueWorkerResult


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
    _pid = 500

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


def test_reference_freeze_is_immutable_and_checksum_verified(tmp_path):
    source = tmp_path / "gen15.pt"
    source.write_bytes(b"gen15-frozen-weights")
    manager = FrozenReferenceManager(tmp_path / "reference")
    created = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    first = manager.freeze(source, generation=15, created_at=created)
    assert manager.verify(first)
    assert first.generation == 15
    assert first.checkpoint_path != str(source)

    # Mutating the live/source file does not move the frozen ruler.
    source.write_bytes(b"new-live-weights")
    second = manager.freeze(source, generation=99, created_at=created)
    assert second == first
    assert manager.verify(second)

    # Mutating the frozen copy itself is detected instead of silently accepted.
    from pathlib import Path
    Path(first.checkpoint_path).write_bytes(b"corrupted")
    assert manager.verify(first) is False


def test_fixed_reference_evaluator_scores_only_complete_colour_pairs(tmp_path):
    subject = tmp_path / "subject.pt"
    reference_source = tmp_path / "reference-source.pt"
    subject.write_bytes(b"subject")
    reference_source.write_bytes(b"reference")
    manager = FrozenReferenceManager(tmp_path / "frozen")
    reference = manager.freeze(
        reference_source,
        generation=15,
        created_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
    )

    def worker(task, queue):
        # The subject is generation 21. Make it win regardless of colour.
        result = "1-0" if task.white_generation == 21 else "0-1"
        row = LiveLeagueWorkerResult(
            game_id=task.game_id,
            pairing_id=task.pairing_id,
            leg=task.leg,
            white_generation=task.white_generation,
            black_generation=task.black_generation,
            opening_name=task.opening_name,
            result=result,
            termination="checkmate",
            pgn="",
            plies=20,
            metadata={},
            elapsed_s=1.0,
        )
        queue.put({"kind": "finished", "game_id": task.game_id, "result": row})

    evaluator = FixedReferenceEvaluator(
        clock=FakeClock(),
        parallel_games=2,
        mp_context=FakeContext(),
        worker_target=worker,
    )
    result = evaluator.evaluate(
        round_index=7,
        subject_generation=21,
        subject_checkpoint=str(subject),
        reference=reference,
        config={},
        openings=[("fen-a", "B20"), ("fen-b", "C50")],
        depth=2,
        max_plies=100,
    )
    assert result.games == 4
    assert result.complete_colour_pairs == 2
    assert result.wins == 4
    assert result.score == 1.0
    evidence = result.to_round_evidence(champion_generation=15, promoted=False)
    assert evidence.fixed_reference_score == 1.0
    assert evidence.paired_games == 4


def test_live_gen15_and_frozen_gen15_use_different_worker_identities(tmp_path):
    live = tmp_path / "live-gen15.pt"
    frozen_source = tmp_path / "frozen-gen15-source.pt"
    live.write_bytes(b"live-gen15-now")
    frozen_source.write_bytes(b"older-frozen-gen15")
    reference = FrozenReferenceManager(tmp_path / "ref").freeze(
        frozen_source,
        generation=15,
        created_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
    )
    seen = []

    def worker(task, queue):
        seen.append((task.white_generation, task.black_generation, task.white_checkpoint, task.black_checkpoint))
        row = LiveLeagueWorkerResult(
            game_id=task.game_id,
            pairing_id=task.pairing_id,
            leg=task.leg,
            white_generation=task.white_generation,
            black_generation=task.black_generation,
            opening_name=task.opening_name,
            result="1/2-1/2",
            termination="draw",
            pgn="",
            plies=12,
            metadata={},
            elapsed_s=1.0,
        )
        queue.put({"kind": "finished", "game_id": task.game_id, "result": row})

    result = FixedReferenceEvaluator(
        clock=FakeClock(),
        parallel_games=2,
        mp_context=FakeContext(),
        worker_target=worker,
    ).evaluate(
        round_index=8,
        subject_generation=15,
        subject_checkpoint=str(live),
        reference=reference,
        config={},
        openings=[("fen-a", "B20")],
        depth=2,
        max_plies=100,
    )

    assert result.games == 2
    assert result.score == 0.5
    assert len(seen) == 2
    assert all(white != black for white, black, *_ in seen)
    assert any(str(live) == white_cp for _, _, white_cp, _ in seen)
    assert any(reference.checkpoint_path == white_cp for _, _, white_cp, _ in seen)
