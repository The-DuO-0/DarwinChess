from __future__ import annotations

"""Isolated Mac smoke test for V2.1 OpenTree.

Run this file from the downloaded snapshot and pass the live project folder as
its only argument. It copies the project into a temporary directory, overlays
V2.1 there, and uses a temporary DARWINCHESS_HOME. Nothing is written into the
live source tree or ~/.darwinchess.
"""

import os
from pathlib import Path
import random
import shutil
import sys
import tempfile


def fail(msg: str) -> None:
    raise SystemExit(f"[V2.1 smoke] FAIL: {msg}")


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: python SMOKE_V21_OPENTREE.py /path/to/dog_matist-2.0")
    source_root = Path(sys.argv[1]).expanduser().resolve()
    overlay_root = Path(__file__).resolve().parent
    if not (source_root / "darwinchess" / "runtime.py").exists():
        fail(f"not a dog_matist project: {source_root}")
    if not (overlay_root / "darwinchess" / "opening_tree.py").exists():
        fail("snapshot is incomplete")

    with tempfile.TemporaryDirectory(prefix="dogmatist-v21-") as td:
        td = Path(td)
        project = td / "project"
        shutil.copytree(source_root / "darwinchess", project / "darwinchess")
        shutil.copytree(source_root / "configs", project / "configs")
        for file in (overlay_root / "darwinchess").glob("*.py"):
            shutil.copy2(file, project / "darwinchess" / file.name)
        shutil.copy2(overlay_root / "configs" / "default.yaml", project / "configs" / "default.yaml")

        os.environ["DARWINCHESS_HOME"] = str(td / "state")
        sys.path.insert(0, str(project))

        import chess
        from darwinchess.opening_tree import OpeningTreeManager
        from darwinchess.runtime import DarwinRuntime
        from darwinchess.selfplay import play_game

        rt = DarwinRuntime(mode="eco")
        tree = OpeningTreeManager(rt.memory, rt.config)
        generation = int(rt.champion_info()["id"])
        searcher = rt.make_searcher()

        print("[V2.1 smoke] phase 1/3: natural game builds tree", flush=True)
        natural = play_game(
            searcher, searcher, rt.config,
            white_name="v21-natural", black_name="v21-natural",
            stochastic=True, seed=99173, depth=1, max_plies=12,
            starting_board=chess.Board(), opening_name="Natural root",
            opening_family="tree", opening_source="natural", tree_start_ply=0,
        )
        gid = rt.memory.add_game(
            source="selfplay", generation=generation,
            white_agent="v21-natural", black_agent="v21-natural",
            result=natural.result, termination=natural.termination, pgn=natural.pgn,
            plies=natural.plies, examples=natural.examples, metadata=natural.metadata,
        )
        updates = tree.observe_record(natural, generation=generation, game_id=gid)
        stats1 = rt.memory.opening_tree_stats()
        if updates <= 0 or stats1["edges"] <= 0:
            fail(f"natural game did not create tree edges: updates={updates}, stats={stats1}")

        print(f"[V2.1 smoke] tree after natural: {stats1}", flush=True)
        print("[V2.1 smoke] phase 2/3: choose a dog-discovered unplayed frontier", flush=True)
        frontier = tree._sample_frontier(random.Random(314159), unplayed_only=True)
        if frontier is None or not frontier.forced_move_uci:
            fail("no unplayed frontier was discovered from the natural search traces")
        print(
            f"[V2.1 smoke] frontier parent={frontier.branch_key.hex()[:8] if frontier.branch_key else 'none'} "
            f"move={frontier.forced_move_uci} ply={frontier.start_ply}", flush=True,
        )

        print("[V2.1 smoke] phase 3/3: revisit frontier and consume the branch", flush=True)
        start_board = chess.Board(frontier.fen)
        explored = play_game(
            searcher, searcher, rt.config,
            white_name="v21-frontier", black_name="v21-frontier",
            stochastic=True, seed=271828, depth=1, max_plies=10,
            starting_board=start_board, opening_name=frontier.label,
            opening_family="tree", opening_source="frontier",
            forced_first_move_uci=frontier.forced_move_uci,
            tree_start_ply=frontier.start_ply,
        )
        if not explored.opening_traces:
            fail("frontier game produced no opening trace")
        if explored.opening_traces[0].played_move_uci != frontier.forced_move_uci:
            fail(
                "current-search safety guard rejected the selected frontier move; "
                "this can happen if the stored frontier is stale, but should not happen immediately in smoke"
            )
        gid2 = rt.memory.add_game(
            source="selfplay", generation=generation,
            white_agent="v21-frontier", black_agent="v21-frontier",
            result=explored.result, termination=explored.termination, pgn=explored.pgn,
            plies=explored.plies, examples=explored.examples, metadata=explored.metadata,
        )
        tree.observe_record(explored, generation=generation, game_id=gid2)
        strict_holdout = rt.memory.opening_frontier_edges(
            max_ply=tree.max_plies - 1, max_visits=0,
            max_gap_cp=tree.frontier_gap_cp, limit=tree.frontier_query_limit,
        )
        stats2 = rt.memory.opening_tree_stats()
        print(f"[V2.1 smoke] tree after frontier: {stats2}", flush=True)
        print(f"[V2.1 smoke] remaining unplayed holdout candidates: {len(strict_holdout)}", flush=True)
        print("[V2.1 smoke] PASS: natural -> discovery -> frontier exploration works in isolated state", flush=True)


if __name__ == "__main__":
    main()
