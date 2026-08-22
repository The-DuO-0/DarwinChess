from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
from typing import Any

from dogmatist_v2.mac_preflight import load_snapshot_manifest, validate_copied_state
from dogmatist_v2.opening_stability import OpeningSearchObservation, build_stability_report


_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def _json_objects(text: str):
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _first(value: Any, keys: tuple[str, ...]) -> Any | None:
    wanted = {k.lower() for k in keys}
    for key, child in _walk(value):
        if key.lower() in wanted and child is not None:
            return child
    return None


def _normalize_production_text(text: str) -> str:
    """Normalize terminal-oriented analyze output before regex parsing.

    The Mac CLI is human-facing, so its output may contain ANSI escapes,
    full-width punctuation, non-breaking spaces, or terminal line wrapping.
    None of those should make a copied-state diagnostic fail.
    """

    without_ansi = _ANSI_ESCAPE_RE.sub("", text)
    normalized = unicodedata.normalize("NFKC", without_ansi)
    return normalized.replace("\u00a0", " ")


def _parse_production_text(text: str) -> dict[str, object] | None:
    """Parse the human-readable output emitted by the production ``analyze`` CLI.

    The current Mac build prints a Chinese sentence such as::

        我会走 Nf3 (g1f3)。当前搜索评价约 +51cp ... 搜索深度 3，访问 6657 个节点；...

    JSON remains preferred when available. For human-readable output, the UCI
    move inside parentheses is authoritative. Parsing deliberately does *not*
    depend on the SAN token or exact punctuation because production formatting
    can vary across Terminal/localization builds.
    """

    normalized = _normalize_production_text(text)
    if "我会走" not in normalized:
        return None

    # Do not tie this to the display SAN. Find the first UCI move in parentheses
    # after the human-facing move sentence. NFKC above converts full-width
    # parentheses to ASCII and ANSI stripping handles colored terminal output.
    summary_tail = normalized.split("我会走", 1)[1]
    move_match = re.search(
        r"\(\s*([a-h][1-8][a-h][1-8][qrbn]?)\s*\)",
        summary_tail,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if move_match is None:
        # Defensive fallback for a future formatter that drops parentheses but
        # keeps an explicit UCI token near the summary.
        move_match = re.search(
            r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b",
            summary_tail,
            flags=re.IGNORECASE,
        )
    if move_match is None:
        return None

    score_match = re.search(
        r"当前搜索评价约\s*([+-]?\d+(?:\.\d+)?)\s*cp",
        normalized,
        flags=re.IGNORECASE,
    )
    depth_match = re.search(r"搜索深度\s*(\d+)", normalized)
    nodes_match = re.search(r"访问\s*(\d+)\s*个节点", normalized)

    return {
        "move": move_match.group(1).lower(),
        "score_cp": float(score_match.group(1)) if score_match else None,
        "depth": int(depth_match.group(1)) if depth_match else None,
        "elapsed_s": None,
        "nodes": int(nodes_match.group(1)) if nodes_match else None,
        "raw_text": text,
    }


def parse_analysis_stdout(text: str) -> dict[str, object]:
    candidates = list(_json_objects(text))
    for payload in reversed(candidates):
        move = _first(payload, ("best_move", "move_uci", "move", "best_move_uci"))
        if move is None:
            continue
        score = _first(payload, ("score_cp", "best_score_cp", "evaluation_cp", "eval_cp"))
        depth = _first(payload, ("depth", "search_depth"))
        elapsed = _first(payload, ("elapsed_s", "elapsed_seconds", "runtime_seconds"))
        return {
            "move": str(move),
            "score_cp": float(score) if score is not None else None,
            "depth": int(depth) if depth is not None else None,
            "elapsed_s": float(elapsed) if elapsed is not None else None,
            "raw": payload,
        }

    production = _parse_production_text(text)
    if production is not None:
        return production

    tail = text[-1200:].strip()
    raise RuntimeError(
        "could not parse darwinchess analyze output; expected JSON or the production human-readable summary"
        + (f":\n{tail}" if tail else "")
    )


def _source_cli(source_copy: Path) -> Path:
    cli = source_copy / ".venv" / "bin" / "darwinchess"
    if not cli.is_file():
        raise FileNotFoundError(f"copied-source CLI not found: {cli}")
    return cli


def _analysis_env(snapshot_state: Path) -> dict[str, str]:
    home = snapshot_state.parent
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / ".config"),
        XDG_CACHE_HOME=str(home / ".cache"),
        PYTHONNOUSERSITE="1",
        DOGMATIST_V2_COPY_VALIDATION="1",
    )
    return env


def analyze_position(
    cli: Path,
    *,
    env: dict[str, str],
    mode: str,
    depth: int,
    fen: str | None,
) -> dict[str, object]:
    command = [str(cli), "--mode", mode, "analyze", "--depth", str(depth)]
    if fen:
        command.extend(["--fen", fen])
    proc = subprocess.run(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"darwinchess analyze failed at depth {depth} (exit={proc.returncode}):\n{proc.stdout[-4000:]}"
        )
    return parse_analysis_stdout(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare copied Gen54's normal deterministic opening search with one deeper search "
            "along exactly the same baseline self-line. No opening book or random exploration is used."
        )
    )
    parser.add_argument("source_copy")
    parser.add_argument("snapshot_state")
    parser.add_argument("--generation", type=int, default=54)
    parser.add_argument("--mode", choices=("eco", "normal", "night"), default="normal")
    parser.add_argument("--base-depth", type=int, default=2)
    parser.add_argument("--deeper-depth", type=int, default=3)
    parser.add_argument("--plies", type=int, default=8)
    args = parser.parse_args(argv)

    if args.base_depth <= 0 or args.deeper_depth <= args.base_depth:
        parser.error("--deeper-depth must be greater than --base-depth")
    if args.plies <= 0 or args.plies > 16:
        parser.error("--plies must be between 1 and 16")

    source = Path(args.source_copy).expanduser().resolve()
    snapshot = Path(args.snapshot_state).expanduser().resolve()
    preflight = validate_copied_state(snapshot, include_spawn_probe=False)
    if not preflight.ok:
        print(json.dumps({"preflight": preflight.as_dict()}, ensure_ascii=False, indent=2))
        print("STOP: copied-state preflight failed.")
        return 2

    manifest = load_snapshot_manifest(snapshot)
    champion = int(manifest.champion_generation) if manifest.champion_generation is not None else None
    if champion != int(args.generation):
        raise RuntimeError(
            f"opening-search probe refused: snapshot champion is Gen{champion}, requested Gen{args.generation}"
        )

    cli = _source_cli(source)
    env = _analysis_env(snapshot)

    try:
        import chess  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "python-chess is required; run this script with the copied source .venv Python"
        ) from exc

    board = chess.Board()
    observations: list[OpeningSearchObservation] = []

    print(
        f"[opening-search] Gen{args.generation} deterministic baseline depth={args.base_depth} "
        f"vs deeper depth={args.deeper_depth}; following baseline line for {args.plies} plies"
    )
    print("[opening-search] random exploration OFF; opening book OFF")

    for ply in range(1, args.plies + 1):
        fen = board.fen()
        baseline = analyze_position(
            cli,
            env=env,
            mode=args.mode,
            depth=args.base_depth,
            fen=None if ply == 1 else fen,
        )
        deeper = analyze_position(
            cli,
            env=env,
            mode=args.mode,
            depth=args.deeper_depth,
            fen=None if ply == 1 else fen,
        )
        baseline_move = str(baseline["move"])
        deeper_move = str(deeper["move"])
        observation = OpeningSearchObservation(
            ply=ply,
            fen=fen,
            baseline_move=baseline_move,
            deeper_move=deeper_move,
            baseline_score_cp=baseline.get("score_cp"),
            deeper_score_cp=deeper.get("score_cp"),
            baseline_depth=baseline.get("depth"),
            deeper_depth=deeper.get("depth"),
            baseline_elapsed_s=baseline.get("elapsed_s"),
            deeper_elapsed_s=deeper.get("elapsed_s"),
        )
        observations.append(observation)
        delta = observation.score_delta_cp
        delta_text = "?" if delta is None else f"{delta:.0f}cp"
        print(
            f"  ply {ply:>2}: {baseline_move:<6} -> {deeper_move:<6} "
            f"delta={delta_text:<6} {observation.status()}"
        )

        try:
            move = chess.Move.from_uci(baseline_move)
        except ValueError as exc:
            raise RuntimeError(f"analyze returned non-UCI move: {baseline_move}") from exc
        if move not in board.legal_moves:
            raise RuntimeError(f"baseline move is illegal in probe position: {baseline_move}")
        board.push(move)
        if board.is_game_over():
            break

    report = build_stability_report(
        int(args.generation),
        int(args.base_depth),
        int(args.deeper_depth),
        observations,
    )
    report_dir = snapshot.parent / "dogmatist_v2_validation_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"opening_search_stability_gen{int(args.generation)}.json"
    out.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + report.format_text())
    print(f"\nreport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
