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

## Failure forensics before r2d

`run_search_r2_failure_probe.py` replays one or more failed holdout openings (default: Slav), records every position where r2c actually spends selective +1 search, and then analyzes those exact FENs three ways:

1. baseline search-r1 at depth 2;
2. the move r2c selected during the game;
3. a fresh full-root depth-3 search with stabilization disabled.

For every stabilization it classifies the change as:

- `helpful_flip`: r2c matches full depth 3 while r1 does not;
- `harmful_flip`: r1 matches full depth 3 while r2c does not;
- `same_as_full`: both match full depth 3;
- `both_differ_from_full`: neither matches full depth 3.

It also reports candidate and baseline regret in centipawns relative to the full depth-3 best move. This distinguishes two very different failure modes:

- the selective-root approximation chose the wrong deeper move, suggesting a safer replacement rule or a better verification set;
- full depth 3 itself prefers the r2c move, suggesting the loss is not simply a selective-root bug and the opening policy/trigger needs a different treatment.

No r2d policy should be tuned until this diagnosis is available. Once Slav is used for failure analysis, the next final holdout must exclude both the original development openings and this first holdout set.

## Adoption rule

Even an `ACCEPT` from a future untouched holdout does not silently modify live production. It is evidence permitting the revision to be registered/adopted through the explicit engine-revision lifecycle, followed by a copied-state full-cycle validation before any live installation.
