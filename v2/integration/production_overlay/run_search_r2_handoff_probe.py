from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from typing import Any

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state
from dogmatist_v2.search_handoff import HandoffBranchEvidence


def _analysis_env(snapshot_state: Path) -> None:
    home = snapshot_state.parent
    os.environ.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_CACHE_HOME=str(home / ".cache"),
        PYTHONNOUSERSITE="1",
        DOGMATIST_V2_COPY_VALIDATION="1",
    )


def _baseline_config(base: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(base)
    cfg.setdefault("search", {})["opening_stabilization"] = {
        "enabled": False,
        "revision_id": "search-r1",
    }
    return cfg


def _score_from_actor(record: Any, actor_color: Any) -> float:
    if record.winner is None:
        return 0.5
    return 1.0 if record.winner == actor_color else 0.0


def _default_report(snapshot: Path, generation: int) -> Path:
    report_dir = snapshot.parent / "dogmatist_v2_validation_reports"
    preferred = report_dir / f"search_r2c_failure_probe_gen{generation}_slav.json"
    if preferred.is_file():
        return preferred
    matches = sorted(report_dir.glob(f"search_r2c_failure_probe_gen{generation}_*.json"))
    if not matches:
        raise FileNotFoundError(
            f"no search-r2c failure-forensics report found under {report_dir}; run the failure probe first"
        )
    return matches[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy-state-only counterfactual handoff probe for failed search-r2c positions. "
            "At each r1/r2c divergence, force either move, then continue both branches under "
            "the same search-r1 policy at shallow and deeper depths."
        )
    )
    parser.add_argument("source_copy")
    parser.add_argument("snapshot_state")
    parser.add_argument("--generation", type=int, default=54)
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument("--forensics-report", default=None)
    parser.add_argument("--shallow-depth", type=int, default=2)
    parser.add_argument("--deep-depth", type=int, default=3)
    parser.add_argument("--continuation-plies", type=int, default=120)
    parser.add_argument("--max-positions", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260824)
    args = parser.parse_args(argv)

    if args.shallow_depth <= 0 or args.deep_depth <= args.shallow_depth:
        parser.error("require 0 < --shallow-depth < --deep-depth")
    if args.continuation_plies <= 0 or args.max_positions <= 0:
        parser.error("continuation/max-position limits must be positive")

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
            f"handoff probe refused: snapshot manifest champion is Gen{snapshot_champion}, "
            f"requested Gen{args.generation}"
        )

    report_path = (
        Path(args.forensics_report).expanduser().resolve()
        if args.forensics_report
        else _default_report(snapshot, int(args.generation))
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    positions = [
        row
        for row in report.get("positions", [])
        if row.get("baseline_move")
        and row.get("candidate_move")
        and row.get("baseline_move") != row.get("candidate_move")
    ][: int(args.max_positions)]
    if not positions:
        raise RuntimeError("forensics report contains no r1/r2c move divergences to probe")

    sys.path.insert(0, str(source))
    _analysis_env(snapshot)

    import chess
    from darwinchess.evaluator import HybridEvaluator
    from darwinchess.runtime import DarwinRuntime
    from darwinchess.search import AlphaBetaSearcher
    from darwinchess.selfplay import play_game

    with DarwinRuntime(mode=args.mode, apply_nice=False) as rt:
        copied_champion = int(rt.champion_info()["id"])
        if copied_champion != int(args.generation):
            raise RuntimeError(
                f"handoff probe refused: copied DB champion is Gen{copied_champion}, "
                f"requested Gen{args.generation}"
            )
        model, payload = rt.load_champion(rt.search_device)
        genome = rt.genome_from_payload(payload)
        base_config = copy.deepcopy(rt.config)
        device = rt.search_device

    common_cfg = _baseline_config(base_config)

    def make_searcher() -> Any:
        evaluator = HybridEvaluator(model, common_cfg, device, genome)
        return AlphaBetaSearcher(evaluator, common_cfg)

    def play_branch(board: Any, forced_move_uci: str, *, depth: int, seed: int) -> dict[str, Any]:
        actor_color = board.turn
        move = chess.Move.from_uci(str(forced_move_uci))
        if move not in board.legal_moves:
            raise RuntimeError(f"illegal forced move {forced_move_uci} for {board.fen()}")
        after = board.copy(stack=False)
        after.push(move)
        record = play_game(
            make_searcher(),
            make_searcher(),
            common_cfg,
            white_name=f"common-r1-d{depth}",
            black_name=f"common-r1-d{depth}",
            stochastic=False,
            seed=seed,
            depth=int(depth),
            max_plies=int(args.continuation_plies),
            starting_board=after,
            opening_name="counterfactual-handoff",
            opening_family="search-r2-handoff",
        )
        return {
            "score": _score_from_actor(record, actor_color),
            "result": record.result,
            "termination": record.termination,
            "plies": int(record.plies),
        }

    print(
        f"[search-r2-handoff] Frozen Gen{args.generation}; divergences={len(positions)}; "
        f"common continuation search-r1 depth {args.shallow_depth} and {args.deep_depth}; book moves OFF"
    )
    print("  Purpose: test whether a deeper opening move is compatible with the shallower policy that inherits the position.")

    output_rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for index, row in enumerate(positions, start=1):
        board = chess.Board(str(row["fen"]))
        baseline_move = str(row["baseline_move"])
        candidate_move = str(row["candidate_move"])
        seed0 = int(args.seed) + index * 100

        shallow_baseline = play_branch(board, baseline_move, depth=int(args.shallow_depth), seed=seed0 + 1)
        shallow_candidate = play_branch(board, candidate_move, depth=int(args.shallow_depth), seed=seed0 + 2)
        deep_baseline = play_branch(board, baseline_move, depth=int(args.deep_depth), seed=seed0 + 3)
        deep_candidate = play_branch(board, candidate_move, depth=int(args.deep_depth), seed=seed0 + 4)

        evidence = HandoffBranchEvidence(
            shallow_baseline_score=float(shallow_baseline["score"]),
            shallow_candidate_score=float(shallow_candidate["score"]),
            deep_baseline_score=float(deep_baseline["score"]),
            deep_candidate_score=float(deep_candidate["score"]),
        )
        diagnosis = evidence.diagnosis.value
        counts[diagnosis] = counts.get(diagnosis, 0) + 1
        payload = {
            "index": index,
            "opening": row.get("opening"),
            "game": row.get("game"),
            "ply": row.get("ply"),
            "fen": row.get("fen"),
            "baseline_move": baseline_move,
            "candidate_move": candidate_move,
            "full_deeper_move": row.get("full_deeper_move"),
            "immediate_classification": row.get("classification"),
            "immediate_candidate_regret_cp": row.get("candidate_regret_cp"),
            "immediate_baseline_regret_cp": row.get("baseline_regret_cp"),
            "shallow_baseline_branch": shallow_baseline,
            "shallow_candidate_branch": shallow_candidate,
            "deep_baseline_branch": deep_baseline,
            "deep_candidate_branch": deep_candidate,
            "handoff": evidence.as_dict(),
        }
        output_rows.append(payload)
        print(
            f"  #{index:02d} ply={row.get('ply')} r1={baseline_move} r2c={candidate_move} "
            f"| shallow {shallow_baseline['score']:.1f}->{shallow_candidate['score']:.1f} "
            f"delta={evidence.shallow_delta:+.1f} "
            f"| deep {deep_baseline['score']:.1f}->{deep_candidate['score']:.1f} "
            f"delta={evidence.deep_delta:+.1f} | {diagnosis}"
        )

    print("\nSEARCH-R2C OPENING HANDOFF SUMMARY")
    print("=" * 48)
    print(f"divergences tested: {len(output_rows)}")
    for key in (
        "candidate_supported",
        "continuation_mismatch",
        "candidate_harmful",
        "mixed",
    ):
        print(f"{key}: {counts.get(key, 0)}")
    print("interpretation:")
    print("  continuation_mismatch = deeper opening move works with deeper follow-up but degrades under the shallow handoff")
    print("  candidate_harmful = candidate branch is worse even under deeper common continuation")
    print("  candidate_supported = candidate branch is not worse under either common continuation")
    print("live state modified: NO")

    payload = {
        "generation": int(args.generation),
        "source_forensics_report": str(report_path),
        "shallow_depth": int(args.shallow_depth),
        "deep_depth": int(args.deep_depth),
        "continuation_plies": int(args.continuation_plies),
        "positions": output_rows,
        "diagnosis_counts": counts,
        "book_moves_injected": False,
        "live_state_modified": False,
    }
    report_dir = snapshot.parent / "dogmatist_v2_validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"search_r2c_handoff_probe_gen{int(args.generation)}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
