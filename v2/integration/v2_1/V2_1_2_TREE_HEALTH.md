# V2.1.2 OpenTree holdout + health validation

This R&D slice focuses on two questions that must be answered before live migration:

1. Is a supposedly hidden promotion opening actually unseen, including through transpositions and previous evaluation?
2. Is the opening tree expanding sustainably, or collapsing onto a tiny set of first-move branches?

## Hidden-frontier rules

A strict promotion frontier is eligible only when the parent edge was search-discovered, the edge was never played, the child position itself has zero visits, the move remains search-viable, and the child has never appeared in a prior promotion gate.

`opening_eval_exposures` tracks evaluation reuse separately for `promotion` and `league`. Adaptive Arena marks an exposure only when a paired-color evaluation actually starts, so positions in an unused tail of a pre-generated schedule remain fresh.

Arena metadata distinguishes strict `frontier-eval-holdout` positions from ordinary frontier fallback positions.

## Tree-health snapshot

`opening_tree_snapshots` stores compact JSON health summaries rather than copying the graph. Current metrics include node/edge counts, viable frontier and hidden holdout inventory, root top-move share, Shannon entropy/effective branching, per-ply coverage, mature branch revisit ratio, active specialists, promotion exposure count, and SQLite database bytes.

A conservative collapse warning becomes active only after the natural root has enough visits.

## Validation

Development-sandbox tests currently pass 5/5:

- branch replay/frontier persistence;
- simple unplayed holdout consumption;
- transposition leakage + promotion reuse rejection;
- health snapshots and growth deltas;
- synthetic first-move monoculture collapse detection.

The local R&D snapshot also contains `SMOKE_V212_MULTIRUN.py`, which runs four short isolated depth-1 rounds against the real Mac chess stack without modifying the live project or lifetime state.
