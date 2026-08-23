# V2.2.11 Search-r2c Engine Gate

## Motivation

Gen54's deterministic opening probe showed severe shallow-search instability: depth 2 chose `h2h4`, while deeper search selected a healthy central/development move. Across the first eight plies, 6/8 best moves flipped between depth 2 and depth 3.

The r2c candidate keeps the normal depth-2 search, then spends one extra ply only when shallow evidence is uncertain. The expensive verification is limited to a bounded subset of root candidates produced by dog_matist itself. No opening book, forced move list, or Stockfish move choice is used.

## Real Mac development A/B

Frozen Gen54, identical model weights, paired colours:

- r2a broad +1 ply: 0.375 over 4 games, 1.646x time -> rejected on compute.
- r2b confidence-gated +1: 0.500 over 4 games, 1.607x time -> rejected on compute.
- r2c selective-root smoke: 0.625 over 4 games, 1.131x time -> promising.
- r2c 12-game development A/B: 0.583, W/D/L 3/8/1, node ratio 1.178x, time ratio 1.201x -> `READY_FOR_FIXED_REFERENCE_GATE`.

The root probe remained repaired: search-r1 `h2h4` -> search-r2c `e2e4`.

## Independent holdout gate

`run_search_r2_holdout_gate.py` uses a dedicated seed and explicitly excludes every opening name used in the 12-game development A/B:

- Initial position
- Nimzo-Indian
- King's Indian
- French
- Queen's Gambit
- Pirc

It then samples unique remaining curated opening starts and plays each twice with colours swapped. The checkpoint/model weights stay frozen and only the search revision changes.

For this engine-only experiment, the immutable reference is the exact frozen Gen54 model running baseline `search-r1`. Because each holdout start is colour-paired, 0.5 is the neutral reference score. The gate therefore records `fixed_reference_delta = holdout_score - 0.5`. This is an engine-revision reference delta, not a claim that the model weights changed.

The existing `EngineRevisionGate` is applied without weakening thresholds:

- reject if compute ratio > 1.60x;
- reject if fixed-reference delta < -0.03;
- require >=12 games;
- reject if A/B score < 0.48;
- accept only if score >= 0.55, fixed-reference delta >= 0, and compute ratio <= 1.30x.

The holdout harness is copy-state-only and performs no model training, champion promotion, replay write, or live-state mutation.

## Adoption rule

Even an `ACCEPT` from the holdout harness does not silently modify live production. It is evidence permitting the revision to be registered/adopted through the explicit engine-revision lifecycle, followed by a copied-state full-cycle validation before any live installation.
