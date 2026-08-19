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

## V2.1.2 — true hidden promotion frontier

V2.1.1 used `edge.visits == 0` as the definition of an unplayed promotion frontier. That still had two leaks:

1. the same child position could already have been visited through a transposition even when this parent edge was unplayed;
2. a hidden frontier position could be reused by multiple promotion gates, turning the holdout into another fixed benchmark over generations.

V2.1.2 fixes both.

A strict promotion frontier now requires:

- the candidate edge has never been played;
- the **child position itself has zero visits**, including visits through other move orders;
- the child has never been used by a previous final promotion gate;
- the move remains within the configured search-gap viability threshold.

Promotion exposure is stored in `opening_eval_exposures`. A strict frontier child is retired from the hidden pool after it is actually evaluated. League exposure is tracked separately and may be reused a small bounded number of times because League is only a screening stage.

The final gate also distinguishes `frontier-eval-holdout` from ordinary `frontier-eval` fallback positions in game metadata, so future research/UI can measure how much of an Arena was genuinely unseen.

### Adaptive-Arena holdout preservation

Arena pre-generates a maximum schedule but may stop early after enough statistical evidence. V2.1.2 marks a hidden position as exposed **only when its paired-color games actually begin**. Unused positions at the tail of an early-stopped schedule are not burned from the holdout pool.

## Evaluation mix

- **League:** may use lightly explored frontier positions because its job is cheap ranking/budget allocation.
- **Final Arena:** preferentially samples strict unseen frontier child positions.

Default promotion mix in the R&D snapshot:

- 20% anchor coverage;
- 50% frontier, preferring strict unseen child positions;
- 30% broad OpenTree positions.

If the strict pool is temporarily too small, the gate falls back to the wider frontier/broad-tree coverage rather than failing, and the source label records that it was a fallback rather than a true hidden holdout.

## V2.1.2 tree-health research metrics

The persistent database now supports longitudinal OpenTree health snapshots. Each completed population round can record:

- total nodes and edges;
- played vs candidate-only edges;
- viable frontier inventory;
- strict promotion-holdout inventory;
- active branch specialists;
- promotion-holdout exposure count;
- mature/revisited branch ratio;
- root first-move visit count;
- root top-move share;
- root Shannon entropy and effective branch count `exp(H)`;
- per-ply node/visit coverage;
- SQLite database size;
- a conservative root-collapse warning.

The collapse warning does not fire on tiny samples. Once the natural root has enough visits, it flags a strong first-move monoculture (for example, top move share above roughly 72% or effective root branching below roughly 2.3). This is diagnostic only; it does not automatically mutate training yet.

Snapshots are stored in `opening_tree_snapshots`, and `status()` can expose recent deltas such as node growth, frontier growth, hidden-holdout growth and effective-branching change.

## Isolated Mac smoke plans

Two non-destructive harnesses exist in the local R&D snapshot:

- `SMOKE_V21_OPENTREE.py`: one natural discovery followed by one safe frontier-consumption test.
- `SMOKE_V212_MULTIRUN.py`: four isolated short rounds checking graph growth, frontier consumption, rotating promotion holdouts and health-snapshot trends.

Both copy the live package into a temporary directory, overlay the R&D files, set a temporary `DARWINCHESS_HOME`, and leave the live source tree plus `~/.darwinchess` untouched.

## Validation in sandbox

- All modified Python files and smoke harnesses pass `py_compile`.
- Forward SQLite schema creation passes.
- Opening node/edge updates and frontier queries pass.
- Branch-specialist persistence passes.
- Bounded descendant-region expansion passes.
- Branch-focused replay sampling successfully draws examples from root + descendants.
- Strict promotion holdout rejects transposition leakage.
- Promotion exposure retirement prevents hidden-position reuse.
- Opening-tree snapshot/trend deltas pass.
- Synthetic root-monoculture collapse detection passes.
- Opening-tree memory/holdout/health tests: **5 passed**.

Full chess execution still must be smoke-tested on the Mac because the development sandbox has no `python-chess` installation. V2.1.2 remains intentionally separate from the live V2.0.1 installation until those isolated checks pass.