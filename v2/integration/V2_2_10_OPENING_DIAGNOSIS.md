# V2.2.10 — Copied-State Opening Diagnosis

This slice turns the Opening Repair lane into a concrete, generation-specific Mac diagnostic.

## Goal

Answer a narrow question before live installation:

> Is Gen54 broadly weak in the opening, or are a few opening/frontier branches responsible?

The diagnostic never changes the live Champion. It runs one Evolution cycle against an isolated copied `.darwinchess` state, captures the early-opening evidence already produced by V2.2.9, and then reads the copied `strength_v2.sqlite3` in SQLite read-only mode.

## Fresh-snapshot rule

Do **not** reuse the earlier validation world that already evolved from Gen54 to Gen62. Create a new snapshot from live state first. The snapshot manifest records the Champion generation, and `run_opening_diagnosis.py` refuses to start if the snapshot Champion does not equal the requested generation.

For a Gen54 diagnosis, the dry preparation step is:

```bash
PYTHONPATH=v2 python v2/integration/production_overlay/prepare_mac_validation.py \
  /Users/o-o/.darwinchess \
  /Users/o-o/dogmatist-opening54-validation \
  --spawn-probe
```

The destination home must be new or empty. The snapshot will be created automatically at:

```text
/Users/o-o/dogmatist-opening54-validation/.darwinchess
```

Inspect `snapshot.champion_generation` in the printed JSON. For this particular test it must be `54`. If live has already moved to another Champion, stop rather than silently diagnosing that model as Gen54.

## Clean Strength-Lab rule

`run_opening_diagnosis.py` resets only these files inside the copied snapshot by default:

- `strength_v2.sqlite3`
- `strength_v2.sqlite3-wal`
- `strength_v2.sqlite3-shm`

The reset helper refuses any target directory whose final path component is not `.darwinchess`, refuses a database name containing a path, and never deletes the production replay/checkpoint database.

This matters because a clean Strength Lab DB prevents old Gen15/Gen54/Gen62 opening pressure from being mixed into the new diagnosis.

## Evidence used

Only rows satisfying both conditions are used:

1. `source_generation == requested generation` (Gen54 by default), and
2. `source_kind LIKE '%_opening'`.

Therefore a middlegame blunder from a game labelled `Queen's Gambit` does not by itself count as an opening failure, and another generation's evidence is not attributed to Gen54.

The report contains:

- opening/frontier bucket;
- internal opening pressure (0–1);
- evidence confidence;
- `WEAK`, `WATCH`, `NO CLEAR WEAKNESS`, or `LOW EVIDENCE` status;
- distinct hard positions and repeated observations;
- mean/max early severity;
- mean/max early value error;
- proposed repair focus;
- explicit `Book moves: OFF` and `Novel exploration: ON` guards.

`pressure` is an internal training/repair signal. It is not Elo and is not an external-engine centipawn verdict.

## Diagnosis command

From the R&D checkout after refreshing the `v2-dynasty-archive` branch and reinstalling the overlay into the copied source tree:

```bash
PYTHONPATH=v2 python v2/integration/production_overlay/run_opening_diagnosis.py \
  /Users/o-o/DarwinChess-v2-test \
  /Users/o-o/dogmatist-opening54-validation/.darwinchess \
  --generation 54 \
  --mode normal \
  --league-parallel 2
```

That first command is a dry run only. It prints the preflight, the snapshot Champion, and the exact isolated paths.

After verifying all of them, execute the same command with:

```bash
  --run
```

The script writes a new JSON artifact beside the normal copied-state validation reports:

```text
opening_diagnosis_gen54_<UTC timestamp>.json
```

and prints a compact table similar to:

```text
GEN54 OPENING DIAGNOSIS
=======================
Queen's Gambit         ███████··· 0.70  WEAK             evidence=8
Reti                   ███······· 0.31  WATCH            evidence=4
frontier:8a42c913      ██········ 0.19  LOW EVIDENCE     evidence=2

Repair focus: Queen's Gambit, Reti
Opening focus ceiling this plan: 60%
Book moves: OFF
Novel exploration: ON
```

## Safety

- Fresh snapshot is produced with SQLite backup while the live database is opened read-only.
- Snapshot checkpoint paths are rewritten to copied files and isolation-checked.
- The diagnosis runner refuses a snapshot whose Champion is not the requested generation.
- Uses the existing copied-state preflight and postflight validator.
- Teacher replay persistence remains forced OFF by copied-state validation.
- League remains 2-way by default; 3 is opt-in.
- Runtime budget still never kills a healthy game.
- Gen54 checkpoint is never trained/overwritten in place by the diagnosis.
- Live `~/.darwinchess` is not used by the chess run.

## Gate before live installation

A real Mac run is still required. Pure-Python CI proves the filtering/ranking/reset logic; it does not prove what Gen54's actual opening profile is. The next decision should be based on the generated Gen54 diagnosis artifact, not on guessed opening names or a human opening book.
