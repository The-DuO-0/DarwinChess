# DogMatist / DarwinChess v2 R&D

This branch starts the replacement evolution engine. It is intentionally not a blind rewrite of the chess UI or durable state layer. The v1 design already has valuable properties worth preserving: atomic champion switching, SQLite/WAL lifetime memory, held-out Arena games, compatible optimizer inheritance, and a stable agent boundary.

## Why v2 changes the evolution algorithm

v1 is effectively winner-take-all:

```text
champion -> one challenger -> Arena -> promote/reject -> repeat
```

That makes failed exploration too disposable and serializes the expensive part of overnight learning.

v2 changes this into a compute-budgeted population league:

```text
                         durable replay memory
                                |
                  +-------------+-------------+
                  |                           |
          parallel self-play             hard positions
          CPU workers 1..N               + openings
                  |                           |
                  +-------------+-------------+
                                |
                        one MPS trainer lane
                                |
          +---------------------+---------------------+
          |                     |                     |
      balanced              explorer             specialist
      candidate             candidate             candidate
          \                     |                     /
           +--------------------+--------------------+
                                |
                 league: round-robin / Swiss subset
                    + champion anchor matches
                                |
                 +--------------+---------------+
                 |                              |
          overall elite                 specialist archive
                 |                    opening/endgame niches
                 +--------------+---------------+
                                |
                       next curriculum/replay mix
```

The design deliberately avoids running several full MPS trainers at once. On a single Apple Silicon machine that usually creates GPU/memory-bandwidth contention. Instead, v2 parallelizes game generation and evaluation while preserving one efficient batch-training lane.

## Core rules

1. **No failed-night amnesia.** Rejected candidates can still contribute replay data and hard-position curricula.
2. **No winner-take-all genetics.** The champion remains the safest parent, but a small elite pool and specialist archive survive selection.
3. **Opening specialists survive.** A candidate can lose overall while remaining a donor for an ECO/opening bucket where it has a statistically useful edge.
4. **No neural-weight averaging by default.** Inheritance happens through replay/curriculum/distillation first. Weight interpolation is postponed until we can test model-soup compatibility safely.
5. **Held-out evaluation remains held out.** League/Arena games used for promotion are not automatically inserted into training replay.
6. **Mac headroom is a first-class constraint.** The overnight controller scales CPU game workers slowly and keeps exactly one MPS trainer slot.

## First implementation slice

`dogmatist_v2/league.py`
: population members, match accounting, Elo-like online league table, elite survivor selection.

`dogmatist_v2/specialists.py`
: opening-bucket specialist discovery and replay donor weights independent of overall promotion.

`dogmatist_v2/resource.py`
: conservative adaptive overnight worker budget with thermal/CPU/memory backoff and one trainer lane.

These modules are intentionally independent of the current GUI. The next integration slice will connect them to the real DarwinChess runtime/database and add population tables, league match persistence, candidate-role training curricula, and a Studio league dashboard.

## Migration policy

Do **not** delete `~/.darwinchess` and do not reset the existing champion. v2 should migrate forward from the lifetime database. Existing PGNs, replay examples, generation history, checkpoints, and insights are research assets even if the final model architecture changes.

If a future network architecture is incompatible with v1 checkpoints, we will use the existing champion/search system as a teacher and distill into the new network while keeping lifetime replay and lineage metadata. That is a controlled brain transplant, not a memory wipe.
