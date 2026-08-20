# V2.1.4 — Strength-gated adaptive OpenTree curriculum

V2.1.3 can react when the opening tree collapses, but diversity is not the primary objective. V2.1.4 adds a two-phase policy rollout so an exploration-heavy curriculum must preserve chess strength before it is allowed to persist.

## Rule

A curriculum change is first a **trial**, never an immediate permanent setting.

1. Record baseline held-out Arena score and OpenTree health.
2. Apply the proposed curriculum for one bounded training window.
3. Run paired held-out evaluation against the same fixed reference.
4. Compare strength first, diversity second.
5. Accept the trial only if it stays inside the configured strength-loss budget and provides useful evidence; otherwise roll back to the baseline policy.

Training loss is explicitly not a strength metric.

## Guard evidence

`TrialEvidence` currently records only bounded scalar evidence:

- paired Arena score and game count;
- a `reference_id` for the fixed comparison opponent;
- effective opening branches;
- viable frontier inventory;
- whether the baseline tree is already in a collapse state.

Baseline and trial evidence are rejected as non-comparable if the Arena reference changed. Arena game counts must also be even, which protects the paired-color assumption at the data boundary. No opening graph is loaded into RAM.

## Default safety behavior

- Fewer than 12 held-out games in either baseline or trial evidence: do not promote a policy change.
- Strength drop worse than 0.06 score: reject even if diversity improves dramatically.
- A strength-safe trial can remain active while recovering from an already-collapsed tree, because entropy may lag behind training.
- Outside collapse recovery, a trial should either produce a measurable diversity gain or a clear strength gain.
- Rejected policies trigger a short cooldown before another adaptive trial can start.
- Policy trials cannot overlap.
- Changing the Arena reference invalidates the score delta instead of silently comparing unlike evaluations.

These thresholds are R&D defaults, not final research claims. They will be calibrated from the isolated Mac multi-round experiment.

## Why this matters

Without this gate, an anti-collapse controller could accidentally optimize for a beautiful opening tree while weakening the actual chess player. V2.1.4 makes the objective lexicographic:

1. preserve/improve chess strength;
2. among strength-safe policies, prefer broader and healthier opening coverage.

## New primitives

- `dogmatist_v2/opentree_guard.py`
  - `TrialEvidence`
  - `GuardDecision`
  - `OpenTreeStrengthGuard`
- `dogmatist_v2/opentree_trials.py`
  - `PolicyTrial`
  - `TrialResult`
  - `OpenTreePolicyTrialManager`

The trial manager implements rollback and rejection cooldown. It is intentionally runtime-agnostic so it can be wired first into the isolated Mac harness before touching the live V2.0.1 state.

## Validation state

The pure-Python guard logic has been manually exercised against the principal decision cases: strength regression, safe diversity gain, insufficient evidence, collapse recovery, clear strength gain, no material gain, reference mismatch, and invalid unpaired game counts. Repository unit tests have been added for both the guard and trial manager; full test-suite execution remains part of the next isolated validation gate.
