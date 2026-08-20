import json
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from dogmatist_v2.live_replay import LiveReplayMixSampler
from dogmatist_v2.live_runtime_overlay import LiveStrengthCoordinator
from dogmatist_v2.strength_store import HardPositionEvidence, StrengthStore


NOW = datetime(2026, 8, 20, 20, 0, tzinfo=timezone.utc)


class FakeMemory:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE games(
                id TEXT PRIMARY KEY,
                generation INTEGER,
                source TEXT,
                metadata_json TEXT
            );
            CREATE TABLE examples(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                ply INTEGER,
                fen TEXT,
                move_uci TEXT,
                played_move_uci TEXT,
                search_score_cp REAL,
                best_score_cp REAL,
                value_target REAL,
                policy_weight REAL,
                priority REAL,
                opening_name TEXT,
                origin_generation INTEGER
            );
            """
        )
        self.added_games = []
        self.insights = []
        self.replay_calls = []

    def seed_selfplay(self, game_id="g1", generation=15):
        self.conn.execute(
            "INSERT INTO games(id,generation,source,metadata_json) VALUES(?,?,?,?)",
            (game_id, generation, "selfplay", json.dumps({"opening_name": "B20"})),
        )
        for ply in range(10):
            losing = ply == 8
            self.conn.execute(
                """
                INSERT INTO examples(
                    game_id,ply,fen,move_uci,played_move_uci,search_score_cp,
                    best_score_cp,value_target,policy_weight,priority,opening_name,origin_generation
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    game_id,
                    ply,
                    f"fen-{ply}",
                    "e2e4",
                    "e2e4",
                    700.0 if losing else 20.0,
                    950.0 if losing else 30.0,
                    -1.0 if losing else 0.0,
                    1.0,
                    1.0,
                    "B20",
                    generation,
                ),
            )
        self.conn.commit()

    def active_specialists(self, limit=64):
        return []

    def replay_sample(
        self,
        batch_size,
        recent_fraction=0.35,
        *,
        opening_names=None,
        opening_fraction=0.0,
        generations=None,
    ):
        self.replay_calls.append((batch_size, recent_fraction, opening_names, opening_fraction, generations))
        return self.conn.execute(
            "SELECT * FROM examples ORDER BY id DESC LIMIT ?",
            (batch_size,),
        ).fetchall()

    def add_game(self, **kwargs):
        gid = f"teacher-{len(self.added_games) + 1}"
        self.added_games.append((gid, kwargs))
        return gid

    def add_insight(self, *args):
        self.insights.append(args)


class FakeMove:
    def __init__(self, text):
        self.text = text

    def uci(self):
        return self.text


@dataclass
class FakeSearchResult:
    move: FakeMove
    score_cp: float
    depth: int
    nodes: int
    elapsed_s: float


class FakeSearcher:
    def __init__(self):
        self.calls = 0

    def search(self, board, depth=None, time_limit_s=None, top_n=5):
        self.calls += 1
        if self.calls % 2:
            return FakeSearchResult(FakeMove("e2e4"), 80.0, depth or 0, 100, 0.05)
        return FakeSearchResult(FakeMove("d2d4"), 260.0, depth or 0, 900, 0.12)


class FakeRuntime:
    def __init__(self, memory):
        self.memory = memory
        self.config = {"search": {"depth": 2}}

    def champion_info(self):
        return {"id": 15}

    def make_searcher(self):
        return FakeSearcher()


def test_overlay_reconstructs_saved_live_game_and_mines_hard_positions(tmp_path):
    memory = FakeMemory()
    memory.seed_selfplay()
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        coordinator = LiveStrengthCoordinator(
            FakeRuntime(memory),
            store,
            board_factory=lambda fen: fen,
        )
        captured = coordinator.capture_saved_games(["g1"], round_index=4, observed_at=NOW)
        assert captured >= 1
        assert store.hard_position_count() >= 1
        sampled = store.sample_hard_positions(4)
        assert sampled[0].opening_bucket == "B20"
        assert sampled[0].source_generation == 15


def test_overlay_builds_recipe_and_writes_teacher_into_existing_replay_path(tmp_path):
    memory = FakeMemory()
    runtime = FakeRuntime(memory)
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        # Seed enough distinct hard positions so the planner has teacher work.
        for index in range(30):
            store.upsert_hard_position(
                HardPositionEvidence(
                    fen=f"fen-{index}",
                    opening_bucket="B20" if index % 2 == 0 else "C50",
                    source_generation=15,
                    source_kind="selfplay",
                    severity=1.0,
                    uncertainty=0.8,
                    value_error=0.9,
                    round_index=3,
                ),
                observed_at=NOW,
                max_per_bucket=64,
            )
        coordinator = LiveStrengthCoordinator(runtime, store, board_factory=lambda fen: fen)
        plan, recipe = coordinator.build_recipe(targeted_examples=20, hard_position_bucket_cap=20)
        assert recipe.teacher_requests
        teacher_count, game_ids = coordinator.execute_teacher_requests(
            recipe,
            generation=15,
            request_cap=2,
            searcher=FakeSearcher(),
        )
        assert teacher_count == 2
        assert len(game_ids) >= 1
        assert memory.added_games
        _, payload = memory.added_games[0]
        assert payload["source"] == "strength_teacher"
        assert payload["termination"] == "deep_search_self_teacher"
        assert payload["examples"][0].move_uci == "d2d4"
        assert payload["examples"][0].priority > 1.0
        assert memory.insights
        assert plan.mode.value == "normal"


def test_pretraining_stage_is_read_only_for_live_replay_by_default(tmp_path):
    memory = FakeMemory()
    memory.seed_selfplay()
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        coordinator = LiveStrengthCoordinator(FakeRuntime(memory), store, board_factory=lambda fen: fen)
        report = coordinator.run_pretraining_stage(
            ["g1"],
            round_index=5,
            observed_at=NOW,
            targeted_examples=12,
        )
        assert report.captured_positions >= 1
        assert report.teacher_examples == 0
        assert report.teacher_game_ids == ()
        assert memory.added_games == []


def test_coordinator_can_wrap_existing_trainer_replay_without_replacing_trainer(tmp_path):
    memory = FakeMemory()
    memory.seed_selfplay()
    runtime = FakeRuntime(memory)
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        coordinator = LiveStrengthCoordinator(runtime, store, board_factory=lambda fen: fen)
        coordinator.capture_saved_games(["g1"], round_index=6, observed_at=NOW)
        _, recipe = coordinator.build_recipe(targeted_examples=12, hard_position_bucket_cap=12)
        original = memory.replay_sample.__func__
        with coordinator.training_override(
            recipe,
            sampler=LiveReplayMixSampler(rng=random.Random(2)),
        ):
            # This is the exact shape ContinualTrainer uses in production.
            rows = memory.replay_sample(
                6,
                0.35,
                opening_names=["B20"],
                opening_fraction=0.65,
                generations=None,
            )
            assert rows
        assert memory.replay_sample.__func__ is original
