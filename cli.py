from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import chess

from .dialogue import DialogueAgent, explain_search
from .exporter import export_research_bundle
from .runtime import DarwinRuntime
from .selfplay import build_pgn


def _runtime(args) -> DarwinRuntime:
    return DarwinRuntime(args.config, mode=args.mode, device=args.device, search_device=args.search_device)


def cmd_init(args) -> int:
    with _runtime(args) as rt:
        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_status(args) -> int:
    with _runtime(args) as rt:
        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args) -> int:
    with _runtime(args) as rt:
        print(json.dumps(rt.doctor(), ensure_ascii=False, indent=2))
    return 0


def cmd_selfplay(args) -> int:
    with _runtime(args) as rt:
        ids = rt.selfplay(args.games)
        print(f"saved {len(ids)} self-play games")
        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_evolve(args) -> int:
    with _runtime(args) as rt:
        try:
            rt.evolve(hours=args.hours, cycles=args.cycles)
        except KeyboardInterrupt:
            print("\nInterrupted safely. Completed games and accepted checkpoints were already committed.")
        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_challenge(args) -> int:
    with _runtime(args) as rt:
        trained = rt.train_challenger(args.steps)
        if trained is None:
            print("Not enough replay examples yet. Run selfplay/evolve first.")
            return 2
        gid, model, stats, path = trained
        print(f"challenger g{gid} trained: {stats}")
        result = rt.gate_challenger(gid, model, games=args.games)
        print(f"arena: {result}")
        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))
    return 0


def cmd_analyze(args) -> int:
    with _runtime(args) as rt:
        board = chess.Board(args.fen) if args.fen else chess.Board()
        result = rt.analyze(args.fen, depth=args.depth, top_n=args.top)
        print(board)
        print(explain_search(board, result))
    return 0


def _parse_move(board: chess.Board, text: str) -> chess.Move | None:
    text = text.strip()
    try:
        return board.parse_san(text)
    except ValueError:
        try:
            move = chess.Move.from_uci(text)
            return move if move in board.legal_moves else None
        except ValueError:
            return None


def cmd_play(args) -> int:
    with _runtime(args) as rt:
        searcher = rt.make_searcher()
        board = chess.Board()
        played_moves: list[chess.Move] = []
        color = args.color
        if color == "random":
            color = random.choice(["white", "black"])
        human = chess.WHITE if color == "white" else chess.BLACK
        print(f"You are {color}. Enter SAN (e4, Nf3, O-O) or UCI (e2e4). Type quit to stop.")

        while not board.is_game_over(claim_draw=True):
            print("\n" + str(board) + "\n")
            if board.turn == human:
                while True:
                    text = input("you> ").strip()
                    if text.lower() in {"quit", "exit", "q"}:
                        return 0
                    move = _parse_move(board, text)
                    if move is not None:
                        board.push(move)
                        played_moves.append(move)
                        break
                    print("Illegal/unrecognized move.")
            else:
                before = board.copy(stack=False)
                result = searcher.search(board, depth=args.depth, top_n=5)
                if result.move is None:
                    break
                print("ai> " + explain_search(before, result))
                board.push(result.move)
                played_moves.append(result.move)

        print("\n" + str(board))
        final_result = board.result(claim_draw=True)
        print("Result:", final_result)
        outcome = board.outcome(claim_draw=True)
        termination = outcome.termination.name.lower() if outcome is not None else "completed"
        generation = int(rt.champion_info()["id"])
        white_name = "Human" if human == chess.WHITE else f"DarwinChess-g{generation}"
        black_name = "Human" if human == chess.BLACK else f"DarwinChess-g{generation}"
        rt.memory.add_game(
            source="human",
            generation=generation,
            white_agent=white_name,
            black_agent=black_name,
            result=final_result,
            termination=termination,
            pgn=build_pgn(played_moves, final_result, white_name, black_name, termination),
            plies=len(played_moves),
            examples=[],  # Remember the encounter without blindly imitating the human.
            metadata={"human_color": color},
        )
        print("This completed game was added to long-term memory (not training replay).")
    return 0


def cmd_chat(args) -> int:
    with _runtime(args) as rt:
        agent = DialogueAgent(rt)
        if args.message:
            print(agent.answer(" ".join(args.message)))
            return 0
        print("DarwinChess chat. Type quit to exit.")
        while True:
            try:
                q = input("you> ").strip()
            except EOFError:
                break
            if q.lower() in {"quit", "exit", "q"}:
                break
            print("darwin> " + agent.answer(q))
    return 0


def cmd_export(args) -> int:
    with _runtime(args) as rt:
        out = Path(args.out).expanduser() if args.out else rt.paths["exports"]
        paths = export_research_bundle(rt.memory, out)
        print(json.dumps(paths, ensure_ascii=False, indent=2))
    return 0

def cmd_teacher(args) -> int:
    with _runtime(args) as rt:
        result = rt.teacher_distill(args.positions)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="darwinchess", description="Persistent self-evolving conversational chess agent")
    parser.add_argument("--config", help="YAML override config")
    parser.add_argument("--mode", choices=["eco", "normal", "night"], help="resource mode")
    parser.add_argument("--device", choices=["cpu", "mps", "cuda"], help="force training device")
    parser.add_argument("--search-device", choices=["cpu", "mps", "cuda"], help="force search/inference device")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="initialize persistent state")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("status", help="show real persistent status")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("doctor", help="check local runtime/MPS/database")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("selfplay", help="generate durable self-play experience")
    p.add_argument("--games", type=int)
    p.set_defaults(func=cmd_selfplay)

    p = sub.add_parser("evolve", help="run the complete self-play→train→arena loop")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--hours", type=float, help="run until this many hours have elapsed")
    g.add_argument("--cycles", type=int, help="run a fixed number of cycles")
    p.set_defaults(func=cmd_evolve)

    p = sub.add_parser("challenge", help="train a challenger from replay and gate it in arena")
    p.add_argument("--steps", type=int)
    p.add_argument("--games", type=int, help="arena games")
    p.set_defaults(func=cmd_challenge)

    p = sub.add_parser("analyze", help="analyze a position")
    p.add_argument("--fen")
    p.add_argument("--depth", type=int)
    p.add_argument("--top", type=int, default=5)
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("play", help="play against the current champion")
    p.add_argument("--color", choices=["white", "black", "random"], default="random")
    p.add_argument("--depth", type=int)
    p.set_defaults(func=cmd_play)

    p = sub.add_parser("chat", help="talk to DarwinChess about its real state or positions")
    p.add_argument("message", nargs="*")
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("teacher", help="optionally label replay positions with Stockfish")
    p.add_argument("--positions", type=int, default=64)
    p.set_defaults(func=cmd_teacher)

    p = sub.add_parser("export", help="export lineage, metrics, insights and PGNs for research")
    p.add_argument("--out")
    p.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code = args.func(args)
    except Exception as exc:
        print(f"DarwinChess error: {exc}", file=sys.stderr)
        if getattr(args, "command", None) == "doctor":
            raise
        code = 1
    raise SystemExit(code)
