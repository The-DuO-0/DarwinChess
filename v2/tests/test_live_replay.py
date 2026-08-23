import random
import sqlite3

from dogmatist_v2.live_replay import LiveReplayMixSampler, LiveReplayOverride
from dogmatist_v2.strength_lab import TrainingBatchBudget
from dogmatist_v2.strength_pipeline import DeepSearchTeacherRequest, StrengthRoundRecipe
from dogmatist_v2.strength_store import HardPositionEvidence


class FakeMemory:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE games(id TEXT PRIMARY KEY, source TEXT);
            CREATE TABLE examples(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                fen TEXT,
                priority REAL,
                opening_name TEXT,
                origin_generation INTEGER,
                tag TEXT
            );
            """
        )
        self.replay_calls = []

    def add_example(self, *, game_id, source, fen, tag, opening_name=None, origin_generation=None, priority=1.0):
        self.conn.execute("INSERT OR IGNORE INTO games(id,source) VALUES(?,?)", (game_id, source))
        self.conn.execute(
            "INSERT INTO examples(game_id,fen,priority,opening_name,origin_generation,tag) VALUES(?,?,?,?,?,?)",
            (game_id, fen, priority, opening_name, origin_generation, tag),
        )
        self.conn.commit()

    def active_specialists(self, limit=64):
        return [{"generation": 31, "opening_name": "B20"}]

    def replay_sample(
        self,
        batch_size,
        recent_fraction=0.35,
        *,
        opening_names=None,
        opening_fraction=0.0,
        generations=None,
    ):
        self.replay_calls.append(
            {
                "batch_size": batch_size,
                "recent_fraction": recent_fraction,
                "opening_names": opening_names,
                "opening_fraction": opening_fraction,
                "generations": generations,
            }
        )
        query = "SELECT * FROM examples"
        params = []
        if opening_names:
            placeholders = ",".join("?" for _ in opening_names)
            query += f" WHERE opening_name IN ({placeholders})"
            params.extend(opening_names)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(batch_size)
        return self.conn.execute(query, params).fetchall()


def _recipe():
    hard = (
        HardPositionEvidence("hard-1", "H", 15, "selfplay", 1.0, 0.8, 0.8, 1),
        HardPositionEvidence("hard-2", "H", 15, "selfplay", 1.0, 0.8, 0.8, 1),
    )
    teacher = (
        DeepSearchTeacherRequest("t1", "teacher-seed-1", "T", 2.0, 15),
        DeepSearchTeacherRequest("t2", "teacher-seed-2", "T", 2.0, 15),
    )
    return StrengthRoundRecipe(
        requested=TrainingBatchBudget(2, 2, 2, 2),
        natural_selfplay_examples=2,
        hard_positions=hard,
        specialist_examples=2,
        teacher_requests=teacher,
        backfilled_examples=0,
    )


def test_sampler_selects_all_live_strength_sources_without_duplication():
    memory = FakeMemory()
    memory.add_example(game_id="h1", source="selfplay", fen="hard-1", tag="hard", priority=3.0)
    memory.add_example(game_id="h2", source="selfplay", fen="hard-2", tag="hard", priority=3.0)
    memory.add_example(game_id="s1", source="league", fen="spec-1", tag="specialist", opening_name="B20", origin_generation=31)
    memory.add_example(game_id="s2", source="league", fen="spec-2", tag="specialist", opening_name="B20", origin_generation=31)
    memory.add_example(game_id="t1", source="strength_teacher", fen="teach-1", tag="teacher")
    memory.add_example(game_id="t2", source="strength_teacher", fen="teach-2", tag="teacher")
    for index in range(6):
        memory.add_example(game_id=f"n{index}", source="selfplay", fen=f"normal-{index}", tag="natural")

    sampler = LiveReplayMixSampler(rng=random.Random(7))
    rows = sampler.sample(memory, _recipe(), batch_size=8, recent_fraction=0.35)
    assert len(rows) == 8
    assert len({int(row["id"]) for row in rows}) == 8
    tags = [row["tag"] for row in rows]
    assert tags.count("hard") >= 2
    assert tags.count("specialist") >= 2
    assert tags.count("teacher") >= 2


def test_sampler_backfills_missing_targeted_rows_with_ordinary_replay():
    memory = FakeMemory()
    memory.add_example(game_id="h1", source="selfplay", fen="hard-1", tag="hard")
    for index in range(12):
        memory.add_example(game_id=f"n{index}", source="selfplay", fen=f"normal-{index}", tag="natural")

    rows = LiveReplayMixSampler(rng=random.Random(1)).sample(
        memory,
        _recipe(),
        batch_size=8,
        recent_fraction=0.35,
    )
    assert len(rows) == 8
    assert len({int(row["id"]) for row in rows}) == 8
    assert any(row["tag"] == "hard" for row in rows)
    assert sum(row["tag"] == "natural" for row in rows) >= 6


def test_scaled_quota_is_exact_for_any_training_batch_size():
    sampler = LiveReplayMixSampler(rng=random.Random(0))
    for size in (1, 7, 128, 129):
        quota = sampler.quota_for(_recipe(), size)
        assert quota.total == size


def test_override_preserves_trainer_focus_kwargs_and_restores_original_method():
    memory = FakeMemory()
    # B20 rows can satisfy specialist + ordinary focus. Hard/teacher recipe rows
    # intentionally use other buckets, so they must not leak into this branch.
    for index in range(12):
        memory.add_example(
            game_id=f"b{index}",
            source="selfplay",
            fen=f"b20-{index}",
            tag="b20",
            opening_name="B20",
            origin_generation=31 if index < 3 else 15,
        )
    memory.add_example(game_id="h1", source="selfplay", fen="hard-1", tag="hard", opening_name="H")
    memory.add_example(game_id="t1", source="strength_teacher", fen="teach-1", tag="teacher", opening_name="T")

    original_func = memory.replay_sample.__func__
    with LiveReplayOverride(
        memory,
        _recipe(),
        sampler=LiveReplayMixSampler(rng=random.Random(4)),
    ):
        rows = memory.replay_sample(
            8,
            0.42,
            opening_names=["B20"],
            opening_fraction=0.75,
            generations=[31],
        )
        assert len(rows) == 8
        assert all(row["opening_name"] == "B20" for row in rows)
        assert memory.replay_calls
        delegated = memory.replay_calls[-1]
        assert delegated["recent_fraction"] == 0.42
        assert delegated["opening_names"] == ["B20"]
        assert delegated["opening_fraction"] == 0.75
        assert delegated["generations"] == [31]

    assert memory.replay_sample.__func__ is original_func


def test_override_restores_original_method_after_training_exception():
    memory = FakeMemory()
    memory.add_example(game_id="n1", source="selfplay", fen="normal", tag="natural")
    original_func = memory.replay_sample.__func__
    try:
        with LiveReplayOverride(memory, _recipe()):
            raise RuntimeError("simulated trainer failure")
    except RuntimeError:
        pass
    assert memory.replay_sample.__func__ is original_func
