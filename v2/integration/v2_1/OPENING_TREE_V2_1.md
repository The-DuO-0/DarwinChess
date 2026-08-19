# dog_matist V2.1 — OpenTree / Frontier Curriculum R&D

Status: **R&D preview, not yet for live installation.**

V2.0.1 proved the population/league/specialist pipeline, but its opening layer was still human-name-centric and seed-position-centric. V2.1 changes the training unit from an opening name to a position/branch in dog_matist's own persistent opening graph.

## Core changes

- `opening_nodes`: compact transposition-aware position nodes keyed by 64-bit Polyglot Zobrist BLOBs.
- `opening_edges`: move edges with visits, candidate observations, average search gap and result evidence.
- `branch_specialists`: specialists are tied to branch roots, not labels such as `Pirc` or `Grunfeld`.
- Replay examples can carry `opening_node_key` + `opening_ply`, allowing candidate training to sample a branch region.
- Explorer candidates train from under-visited but search-viable frontier branches.
- Specialist candidates train from persistent branch specialists and their bounded descendants.
- Self-play mix becomes Natural / Frontier / Specialist / Anchor. Human opening names are confined to the small anchor slice and UI/debug labels.
- Arena/League sample a mixed set of anchors + frontier positions + broad tree positions. Paired colors remain mandatory.
- Reflection no longer calls a four-ply continuation from a seeded FEN a complete “opening sequence”.

## RAM policy

The full graph is **never materialized as Python objects**. Selection queries are bounded (default 256 rows). The persistent graph lives in SQLite; cold nodes cost disk, not resident RAM. `opening_tree.ram_budget_mb` is currently a safety/documentation cap; V2.1 does not need an in-memory graph cache at all.

Default opening horizon: 16 plies.

## V2.1.1 frontier refinement

The first V2.1 snapshot retained only the top three root alternatives at every observed opening position. That was too narrow for the stated goal of discovering new but still viable branches. The current R&D snapshot uses **progressive widening**:

- first 6 plies: retain top 8 already-scored root alternatives;
- later opening plies: retain top 4;
- ordinary stochastic self-play can remain conservative while the wider alternatives become future frontier candidates.

This does **not** multiply AlphaBeta root search work. The existing searcher evaluates every legal root move before truncating the returned candidate list; V2.1.1 simply keeps more of those already-computed results near move 1.

## Frontier score

A frontier edge is eligible when it is:

1. within the opening horizon;
2. seen by search at least once;
3. played only a small number of times;
4. not too far behind the local best search move.

Selection weight combines search viability, low visit count, uncertainty, and parent support. Frontier self-play starts from the parent position and forces only the first *dog-discovered* frontier move; search is still run at that position and the replay target remains the search-best move. A current-search safety guard cancels the forced exploration move if it has become too weak. This keeps exploration separate from policy supervision.

## Promotion holdout frontier

League screening and final promotion no longer need to use the exact same opening distribution.

- **League:** may use lightly explored frontier positions because its job is cheap ranking/budget allocation.
- **Final Arena:** preferentially samples viable frontier child positions with `visits == 0` — positions that search noticed but self-play has not yet actually consumed.

Once self-play visits such a branch, it automatically leaves the strict unplayed holdout pool. This gives the promotion gate a cheap opening-generalization test without maintaining a second human-authored opening book. If the unplayed pool is temporarily too small early in training, the gate falls back to the wider frontier/broad-tree coverage rather than failing.

Default promotion mix in the R&D snapshot:

- 20% anchor coverage;
- 50% frontier, preferring unplayed child branches;
- 30% broad OpenTree positions.

## Isolated Mac smoke plan

The current snapshot includes an isolated `SMOKE_V21_OPENTREE.py` harness. It copies the live package into a temporary directory, overlays V2.1 there, sets a temporary `DARWINCHESS_HOME`, and then tests:

1. a short natural game creates opening nodes/edges;
2. OpenTree discovers a viable unplayed frontier from search alternatives;
3. the next short game starts from that parent and consumes the frontier move, subject to the current-search safety guard;
4. the branch leaves the strict unplayed holdout pool after being visited.

The live source tree and `~/.darwinchess` are not modified by this smoke harness.

## Validation in sandbox

- All modified Python files pass `py_compile`.
- Forward SQLite schema creation passes.
- Opening node/edge updates and frontier queries pass.
- Branch-specialist persistence passes.
- Bounded descendant-region expansion passes.
- Branch-focused replay sampling successfully draws examples from root + descendants.
- Strict `max_visits=0` holdout query passes: an unplayed candidate is eligible, and disappears from the holdout after the edge is actually played.
- Opening-tree memory tests: **2 passed**.

Full chess execution still must be smoke-tested on the Mac because the sandbox has no `python-chess` installation.