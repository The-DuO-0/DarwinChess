from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math

import chess
import torch

from .evaluator import HybridEvaluator
from .genome import AgentGenome
from .memory import MemoryStore
from .network import ChessNet
from .opening_curriculum import OpeningCurriculum
from .search import AlphaBetaSearcher
from .selfplay import play_game


@dataclass
class ArenaResult:
    games: int
    wins: int
    draws: int
    losses: int
    score: float
    wilson_lower: float
    promoted: bool


class Arena:
    def __init__(self, config: dict[str, Any], memory: MemoryStore, device: torch.device):
        self.config = config
        self.memory = memory
        self.device = device

    def compare(
        self,
        challenger: ChessNet,
        champion: ChessNet,
        *,
        challenger_generation: int,
        champion_generation: int,
        challenger_genome: AgentGenome,
        champion_genome: AgentGenome,
        games: int | None = None,
    ) -> ArenaResult:
        acfg = self.config["arena"]
        games = int(games or acfg["games"])
        depth = int(acfg.get("depth", self.config["search"]["depth"]))
        max_plies = int(acfg.get("max_game_plies", 220))
        threshold = float(acfg.get("promotion_score", 0.55))
        wilson_z = float(acfg.get("promotion_wilson_z", 1.2816))

        challenger.eval()
        champion.eval()
        ce = HybridEvaluator(challenger, self.config, self.device, challenger_genome)
        pe = HybridEvaluator(champion, self.config, self.device, champion_genome)
        cs = AlphaBetaSearcher(ce, self.config)
        ps = AlphaBetaSearcher(pe, self.config)

        seed = int(self.config["project"].get("seed", 0)) + challenger_generation * 1009 + champion_generation
        curriculum = OpeningCurriculum(seed=seed)
        pairs = curriculum.arena_pairs((games + 1) // 2)

        wins = draws = losses = 0
        played = 0
        for pair_index, (start_board, opening_name) in enumerate(pairs):
            for challenger_white in (True, False):
                if played >= games:
                    break
                i = played
                if challenger_white:
                    record = play_game(
                        cs, ps, self.config,
                        white_name=f"challenger-g{challenger_generation}",
                        black_name=f"champion-g{champion_generation}",
                        stochastic=False,
                        seed=100000 + i,
                        depth=depth,
                        max_plies=max_plies,
                        starting_board=start_board,
                        opening_name=opening_name,
                        opening_family="arena",
                    )
                    if record.winner is chess.WHITE:
                        r = 1.0
                    elif record.winner is None:
                        r = 0.5
                    else:
                        r = 0.0
                    color = "white"
                else:
                    record = play_game(
                        ps, cs, self.config,
                        white_name=f"champion-g{champion_generation}",
                        black_name=f"challenger-g{challenger_generation}",
                        stochastic=False,
                        seed=100000 + i,
                        depth=depth,
                        max_plies=max_plies,
                        starting_board=start_board,
                        opening_name=opening_name,
                        opening_family="arena",
                    )
                    if record.winner is chess.BLACK:
                        r = 1.0
                    elif record.winner is None:
                        r = 0.5
                    else:
                        r = 0.0
                    color = "black"

                if r == 1.0:
                    wins += 1
                elif r == 0.5:
                    draws += 1
                else:
                    losses += 1

                metadata = dict(record.metadata)
                metadata.update({
                    "arena_pair": pair_index,
                    "opening_name": opening_name,
                    "paired_colors": True,
                })
                gid = self.memory.add_game(
                    source="arena",
                    generation=challenger_generation,
                    white_agent=f"challenger-g{challenger_generation}" if challenger_white else f"champion-g{champion_generation}",
                    black_agent=f"champion-g{champion_generation}" if challenger_white else f"challenger-g{challenger_generation}",
                    result=record.result,
                    termination=record.termination,
                    pgn=record.pgn,
                    plies=record.plies,
                    examples=[],
                    metadata=metadata,
                )
                self.memory.add_arena_match(challenger_generation, champion_generation, gid, color, r)
                played += 1

        score = (wins + 0.5 * draws) / max(1, played)
        n = max(1, played)
        z2 = wilson_z * wilson_z
        denom = 1.0 + z2 / n
        center = (score + z2 / (2.0 * n)) / denom
        margin = wilson_z * math.sqrt(score * (1.0 - score) / n + z2 / (4.0 * n * n)) / denom
        wilson_lower = max(0.0, center - margin)
        promoted = score >= threshold and wilson_lower > 0.5
        return ArenaResult(played, wins, draws, losses, score, wilson_lower, promoted)
