# DarwinChess Studio 1.0

Desktop UI add-on for the existing DarwinChess 1.0 project. It deliberately does **not** replace or copy the chess brain, SQLite database, replay memory, checkpoints, or champion selection logic.

## Install on the Mac

1. Unzip this package.
2. Copy `studio/`, `install_studio.command`, and `run_studio.command` into the existing **DarwinChess-1.0 project folder** (the folder that already contains `.venv`, `setup_mac.sh`, etc.).
3. Double-click `install_studio.command` once. macOS may ask you to allow the script in Privacy & Security.
4. Double-click `run_studio.command` whenever you want the GUI.

Terminal equivalent:

```bash
cd /path/to/DarwinChess-1.0
./install_studio.command
./run_studio.command
```

## What is wired to the real system

- **Play Champion** uses `DarwinChessAgent.best_move(fen)`; there is no dummy move generator.
- **Dashboard** uses `DarwinChessAgent.status()`.
- **Conversation** uses `DarwinChessAgent.talk()`.
- **Evolution** launches the existing `darwinchess --mode ... evolve`, `challenge`, `selfplay`, and `export` commands.
- **Stop safely** sends SIGINT on macOS so the existing safe-boundary behavior is used.
- **Research** reads the existing SQLite database in read-only mode and discovers generation/metric tables without changing them.
- Human-vs-champion PGNs are saved to `~/.darwinchess/studio_games/`. Studio never inserts those games into replay automatically.

## UI areas

### Dashboard
Current champion generation, lifetime game/replay counts (when exposed by `status()`), raw status view, DB location, and process state.

### Play Champion
Clickable chessboard, white/black selection, board flip, legal-move highlighting, promotion chooser, move history, FEN, AI-thinking lockout, check highlighting, resign/new game, and PGN saving.

### Evolution
Resource profile (`eco`, `normal`, `night`), cycle/hour runs, safe stop, one-off challenge, self-play generation, export, live stdout, and an automatically highlighted Self-play → Train → Arena → Promote/Reject pipeline.

### Research & lineage
Read-only generations/metrics tables, database table counts, training-loss chart, Arena-score chart, and export button. The DB adapter is deliberately schema-tolerant so it can survive modest backend evolution.

### Conversation
A desktop chat panel directly connected to DarwinChess's language layer.

## Data safety

Studio does not contain reset/delete buttons. It never deletes `~/.darwinchess`, never writes over champion checkpoints, and never changes promotion rules. Training continues to use DarwinChess's existing held-out Arena and atomic champion switch.

## If the window cannot find DarwinChess

Run from the project venv:

```bash
source .venv/bin/activate
darwinchess doctor
python -m studio
```

If `darwinchess doctor` works, Studio should use the same install and state directory.
