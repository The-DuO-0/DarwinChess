from dataclasses import dataclass
from datetime import datetime, timezone

from dogmatist_v2.live_bridge import AlphaBetaTeacherAdapter, LiveGameEvidenceBridge
from dogmatist_v2.strength_pipeline import DeepSearchTeacherRequest
from dogmatist_v2.strength_store import StrengthStore


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


@dataclass
class FakeExample:
    fen: str
    value_target: float
    search_score_cp: float | None
    best_score_cp: float | None


@dataclass
class FakeRecord:
    examples: list[FakeExample]
    metadata: dict


class FakeMove:
    def __init__(self, text: str):
        self.text = text

    def uci(self):
        return self.text


@dataclass
class FakeSearchResult:
    move: FakeMove | None
    score_cp: float
    depth: int
    nodes: int
    elapsed_s: float


class FakeSearcher:
    def __init__(self):
        self.calls = []

    def search(self, board, depth=None, time_limit_s=None, top_n=5):
        self.calls.append((board, depth, time_limit_s, top_n))
        if len(self.calls) == 1:
            return FakeSearchResult(FakeMove("e2e4"), 100.0, depth or 0, 100, 0.10)
        return FakeSearchResult(FakeMove("d2d4"), 260.0, depth or 0, 900, 0.25)


def test_live_game_bridge_mines_current_replay_fields_without_schema_change(tmp_path):
    record = FakeRecord(
        examples=[
            FakeExample(f"fen-{i}", -1.0 if i == 8 else 0.0, 700.0 if i == 8 else 20.0, 950.0 if i == 8 else 30.0)
            for i in range(12)
        ],
        metadata={"opening_name": "B20"},
    )
    with StrengthStore(tmp_path / "strength.sqlite3") as store:
        bridge = LiveGameEvidenceBridge(store, skip_opening_plies=6, max_positions_per_game=4)
        rows = bridge.candidates_from_record(record, generation=15, round_index=9)
        assert rows
        assert rows[0].evidence.fen == "fen-8"
        assert rows[0].evidence.opening_bucket == "B20"
        assert rows[0].evidence.value_error > 0.8
        stored = bridge.persist_record(
            record,
            generation=15,
            round_index=9,
            observed_at=NOW,
        )
        assert stored >= 1
        assert store.hard_position_count() >= 1


def test_alpha_beta_teacher_uses_time_cap_not_depth_multiplication():
    request = DeepSearchTeacherRequest(
        position_key="p1",
        fen="start-fen",
        opening_bucket="B20",
        search_multiplier=3.0,
        source_generation=15,
    )
    searcher = FakeSearcher()
    adapter = AlphaBetaTeacherAdapter(maximum_teacher_time_s=2.0)
    result = adapter.execute(
        request,
        searcher=searcher,
        board_factory=lambda fen: fen,
        base_depth=2,
    )
    assert result is not None
    assert result.move_uci == "d2d4"
    assert result.value_target > 0
    assert len(searcher.calls) == 2
    _, baseline_depth, baseline_limit, _ = searcher.calls[0]
    _, teacher_depth, teacher_limit, _ = searcher.calls[1]
    assert baseline_depth == 2
    assert baseline_limit is None
    assert teacher_depth == 3
    assert 0.29 <= teacher_limit <= 0.31
