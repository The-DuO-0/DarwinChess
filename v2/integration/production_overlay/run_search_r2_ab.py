from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from dataclasses import dataclass

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state


@dataclass
class SearchMeter:
    calls: int = 0
    nodes: int = 0
    elapsed_s: float = 0.0
    opening_stabilized: int = 0
    opening_extra_nodes: int = 0

    def add(self, result) -> None:
        self.calls += 1
        self.nodes += int(getattr(result, "nodes", 0) or 0)
        self.elapsed_s += float(getattr(result, "elapsed_s", 0.0) or 0.0)
        if bool(getattr(result, "opening_stabilized", False)):
            self.opening_stabilized += 1
        self.opening_extra_nodes += int(getattr(result, "opening_extra_nodes", 0) or 0)

    def merge(self, other: "SearchMeter") -> None:
        self.calls += other.calls
        self.nodes += other.nodes
        self.elapsed_s += other.elapsed_s
        self.opening_stabilized += other.opening_stabilized
        self.opening_extra_nodes += other.opening_extra_nodes

    def as_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "nodes": self.nodes,
            "elapsed_s": self.elapsed_s,
            "opening_stabilized": self.opening_stabilized,
            "opening_extra_nodes": self.opening_extra_nodes,
        }


class MeteredSearcher:
    def __init__(self, inner, meter: SearchMeter):
        self.inner = inner
        self.meter = meter

    def search(self, *args, **kwargs):
        result = self.inner.search(*args, **kwargs)
        self.meter.add(result)
        return result


def _analysis_env(snapshot_state: Path) -> None:
    home = snapshot_state.parent
    os.environ.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_CACHE_HOME=str(home / ".cache"),
        PYTHONNOUSERSITE="1",
        DOGMATIST_V2_COPY_VALIDATION="1",
    )


def _candidate_config(base: dict, *, enabled: bool) -> dict:
    cfg = copy.deepcopy(base)
    cfg.setdefault("search", {})["opening_stabilization"] = {
        "enabled": bool(enabled),
        "revision_id": "search-r2-opening-stabilization",
        "opening_plies": 8,
        "always_verify_plies": 4,
        "extra_depth": 1,
        "candidate_margin_cp": 25.0,
        "iteration_swing_cp": 60.0,
        "max_extra_searches": 6,
    }
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Paired frozen-weight A/B smoke/gate for search-r1 versus the candidate "
            "search-r2 opening stabilization revision. No model training or DB writes."
        )
    )
    parser.add_argument("source_copy")
    parser.add_argument("snapshot_state")
    parser.add_argument("--generation", type=int, default=54)
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument("--pairs", type=int, default=2, help="paired color openings; 2 pairs = 4 games")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-plies", type=int, default=180)
    parser.add_argument("--seed", type=int, default=20260822)
    args = parser.parse_args(argv)

    if args.pairs <= 0:
        parser.error("--pairs must be positive")
    if args.depth <= 0:
        parser.error("--depth must be positive")
    if args.max_plies <= 0:
        parser.error("--max-plies must be positive")

    source = Path(args.source_copy).expanduser().resolve()
    snapshot = Path(args.snapshot_state).expanduser().resolve()
    preflight = validate_copied_state(snapshot, include_spawn_probe=False)
    if not preflight.ok:
        print(json.dumps({"preflight": preflight.as_dict()}, ensure_ascii=False, indent=2))
        print("STOP: copied-state preflight failed.")
        return 2

    manifest = load_snapshot_manifest(snapshot)
    snapshot_champion = int(manifest.champion_generation) if manifest.champion_generation is not None else None
    if snapshot_champion != int(args.generation):
        raise RuntimeError(
            f"search-r2 A/B refused: snapshot manifest champion is Gen{snapshot_champion}, "
            f"requested Gen{args.generation}"
        )

    if not (source / "darwinchess" / "search.py").is_file():
        raise FileNotFoundError(f"copied production search.py not found under {source}")

    # Import the copied production package, not an unrelated installed build.
    sys.path.insert(0, str(source))
    _analysis_env(snapshot)

    import chess
    from darwinchess.evaluator import HybridEvaluator
    from darwinchess.opening_curriculum import OpeningCurriculum
    from darwinchess.runtime import DarwinRuntime
    from darwinchess.search import AlphaBetaSearcher
    from darwinchess.selfplay import play_game

    with DarwinRuntime(mode=args.mode, apply_nice=False) as rt:
        live_copy_champion = int(rt.champion_info()["id"])
        if live_copy_champion != int(args.generation):
            raise RuntimeError(
                f"search-r2 A/B refused: copied DB champion is Gen{live_copy_champion}, "
                f"requested Gen{args.generation}. Rebuild a clean frozen snapshot first."
            )
        model, payload = rt.load_champion(rt.search_device)
        genome = rt.genome_from_payload(payload)
        base_config = copy.deepcopy(rt.config)
        device = rt.search_device

    baseline_cfg = _candidate_config(base_config, enabled=False)
    candidate_cfg = _candidate_config(base_config, enabled=True)

    def make_searcher(enabled: bool, meter: SearchMeter):
        cfg = candidate_cfg if enabled else baseline_cfg
        evaluator = HybridEvaluator(model, cfg, device, genome)
        return MeteredSearcher(AlphaBetaSearcher(evaluator, cfg), meter)

    curriculum = OpeningCurriculum(seed=int(args.seed))
    starts: list[tuple[chess.Board, str]] = [(chess.Board(), "Initial position")]
    if args.pairs > 1:
        starts.extend(curriculum.arena_pairs(args.pairs - 1))

    wins = draws = losses = 0
    baseline_meter = SearchMeter()
    candidate_meter = SearchMeter()
    game_rows: list[dict[str, object]] = []

    print(
        f"[search-r2-ab] Frozen Gen{args.generation}; search-r1 depth={args.depth} vs "
        f"search-r2 opening-only +1; pairs={args.pairs}; book moves OFF"
    )

    played = 0
    for pair_index, (start_board, opening_name) in enumerate(starts):
        for candidate_white in (True, False):
            b_game = SearchMeter()
            c_game = SearchMeter()
            baseline = make_searcher(False, b_game)
            candidate = make_searcher(True, c_game)
            if candidate_white:
                white, black = candidate, baseline
                white_name, black_name = "search-r2", "search-r1"
                candidate_color = chess.WHITE
            else:
                white, black = baseline, candidate
                white_name, black_name = "search-r1", "search-r2"
                candidate_color = chess.BLACK

            record = play_game(
                white,
                black,
                base_config,
                white_name=white_name,
                black_name=black_name,
                stochastic=False,
                seed=int(args.seed) + played,
                depth=int(args.depth),
                max_plies=int(args.max_plies),
                starting_board=start_board,
                opening_name=opening_name,
                opening_family="search-r2-ab",
            )

            if record.winner is None:
                score = 0.5
                draws += 1
            elif record.winner == candidate_color:
                score = 1.0
                wins += 1
            else:
                score = 0.0
                losses += 1

            baseline_meter.merge(b_game)
            candidate_meter.merge(c_game)

            played += 1
            game_rows.append(
                {
                    "game": played,
                    "pair": pair_index + 1,
                    "opening": opening_name,
                    "candidate_color": "white" if candidate_white else "black",
                    "result": record.result,
                    "candidate_score": score,
                    "plies": record.plies,
                    "candidate_nodes": c_game.nodes,
                    "baseline_nodes": b_game.nodes,
                    "candidate_elapsed_s": c_game.elapsed_s,
                    "baseline_elapsed_s": b_game.elapsed_s,
                    "candidate_stabilized_calls": c_game.opening_stabilized,
                    "candidate_extra_nodes": c_game.opening_extra_nodes,
                }
            )
            print(
                f"  game {played:>2}/{args.pairs * 2}: {opening_name:<24} "
                f"r2={'W' if candidate_white else 'B'} score={score:.1f} plies={record.plies} "
                f"stabilized={c_game.opening_stabilized}"
            )

    score = (wins + 0.5 * draws) / max(1, played)
    node_ratio = candidate_meter.nodes / max(1, baseline_meter.nodes)
    time_ratio = candidate_meter.elapsed_s / max(1e-9, baseline_meter.elapsed_s)
    enough_for_gate = played >= 12

    summary = {
        "generation": int(args.generation),
        "baseline_revision": "search-r1",
        "candidate_revision": "search-r2-opening-stabilization",
        "pairs": int(args.pairs),
        "games": played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "candidate_score": score,
        "baseline": baseline_meter.as_dict(),
        "candidate": candidate_meter.as_dict(),
        "candidate_to_baseline_node_ratio": node_ratio,
        "candidate_to_baseline_time_ratio": time_ratio,
        "enough_games_for_engine_gate": enough_for_gate,
        "book_moves_injected": False,
        "games_detail": game_rows,
    }

    report_dir = snapshot.parent / "dogmatist_v2_validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"search_r2_ab_gen{int(args.generation)}_{int(args.pairs)}pairs.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nSEARCH-R2 FROZEN GEN A/B")
    print("=" * 40)
    print(f"score: {score:.3f}  W/D/L={wins}/{draws}/{losses}  games={played}")
    print(f"node ratio r2/r1: {node_ratio:.3f}")
    print(f"time ratio r2/r1: {time_ratio:.3f}")
    print(f"r2 stabilized calls: {candidate_meter.opening_stabilized}")
    print(f"r2 extra opening nodes: {candidate_meter.opening_extra_nodes}")
    print("book moves: OFF")
    print(
        "gate status: "
        + ("ENOUGH GAMES FOR ENGINE GATE" if enough_for_gate else "SMOKE ONLY; run >=6 pairs before adoption")
    )
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
