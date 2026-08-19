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
- Arena/League sample a mixed set of stable anchors + frontier positions + broad tree positions. Paired colors remain mandatory.
- Reflection no longer calls a four-ply continuation from a seeded FEN a complete “opening sequence”.

## RAM policy

The full graph is **never materialized as Python objects**. Selection queries are bounded (default 256 rows). The persistent graph lives in SQLite; cold nodes cost disk, not resident RAM. `opening_tree.ram_budget_mb` is currently a safety/documentation cap; V2.1 does not need an in-memory graph cache at all.

Default opening horizon: 16 plies. Candidate top-k recorded per observed position: 3.

## Frontier score

A frontier edge is eligible when it is:

1. within the opening horizon;
2. seen by search at least once;
3. played only a small number of times;
4. not too far behind the local best search move.

Selection weight combines search viability, low visit count, uncertainty, and parent support. Frontier self-play starts from the parent position and forces only the first *dog-discovered* frontier move; search is still run at that position and the replay target remains the search-best move. A current-search safety guard cancels the forced exploration move if it has become too weak. This keeps exploration separate from policy supervision.

## Validation in sandbox

- All modified Python files pass `py_compile`.
- Forward SQLite schema creation passes.
- Opening node/edge updates and frontier queries pass.
- Branch-specialist persistence passes.
- Bounded descendant-region expansion passes.
- Branch-focused replay sampling successfully draws examples from root + descendants.

Full chess execution still must be smoke-tested on the Mac because the sandbox has no `python-chess` installation.
