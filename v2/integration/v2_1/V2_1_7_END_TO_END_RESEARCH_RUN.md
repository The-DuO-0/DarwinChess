# V2.1.7 — end-to-end OpenTree research run

V2.1.6 proved two important mechanics on the real Mac in isolated state:

1. shadow promotion could defer a passing ordinary Arena without moving the durable champion, then commit only after the second gate accepted;
2. a four-round real `python-chess` OpenTree multirun grew from 116/115 nodes/edges to 383/384, consumed four frontier branches, retired four promotion holdouts, increased root effective branching from 1.0 to 4.0, and reduced top-move share from 1.00 to 0.25.

Those tests validate mechanics, not long-term chess improvement. V2.1.7 is therefore an experiment harness rather than another opening feature.

## Research-run contract

The downloadable integration snapshot contains `RESEARCH_V217_OPENTREE.py` plus a runtime helper. The harness:

- copies the live source/config into a temporary project;
- overlays V2.1.7 without modifying the live tree;
- uses a separate persistent `~/dog_matist_research/v217-.../state` rather than `~/.darwinchess`;
- freezes the starting champion as a fixed CPU reference checkpoint;
- bootstraps replay only inside research state;
- runs real self-play -> population training -> League -> ordinary Arena;
- evaluates the top shadow candidate against the fixed reference;
- when an adaptive curriculum trial is active, freezes the exact same paired start positions for the baseline champion and trial candidate;
- permits durable promotion only after the ordinary gate and fixed-reference policy guard both allow it;
- preserves branch-specialist retention independently from overall promotion;
- writes one compact JSONL trace row per round plus a final conservative report.

## Rich trace schema

V2.1.7 extends `OpenTreeRoundTrace` with experiment fields needed to diagnose a real run without loading checkpoints or the graph:

- durable champion generation;
- top candidate generation;
- promotion action (`promote`, `reject`, `defer`);
- paired fixed-reference score/game count and W/D/L fields;
- training loss;
- Natural/Frontier/Specialist/Anchor policy mix;
- policy-trial status/id/reason;
- elapsed round time;
- existing nodes/edges/frontier/holdout/effective-branching/root-concentration/branch-survival/DB-size metrics.

The JSONL reader remains backward-compatible because new fields have defaults.

## Profiles

The first Mac gate should use the **quick** profile:

- 4 rounds;
- 4 self-play games per round;
- 36 population-training steps per round;
- 8 fixed-reference paired Arena games per round;
- isolated replay bootstrap floor of 96 examples.

If that run completes without invariant failures, the **research** profile raises the experiment to 6 rounds, 6 self-play games, 72 training steps and 12 fixed-reference games per round.

These are validation budgets, not final training recommendations.

## Strength-first verdict

The final report remains deliberately conservative:

- `fail`: material fixed-reference strength regression beyond the configured budget;
- `watch`: insufficient evidence, persistent opening collapse, no net graph growth, weak branch survival, or repeated policy rollbacks;
- `pass`: strength-safe multi-round tree growth with acceptable branch persistence.

A larger or more diverse OpenTree can never override a material chess-strength failure.

## Resource policy

The full opening graph stays in SQLite. The experiment adds one frozen CPU reference model and compact scalar trace state; it does not add another MPS trainer. The one-GPU-trainer rule remains unchanged.

## Remaining gate

V2.1.7 is still not for live installation. The next required step is the isolated real-Mac **quick** end-to-end run. Only after its trace and final report are inspected should the longer research profile or preview migration be considered.
