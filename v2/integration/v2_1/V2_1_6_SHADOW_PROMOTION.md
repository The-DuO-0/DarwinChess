# V2.1.6 — Shadow promotion during adaptive curriculum trials

V2.1.4/5 gate curriculum changes with fixed-reference strength evidence. One architectural hole remained: if the normal challenger Arena promoted a model *before* the curriculum guard finished, rolling back only the curriculum would not undo an already-mutated champion.

V2.1.6 closes that hole with a shadow-promotion coordinator.

## Rule

During a normal round with no adaptive curriculum trial, promotion behavior is unchanged: the ordinary challenger-vs-champion gate decides.

During an active OpenTree policy trial, the strongest candidate remains a **shadow candidate** until two independent conditions hold:

1. it passes the ordinary challenger-vs-current-champion Arena;
2. the fixed-reference OpenTree strength guard accepts the trial.

If condition 1 fails, reject immediately. If condition 1 passes but fixed-reference evidence is incomplete, defer champion mutation. If the curriculum guard rejects, the shadow candidate must not replace the champion even when its ordinary small Arena happened to pass.

Specialist retention remains independent: a rejected shadow candidate may still contribute a statistically supported branch-specialist checkpoint/replay donor.

## Why the second gate matters

The ordinary promotion gate asks: “does this candidate look stronger than the current champion on this paired Arena?”

The curriculum guard asks a different question: “did this exploration policy preserve strength against the experiment’s fixed reference while improving or recovering OpenTree health?”

Both are required during an adaptive-policy experiment. This prevents statistical noise in one short challenger Arena from allowing an exploration-heavy trial to move the durable champion before the experiment is validated.

## New primitive

`dogmatist_v2/opentree_promotion.py` contains:

- `PromotionEvidence`
- `PromotionDecision`
- `OpenTreePromotionCoordinator`

Actions are `promote`, `reject`, or `defer`.

The module is runtime-agnostic and pure Python. The next integration step is to split the current final gate in the isolated V2.1 snapshot into “evaluate candidate” and “commit champion” so the coordinator can defer the durable mutation safely.
