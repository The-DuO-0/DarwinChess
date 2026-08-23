from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from typing import Any

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state
from dogmatist_v2.search_forensics import SearchForensicRow, summarize_search_forensics


CANDIDATE_REVISION = "search-r2c-selective-root"


def _analysis_env(snapshot_state: Path) -> None:
    home = snapshot_state.parent
    os.environ.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_CACHE_HOME=str(home / ".cache"),
        PYTHONNOUSERSITE="1",
        DOGMATIST_V2_COPY_VALIDATION="1",
    )


def _candidate_config(base: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
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


class CaptureSearcher:
    """Record only positions where r2c actually spent selective +1 search."""

    def __init__(self, inner: Any, captures: list[dict[str, Any]]) -> None:
        self.inner = inner
        self.captures = captures

    def search(self, board: Any, *args: Any, **kwargs: Any) -> Any:
        fen = board.fen()
        result = self.inner.search(board, *args, **kwargs)
        if bool(getattr(result, "opening_stabilized", False)):
            self.captures.append(
                {
                    "fen": fen,
                    "candidate_move": result.move.uci() if result.move is not None else None,
                    "candidate_score_cp": float(result.score_cp),
                    "reason": getattr(result, "opening_stabilization_reason", None),
                    "verified_moves": int(getattr(result, "opening_verified_moves", 0) or 0),
                    "extra_nodes": int(getattr(result, "opening_extra_nodes", 0) or 0),
                }
            )
        return result


def _score_map(result: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in getattr(result, "candidates", []) or []:
        move = getattr(row, "move", None)
        if move is not None:
            out[move.uci()] = float(getattr(row, "score_cp", 0.0))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy-state-only failure forensics for search-r2c. Replays selected holdout openings, "
            "captures every r2c stabilization position, then compares search-r1 depth2, r2c's "
            "chosen move, and a fresh full-root depth3 result on exactly the same FEN."
        )
    )
    parser.add_argument("source_copy")
    parser.add_argument("snapshot_state")
    parser.add_argument("--generation", type=int, default=54)
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument("--opening", action="append", default=None, help="curated opening name; may be repeated")
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--deeper-depth", type=int, default=3)
    parser.add_argument("--max-plies", type=int, default=180)
    parser.add_argument("--seed", type=int, default=20260823)
    args = parser.parse_args(argv)

    if args.depth <= 0 or args.deeper_depth <= args.depth:
        parser.error("require 0 < --depth < --deeper-depth")
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
            f"failure probe refused: snapshot manifest champion is Gen{snapshot_champion}, "
            f"requested Gen{args.generation}"
        )

    sys.path.insert(0, str(source))
    _analysis_env(snapshot)

    import chess
    from darwinchess.evaluator import HybridEvaluator
    from darwinchess.opening_curriculum import CURATED_OPENINGS
    from darwinchess.runtime import DarwinRuntime
    from darwinchess.search import AlphaBetaSearcher
    from darwinchess.selfplay import play_game

    with DarwinRuntime(mode=args.mode, apply_nice=False) as rt:
        copied_champion = int(rt.champion_info()["id"])
        if copied_champion != int(args.generation):
            raise RuntimeError(
                f"failure probe refused: copied DB champion is Gen{copied_champion}, "
                f"requested Gen{args.generation}"
            )
        model, payload = rt.load_champion(rt.search_device)
        genome = rt.genome_from_payload(payload)
        base_config = copy.deepcopy(rt.config)
        device = rt.search_device

    baseline_cfg = _candidate_config(base_config, enabled=False)
    candidate_cfg = _candidate_config(base_config, enabled=True)

    def make_searcher(*, candidate: bool) -> Any:
        cfg = candidate_cfg if candidate else baseline_cfg
        evaluator = HybridEvaluator(model, cfg, device, genome)
        return AlphaBetaSearcher(evaluator, cfg)

    by_name = {row.name: row for row in CURATED_OPENINGS}
    opening_names = args.opening or ["Slav"]
    missing = [name for name in opening_names if name not in by_name]
    if missing:
        raise ValueError(f"unknown curated opening(s): {missing}")

    print(
        f"[search-r2c-forensics] Frozen Gen{args.generation}; openings={', '.join(opening_names)}; "
        f"depth {args.depth} / full deeper {args.deeper_depth}; book moves OFF"
    )
    print("  NOTE: these openings are now failure-analysis data and must not be reused as the next final holdout.")

    game_rows: list[dict[str, Any]] = []
    captured: list[dict[str, Any]] = []
    played = 0
    for opening_name in opening_names:
        start_board = by_name[opening_name].board()
        for candidate_white in (True, False):
            captures_this_game: list[dict[str, Any]] = []
            baseline = make_searcher(candidate=False)
            candidate = CaptureSearcher(make_searcher(candidate=True), captures_this_game)
            if candidate_white:
                white, black = candidate, baseline
                white_name, black_name = "search-r2c", "search-r1"
                candidate_color = chess.WHITE
            else:
                white, black = baseline, candidate
                white_name, black_name = "search-r1", "search-r2c"
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
                opening_family="search-r2c-failure-probe",
            )
            if record.winner is None:
                candidate_score = 0.5
            elif record.winner == candidate_color:
                candidate_score = 1.0
            else:
                candidate_score = 0.0
            for row in captures_this_game:
                row["opening"] = opening_name
                row["candidate_color"] = "white" if candidate_white else "black"
                row["game"] = played + 1
                captured.append(row)
            played += 1
            game_rows.append(
                {
                    "game": played,
                    "opening": opening_name,
                    "candidate_color": "white" if candidate_white else "black",
                    "candidate_score": candidate_score,
                    "result": record.result,
                    "plies": int(record.plies),
                    "stabilized_positions": len(captures_this_game),
                }
            )
            print(
                f"  game {played}: {opening_name:<22} r2c={'W' if candidate_white else 'B'} "
                f"score={candidate_score:.1f} plies={record.plies} stabilized={len(captures_this_game)}"
            )

    unique: dict[str, dict[str, Any]] = {}
    for row in captured:
        unique.setdefault(str(row["fen"]), row)

    forensic_rows: list[SearchForensicRow] = []
    detailed_rows: list[dict[str, Any]] = []
    print("\nSTABILIZATION FORENSICS")
    print("=" * 72)
    for index, capture in enumerate(unique.values(), start=1):
        board = chess.Board(str(capture["fen"]))
        absolute_ply = (int(board.fullmove_number) - 1) * 2 + (1 if board.turn == chess.WHITE else 2)
        shallow = make_searcher(candidate=False).search(board.copy(stack=False), depth=int(args.depth), top_n=128)
        full = make_searcher(candidate=False).search(board.copy(stack=False), depth=int(args.deeper_depth), top_n=128)
        shallow_move = shallow.move.uci() if shallow.move is not None else None
        full_move = full.move.uci() if full.move is not None else None
        candidate_move = capture.get("candidate_move")
        full_scores = _score_map(full)
        row = SearchForensicRow(
            fen=str(capture["fen"]),
            ply=absolute_ply,
            baseline_move=shallow_move,
            candidate_move=str(candidate_move) if candidate_move is not None else None,
            full_deeper_move=full_move,
            full_best_score_cp=float(full.score_cp) if full.move is not None else None,
            full_baseline_score_cp=full_scores.get(shallow_move) if shallow_move is not None else None,
            full_candidate_score_cp=full_scores.get(str(candidate_move)) if candidate_move is not None else None,
        )
        forensic_rows.append(row)
        detail = {
            "index": index,
            "opening": capture.get("opening"),
            "game": capture.get("game"),
            "candidate_color": capture.get("candidate_color"),
            "fen": row.fen,
            "ply": row.ply,
            "baseline_move": row.baseline_move,
            "candidate_move": row.candidate_move,
            "full_deeper_move": row.full_deeper_move,
            "classification": row.classification,
            "candidate_regret_cp": row.candidate_regret_cp,
            "baseline_regret_cp": row.baseline_regret_cp,
            "reason": capture.get("reason"),
            "verified_moves": capture.get("verified_moves"),
            "extra_nodes": capture.get("extra_nodes"),
        }
        detailed_rows.append(detail)
        c_regret = "?" if row.candidate_regret_cp is None else f"{row.candidate_regret_cp:.0f}cp"
        b_regret = "?" if row.baseline_regret_cp is None else f"{row.baseline_regret_cp:.0f}cp"
        print(
            f"  #{index:02d} ply={row.ply:<2} r1={str(row.baseline_move):<5} "
            f"r2c={str(row.candidate_move):<5} full{args.deeper_depth}={str(row.full_deeper_move):<5} "
            f"{row.classification:<21} regret(r2c/r1)={c_regret}/{b_regret}"
        )

    summary = summarize_search_forensics(forensic_rows)
    print("\nSEARCH-R2C FAILURE FORENSICS SUMMARY")
    print("=" * 48)
    print(f"positions: {summary.positions}")
    print(f"helpful flips: {summary.helpful_flips}")
    print(f"harmful flips: {summary.harmful_flips}")
    print(f"same as full depth{args.deeper_depth}: {summary.same_as_full}")
    print(f"both differ from full depth{args.deeper_depth}: {summary.both_differ_from_full}")
    print(f"r2c/full match rate: {summary.candidate_full_match_rate:.3f}")
    print(f"r1/full match rate: {summary.baseline_full_match_rate:.3f}")
    if summary.mean_candidate_regret_cp is not None:
        print(f"mean r2c regret vs full depth{args.deeper_depth}: {summary.mean_candidate_regret_cp:.1f}cp")
    if summary.mean_baseline_regret_cp is not None:
        print(f"mean r1 regret vs full depth{args.deeper_depth}: {summary.mean_baseline_regret_cp:.1f}cp")
    print("adoption decision: NONE - diagnostic only")
    print("live state modified: NO")

    payload = {
        "generation": int(args.generation),
        "candidate_revision": CANDIDATE_REVISION,
        "openings": opening_names,
        "depth": int(args.depth),
        "deeper_depth": int(args.deeper_depth),
        "games": game_rows,
        "positions": detailed_rows,
        "summary": summary.as_dict(),
        "book_moves_injected": False,
        "live_state_modified": False,
        "warning": "Failure-analysis openings are consumed diagnostic data; exclude them from the next final holdout.",
    }
    report_dir = snapshot.parent / "dogmatist_v2_validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_".join(name.lower().replace(" ", "-").replace("'", "") for name in opening_names)
    out = report_dir / f"search_r2c_failure_probe_gen{int(args.generation)}_{suffix}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
