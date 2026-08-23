# V2.2.2 — Strength Lab: keep improving after a dominant Champion

A long-lived Champion is useful evidence, but it must not turn the project into generation churn around the same strength ceiling. V2.2 therefore treats **model generation** and **engine revision** as two separate axes of progress.

## Core rule

`Gen15 stays Champion` does **not** mean `training is successful`.

A round is considered healthy only when at least one of these is moving:

- fixed-reference strength;
- promotion strength against the reigning Champion;
- specialist strength on retained opening/position buckets;
- a separately A/B-tested engine/search revision.

If several sufficiently-tested rounds show neither promotion nor material fixed-reference gain, the run enters **plateau mode** rather than continuing the same loop indefinitely.

## Strength Lab curriculum

Normal mode uses a modest amount of targeted work:

- 55% natural self-play;
- 20% hard-position replay;
- 15% retained-specialist sparring;
- 10% deep-search teacher positions.

Plateau mode shifts compute toward places the current Champion does not understand well:

- 40% natural self-play;
- 30% hard-position replay;
- 15% retained-specialist sparring;
- 15% deep-search teacher positions.

These are initial R&D defaults and must remain configurable after real-Mac profiling.

## Hard-position mining

The trainer should retain compact position records from losses, unstable draws and high-error decisions. Priority combines:

- bad game outcome from the model's perspective;
- value prediction error versus the eventual result;
- policy surprise/uncertainty;
- repeated failure on the same position family.

Selection is deduplicated and capped per opening bucket so one recurring failure cannot consume the whole replay budget.

## Sparse deep-search self-teaching

The project does not need an external pretrained chess engine as its teacher. Instead, a small fraction of selected difficult positions are re-analysed by the **same dog_matist engine with a larger search budget**.

Normal mode starts at roughly 2x search on 10% of selected hard positions. Plateau mode starts at roughly 3x search on 15%. The resulting stronger policy/value targets are distilled back into the trainable network.

This is intentionally sparse: the Mac should spend extra compute where it is informative, not make every self-play move 3x slower.

## Engine revision track

Search/runtime changes are versioned independently from generations. Example:

`Gen15 + search-r1` -> `Gen15 + search-r2 candidate`

The model weights are frozen while the search revision is tested. A revision is adopted only after paired-colour A/B games show it is stronger, fixed-reference strength does not regress, and compute growth remains inside the Mac budget.

This separation is important: otherwise a stronger generation can hide a worse search algorithm, or a better search implementation can be mistaken for a better trained network.

The initial conservative gate is:

- at least 12 paired A/B games before adoption;
- candidate score >= 55% against baseline;
- no fixed-reference regression;
- preferred compute-cost ratio <= 1.30x;
- hard reject beyond 1.60x compute cost or material fixed-reference regression.

These thresholds are R&D defaults, not claims of statistical certainty. Longer validation should be used before a major engine revision becomes permanent.

## UI

Evolution now exposes a dedicated Strength Lab step:

`Self-play -> Strength Lab -> Population train -> League (2-3) -> Arena -> Strength guard -> Promote/Reject -> Archive + Chronicle -> Next round`

The Strength Lab payload reports:

- normal vs plateau mode;
- curriculum mix;
- deep-search teacher fraction;
- teacher search multiplier;
- reason the mode was selected.

A future Engine Lab card should additionally show the current engine revision, candidate revision, A/B score, fixed-reference delta and compute-cost ratio.

## Production integration still required

The pure-Python planner, plateau detector, hard-position selector, engine revision gate and UI protocol are now testable in isolation. The real Mac trainer still needs adapters that provide:

1. per-position value/policy difficulty signals;
2. compact hard-position persistence;
3. a way to request deeper analysis from the existing search implementation;
4. paired A/B execution with identical model weights and starts;
5. replay weighting that consumes the Strength Lab curriculum without loading archived models into RAM.

Until those adapters are wired, Strength Lab is an R&D control layer rather than a claim that the live installed engine is already stronger.
