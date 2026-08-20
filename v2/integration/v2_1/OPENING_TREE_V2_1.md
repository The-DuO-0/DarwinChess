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

V2.1.2 tightens this rule: a strict promotion holdout must also have an unvisited child position, closing transposition leakage, and it retires after actual promotion exposure. Once self-play visits such a branch, it also leaves the strict unplayed holdout pool.

Default promotion mix in the R&D snapshot:

- 20% anchor coverage;
- 50% frontier, preferring strict unseen child branches;
- 30% broad OpenTree positions.

## Tree-health diagnostics

V2.1.2 adds compact persistent health snapshots rather than copying the graph. Metrics include node/edge counts, frontier/holdout inventory, first-move top share, Shannon entropy/effective branching, per-ply coverage, branch revisit ratio, specialist count, promotion exposures and database size. A conservative collapse warning is diagnostic only until the root has enough visits.

## V2.1.3 adaptive anti-collapse curriculum

V2.1.3 adds a conservative response layer in `dogmatist_v2/opentree_policy.py`.

The response changes **curriculum allocation**, not chess rules and not human opening preferences. When mature root statistics show probable concentration collapse, the controller gradually shifts compute toward search-viable Frontier exploration, modestly raises early stochastic temperature, and may loosen the frontier search-gap cap within a hard safety ceiling. Specialist and anchor floors remain protected.

Safeguards:

- minimum sample count before intervention;
- separate collapse/recovery thresholds (hysteresis);
- bounded per-round curriculum movement;
- convex recovery to the 45/30/15/10 baseline;
- zero-frontier fallback to Natural self-play;
- no named-opening target and no forced first move.

The corresponding unit tests are committed, but this newest controller still needs execution in CI or the isolated Mac R&D environment before integration into the evolution runtime.

## Isolated Mac smoke plan

The R&D snapshots include isolated harnesses that copy the live package into a temporary directory, overlay V2.1 there, set a temporary `DARWINCHESS_HOME`, and test natural discovery/frontier consumption without touching the live source tree or lifetime state. V2.1.2 also defines a four-round multirun gate for graph growth, rotating holdouts and health trends.

## Validation status

Previously validated in the development snapshot:

- modified Python files compiled;
- forward SQLite schema creation;
- opening node/edge persistence and frontier queries;
- branch-specialist persistence;
- bounded descendant-region expansion;
- branch-focused replay sampling;
- strict holdout/transposition leakage handling;
- health snapshot/trend logic and synthetic collapse detection.

Still required before live install:

1. execute the committed V2.1.3 policy tests;
2. run the isolated Mac python-chess smoke/multirun harness;
3. wire adaptive policy only into the isolated multirun and inspect strength + diversity together;
4. perform a longer isolated multi-generation run;
5. only then design the live V2.0.1 -> V2.1 migration.
