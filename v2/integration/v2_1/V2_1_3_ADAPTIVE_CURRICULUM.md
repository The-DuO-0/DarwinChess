# V2.1.3 — Adaptive OpenTree curriculum (R&D)

Status: **R&D only; do not install over the live V2.0.1 Mac state yet.**

V2.1.2 added diagnostics for opening-tree collapse. V2.1.3 adds the first conservative response mechanism, but deliberately avoids hard-coding a preferred human opening or forcing a particular first move.

## Principle

A collapse warning should change **where the compute budget is spent**, not declare that dog_matist must play `e4`, `d4`, `c4`, etc.

The controller therefore consumes only aggregate OpenTree health scalars:

- root visits;
- top first-move share;
- effective root branching;
- viable frontier inventory;
- strict promotion-holdout inventory;
- branch revisit ratio;
- the diagnostic collapse flag.

It never loads the graph into memory and never consumes opening names.

## Baseline mix

The default self-play budget remains:

- Natural: 45%
- Frontier: 30%
- Branch specialist: 15%
- Human anchor: 10%

When root concentration is mature enough to be credible, the controller can gradually move budget toward Frontier exploration while protecting floors for specialist inheritance and anchor coverage. Early stochastic temperature is increased only modestly, and the frontier centipawn-gap guard may loosen within a hard cap. The current search safety check still has final authority, so exploration cannot force a move that has become obviously bad.

## Anti-oscillation safeguards

- No collapse response before a minimum number of natural-root visits.
- Separate enter/exit thresholds provide hysteresis.
- Curriculum movement is capped per update.
- Recovery uses convex interpolation back toward the baseline mix, preserving a normalized budget without independent-component overshoot.
- If viable frontier inventory is empty, the Frontier budget falls back to Natural self-play instead of spinning/retrying.

## Why this is preferable to forced diversity

A forced-opening response would optimize a human-authored diversity target and could keep objectively weak branches alive merely to make a dashboard look balanced. V2.1.3 instead asks the model to spend more search/self-play effort on underexplored *search-viable* regions. If one first move is genuinely much stronger for the current model, OpenTree is allowed to remain uneven; the controller only reacts when concentration and effective branching indicate probable training collapse rather than demonstrated strength.

## Current implementation

`v2/dogmatist_v2/opentree_policy.py` contains:

- `TreeHealth`
- `CurriculumMix`
- `OpenTreePolicy`
- `OpenTreeCurriculumController`

`v2/tests/test_opentree_policy.py` covers nominal behavior, collapse response, hysteresis/recovery, zero-frontier fallback, and small-sample protection.

These tests are committed but still need execution in CI or the isolated Mac R&D environment before this controller is wired into the live evolution runtime.

## Next integration gate

After test execution, connect the controller to the isolated V2.1 multirun harness only. Log, per round:

1. health snapshot before policy update;
2. resulting source mix / temperature scale / frontier-gap cap;
3. nodes/edges/frontier/holdout after the round;
4. root entropy/effective branching trend;
5. chess-strength proxy so diversity is never optimized independently of playing quality.

Only after a multi-round isolated run shows stable behavior should the adaptive policy become eligible for a live V2.1 migration.
