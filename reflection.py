from __future__ import annotations

from collections import Counter
from typing import Any
import io

import chess.pgn

from .memory import MemoryStore


class ReflectionEngine:
    """Turns durable game statistics into durable, inspectable natural-language insights."""

    def __init__(self, memory: MemoryStore):
        self.memory = memory

    @staticmethod
    def _opening_prefix(pgn_text: str, plies: int = 4) -> str:
        try:
            game = chess.pgn.read_game(io.StringIO(pgn_text))
            if game is None:
                return "unknown"
            board = game.board()
            sans: list[str] = []
            for i, move in enumerate(game.mainline_moves()):
                if i >= plies:
                    break
                sans.append(board.san(move))
                board.push(move)
            return " ".join(sans) or "unknown"
        except Exception:
            return "unknown"

    def reflect_recent(self, generation: int | None, limit: int = 50) -> list[str]:
        games = [r for r in self.memory.recent_games(limit) if r["source"] == "selfplay"]
        if not games:
            return []
        decisive = sum(1 for g in games if g["result"] != "1/2-1/2")
        avg_plies = sum(int(g["plies"]) for g in games) / len(games)
        openings = Counter(self._opening_prefix(g["pgn"]) for g in games)
        top_opening, top_count = openings.most_common(1)[0]
        results = Counter(g["result"] for g in games)
        texts = [
            f"最近 {len(games)} 盘自我对弈中，{decisive} 盘分出胜负，平均 {avg_plies:.1f} 个半回合。",
            f"最近最常出现的开局序列是 {top_opening}，出现 {top_count}/{len(games)} 次。",
            f"最近结果分布：白胜 {results['1-0']}，黑胜 {results['0-1']}，和棋 {results['1/2-1/2']}。",
        ]
        for text in texts:
            self.memory.add_insight(generation, "selfplay_summary", text, {"window": len(games)})
        return texts
