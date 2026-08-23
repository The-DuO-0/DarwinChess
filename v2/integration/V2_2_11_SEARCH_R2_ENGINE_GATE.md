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

## Real Mac independent holdout result

The first independent holdout used six unseen starts:

- Slav
- Open Game
- QGD
- Scandinavian
- Grunfeld
- Caro-Kann

Result on frozen Gen54:

- score: 0.417
- W/D/L: 0/10/2
- fixed-reference delta vs frozen search-r1: -0.083
- node ratio r2c/r1: 0.967x
- time ratio r2c/r1: 0.957x
- engine gate: `REJECT` because fixed-reference strength regressed

Both decisive losses occurred in the Slav pair; all other holdout games were draws. This is not statistical proof that r2c is globally weaker, but the gate is intentionally conservative and therefore r2c is **not adoptable**.

The failed holdout is now consumed diagnostic data. It must not be reused as the final acceptance holdout for a later revision.

## Slav failure forensics

The real Mac Slav replay captured four unique positions where r2c spent selective +1 search. Comparing r1 depth 2, the r2c move, and a fresh full-root depth 3 on the exact same FENs produced:

- helpful flips: 1
- harmful flips: 0
- same as full depth 3: 1
- both differ from full depth 3: 2
- r2c/full-depth3 move match rate: 0.500
- r1/full-depth3 move match rate: 0.250
- mean r2c regret vs full depth 3: 29.4 cp
- mean r1 regret vs full depth 3: 49.3 cp

The most important observation is **zero harmful flips**. In the captured failure positions r2c was, on average, closer to full depth 3 than r1, yet the candidate still lost both Slav games. Therefore the first holdout failure cannot be explained simply as "selective-root picked the wrong deeper move".

This points to a second failure mode: an opening move that is locally preferred by deeper search may hand the game to a shallower continuation policy that cannot exploit or safely maintain the resulting position. Full depth 3 is also only a diagnostic reference, not ground truth for winning chess.

## Counterfactual handoff probe before r2d

`run_search_r2_handoff_probe.py` consumes the failure-forensics JSON and tests only positions where r1 and r2c actually chose different moves. For each divergence it creates two counterfactual branches:

1. force the r1 move;
2. force the r2c move.

After the forced move, **both sides use the same search-r1 continuation policy**, first at depth 2 and then at depth 3. This removes the original asymmetric r1-vs-r2c match from the continuation and asks a causal question: did the opening move itself improve the position for the policy that inherits it?

Each divergence is classified as:

- `candidate_supported`: r2c branch is not worse under either common continuation;
- `continuation_mismatch`: r2c branch is worse under shallow continuation but not under deeper continuation;
- `candidate_harmful`: r2c branch is worse under both common continuations;
- `mixed`: shallow continuation likes r2c but deeper continuation does not.

A `continuation_mismatch` result would support a new r2d design based on safe handoff/phase consistency rather than another arbitrary opening threshold. A `candidate_harmful` result would instead mean full-depth3 agreement was an unreliable local teacher. `candidate_supported` would suggest that the two Slav losses are more likely a small-sample or multi-trigger interaction and should not be used to overfit r2d.

No r2d policy should be tuned until this counterfactual diagnosis is available. Slav and the first holdout set remain consumed diagnostic data and must stay excluded from the next final holdout.

## Adoption rule

Even an `ACCEPT` from a future untouched holdout does not silently modify live production. It is evidence permitting the revision to be registered/adopted through the explicit engine-revision lifecycle, followed by a copied-state full-cycle validation before any live installation.
