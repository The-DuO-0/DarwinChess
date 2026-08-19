from __future__ import annotations

from typing import Any

import chess

from .dialogue import DialogueAgent, explain_search
from .runtime import DarwinRuntime


class DarwinChessAgent:
    """Stable programmatic boundary for embedding DarwinChess in a larger agent.

    The outer agent does not need to know about PyTorch, SQLite, search, replay,
    or champion lineage. It can treat this as a persistent tool/skill.
    """

    def __init__(
        self,
        config_path: str | None = None,
        *,
        mode: str = "normal",
        device: str | None = None,
        search_device: str | None = None,
    ):
        self.runtime = DarwinRuntime(
            config_path,
            mode=mode,
            device=device,
            search_device=search_device,
        )
        self.dialogue = DialogueAgent(self.runtime)

    def close(self) -> None:
        self.runtime.close()

    def __enter__(self) -> "DarwinChessAgent":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def status(self) -> dict[str, Any]:
        return self.runtime.status()

    def best_move(self, fen: str, *, depth: int | None = None) -> dict[str, Any]:
        board = chess.Board(fen)
        result = self.runtime.analyze(fen, depth=depth, top_n=5)
        if result.move is None:
            return {
                "move_uci": None,
                "move_san": None,
                "score_cp": result.score_cp,
                "terminal": True,
                "explanation": explain_search(board, result),
            }
        return {
            "move_uci": result.move.uci(),
            "move_san": board.san(result.move),
            "score_cp": result.score_cp,
            "depth": result.depth,
            "nodes": result.nodes,
            "pv_uci": [m.uci() for m in result.pv],
            "candidates": [
                {"move_uci": c.move.uci(), "move_san": board.san(c.move), "score_cp": c.score_cp}
                for c in result.candidates
            ],
            "terminal": False,
            "explanation": explain_search(board, result),
        }

    def talk(self, message: str) -> str:
        return self.dialogue.answer(message)

    def chat(self, message: str) -> str:
        """Alias for outer agents that expose a chat-style tool name."""
        return self.talk(message)

    def evolve_once(self) -> dict[str, Any]:
        return self.runtime.evolve_cycle()

    def remember_status(self) -> dict[str, Any]:
        """Alias useful for tool-based outer agents that distinguish memory calls."""
        return self.runtime.status()
