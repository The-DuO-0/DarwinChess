from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state
from dogmatist_v2.opening_search_revision import select_holdout_opening_names
from dogmatist_v2.strength_lab import EngineRevisionGate, EngineTrialEvidence

# These were used during the first 12-game r2c development A/B on frozen Gen54.
# The final gate deliberately excludes them so the candidate cannot pass by only
# fitting the exact openings used while tuning the search revision.
DEVELOPMENT_OPENINGS = {
    "Initial position",
    "Nimzo-Indian",
    "King's Indian",
    "French",
    "Queen's Gambit",
    "Pirc",
}

CANDIDATE_REVISION = "search-r2c-selective-root"
BASELINE_REVISION = "search-r1"
DEFAULT_HOLDOUT_SEED = 20260823


class SearchMeter:
    def __init__(self) -> None:
        self.calls = 0
        self.nodes = 0
        self.elapsed_s = 0.0
        self.opening_stabilized = 0
        self.opening_extra_nodes = 0
        self.opening_verified_moves = 0

    def add(self, result) -> None:
        self.calls += 1
        self.nodes += int(getattr(result, "nodes", 0) or 0)
        self.elapsed_s += float(getattr(result, "elapsed_s", 0.0) or 0.0)
        if bool(getattr(result, "opening_stabilized", False)):
            self.opening_stabilized += 1
        self.opening_extra_nodes += int(getattr(result, "opening_extra_nodes", 0) or 0)
        self.opening_verified_moves += int(getattr(result, "opening_verified_moves", 0) or 0)

    def merge(self, other: "SearchMeter") -> None:
        self.calls += other.calls
        self.nodes += other.nodes
        self.elapsed_s += other.elapsed_s
        self.opening_stabilized += other.opening_stabilized
        self.opening_extra_nodes += other.opening_extra_nodes
        self.opening_verified_moves += other.opening_verified_moves

    def as_dict(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "nodes": self.nodes,
            "elapsed_s": self.elapsed_s,
            "opening_stabilized": self.opening_stabilized,
            "opening_extra_nodes": self.opening_extra_nodes,
            "opening_verified_moves": self.opening_verified_moves,
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
        "revision_id": CANDIDATE_REVISION,
        "opening_plies": 8,
        "always_verify_plies": 0,
        "extra_depth": 1,
        "candidate_margin_cp": 18.0,
        "iteration_swing_cp": 60.0,
        "move_flip_min_swing_cp": 45.0,
        "max_extra_searches": 3,
        "verification_min_candidates": 4,
        "verification_max_candidates": 8,
        "verification_score_window_cp": 90.0,
    }
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Independent holdout EngineRevisionGate for search-r2c on frozen model weights. "
            "Uses opening names disjoint from the development A/B, paired colours, no DB writes."
        )
    )
    parser.add_argument("source_copy")
    parser.add_argument("snapshot_state")
    parser.add_argument("--generation", type=int, default=54)
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument("--pairs", type=int, default=6, help="holdout colour pairs; 6 pairs = 12 games")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--max-plies", type=int, default=180)
    parser.add_argument("--seed", type=int, default=DEFAULT_HOLDOUT_SEED)
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
            f"search-r2c holdout gate refused: snapshot manifest champion is Gen{snapshot_champion}, "
            f"requested Gen{args.generation}"
        )

    if not (source / "darwinchess" / "search.py").is_file():
        raise FileNotFoundError(f"copied production search.py not found under {source}")

    sys.path.insert(0, str(source))
    _analysis_env(snapshot)

    import chess
    from darwinchess.evaluator import HybridEvaluator
    from darwinchess.opening_curriculum import CURATED_OPENINGS
    from darwinchess.runtime import DarwinRuntime
    from darwinchess.search import AlphaBetaSearcher
    from darwinchess.selfplay import play_game

    with DarwinRuntime(mode=args.mode, apply_nice=False) as rt:
        live_copy_champion = int(rt.champion_info()["id"])
        if live_copy_champion != int(args.generation):
            raise RuntimeError(
                f"search-r2c holdout gate refused: copied DB champion is Gen{live_copy_champion}, "
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

    opening_by_name = {row.name: row for row in CURATED_OPENINGS}
    holdout_names = select_holdout_opening_names(
        opening_by_name,
        excluded_names=DEVELOPMENT_OPENINGS,
        pair_count=int(args.pairs),
        seed=int(args.seed),
    )
    starts = [(opening_by_name[name].board(), name) for name in holdout_names]

    wins = draws = losses = 0
    baseline_meter = SearchMeter()
    candidate_meter = SearchMeter()
    rows: list[dict[str, object]] = []

    print(
        f"[search-r2c-holdout] Frozen Gen{args.generation}; {args.pairs} unseen opening pairs; "
        f"search-r1 vs search-r2c; book moves OFF; seed={args.seed}"
    )
    print("  development openings excluded: " + ", ".join(sorted(DEVELOPMENT_OPENINGS)))
    print("  holdout openings: " + ", ".join(holdout_names))

    played = 0
    for pair_index, (start_board, opening_name) in enumerate(starts):
        for candidate_white in (True, False):
            b_game = SearchMeter()
            c_game = SearchMeter()
            baseline = make_searcher(False, b_game)
            candidate = make_searcher(True, c_game)
            if candidate_white:
                white, black = candidate, baseline
                white_name, black_name = CANDIDATE_REVISION, BASELINE_REVISION
                candidate_color = chess.WHITE
            else:
                white, black = baseline, candidate
                white_name, black_name = BASELINE_REVISION, CANDIDATE_REVISION
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
                opening_family="search-r2c-independent-holdout",
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
            rows.append({
                "game": played,
                "pair": pair_index + 1,
                "opening": opening_name,
                "candidate_color": "white" if candidate_white else "black",
                "result": record.result,
                "candidate_score": score,
                "plies": int(record.plies),
                "candidate_nodes": c_game.nodes,
                "baseline_nodes": b_game.nodes,
                "candidate_elapsed_s": c_game.elapsed_s,
                "baseline_elapsed_s": b_game.elapsed_s,
                "candidate_stabilized_calls": c_game.opening_stabilized,
                "candidate_extra_nodes": c_game.opening_extra_nodes,
                "candidate_verified_moves": c_game.opening_verified_moves,
            })
            print(
                f"  game {played:>2}/{args.pairs * 2}: {opening_name:<24} "
                f"r2c={'W' if candidate_white else 'B'} score={score:.1f} plies={record.plies} "
                f"stabilized={c_game.opening_stabilized} verified={c_game.opening_verified_moves}"
            )

    score = (wins + 0.5 * draws) / max(1, played)
    node_ratio = candidate_meter.nodes / max(1, baseline_meter.nodes)
    time_ratio = candidate_meter.elapsed_s / max(1e-9, baseline_meter.elapsed_s)

    # The immutable reference for an engine-revision experiment is the same
    # frozen Gen54 checkpoint running the baseline search-r1. Paired colours make
    # 0.5 the neutral reference point, so the holdout delta is measured relative
    # to that fixed baseline without changing model weights.
    fixed_reference_delta = score - 0.5
    evidence = EngineTrialEvidence(
        candidate_revision_id=CANDIDATE_REVISION,
        paired_games=played,
        score_vs_baseline=score,
        fixed_reference_delta=fixed_reference_delta,
        compute_cost_ratio=time_ratio,
    )
    decision = EngineRevisionGate().decide(evidence)
    avg_verified = candidate_meter.opening_verified_moves / max(1, candidate_meter.opening_stabilized)

    summary = {
        "generation": int(args.generation),
        "baseline_revision": BASELINE_REVISION,
        "candidate_revision": CANDIDATE_REVISION,
        "holdout": True,
        "holdout_seed": int(args.seed),
        "development_openings_excluded": sorted(DEVELOPMENT_OPENINGS),
        "holdout_openings": list(holdout_names),
        "pairs": int(args.pairs),
        "games": played,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "candidate_score": score,
        "fixed_reference_delta": fixed_reference_delta,
        "baseline": baseline_meter.as_dict(),
        "candidate": candidate_meter.as_dict(),
        "candidate_to_baseline_node_ratio": node_ratio,
        "candidate_to_baseline_time_ratio": time_ratio,
        "average_verified_moves_per_stabilization": avg_verified,
        "engine_gate_action": decision.action.value,
        "engine_gate_reason": decision.reason,
        "book_moves_injected": False,
        "policy": candidate_cfg["search"]["opening_stabilization"],
        "games_detail": rows,
    }

    report_dir = snapshot.parent / "dogmatist_v2_validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"search_r2c_holdout_gate_gen{int(args.generation)}_{int(args.pairs)}pairs.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nSEARCH-R2C INDEPENDENT HOLDOUT ENGINE GATE")
    print("=" * 52)
    print("holdout openings: " + ", ".join(holdout_names))
    print(f"score: {score:.3f}  W/D/L={wins}/{draws}/{losses}  games={played}")
    print(f"fixed-reference delta vs frozen r1: {fixed_reference_delta:+.3f}")
    print(f"node ratio r2c/r1: {node_ratio:.3f}")
    print(f"time ratio r2c/r1: {time_ratio:.3f}")
    print(f"r2c stabilized calls: {candidate_meter.opening_stabilized}")
    print(f"r2c extra opening nodes: {candidate_meter.opening_extra_nodes}")
    print(f"avg verified root moves/stabilization: {avg_verified:.2f}")
    print("book moves: OFF")
    print(f"ENGINE GATE: {decision.action.value.upper()} - {decision.reason}")
    print("live state modified: NO")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
