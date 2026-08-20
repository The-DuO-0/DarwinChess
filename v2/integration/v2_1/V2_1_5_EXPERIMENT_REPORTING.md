# V2.1.5 — OpenTree experiment reporting gate

V2.1.4 can propose, trial and roll back adaptive opening curricula. V2.1.5 adds a compact experiment trace so the Mac validation run can be judged from strength and tree-health evidence together instead of terminal impressions.

## Round trace

Each isolated round emits one JSONL row containing only aggregate scalars:

- fixed `reference_id` used by paired Arena;
- Arena score and paired game count;
- OpenTree node/edge counts;
- viable frontier and strict promotion-holdout inventory;
- root effective branching and top-move share;
- branch-survival ratio across rounds;
- SQLite database bytes;
- collapse warning;
- policy-trial id/status/reason.

The trace never serializes the opening graph itself.

## Comparability rules

A single report requires one fixed `reference_id`. If the reference champion changes, begin a new experiment report. Arena game counts must be even because strength evidence is paired-color.

## Conservative verdict

`OpenTreeExperimentReport` returns one of:

- **fail** — held-out strength falls beyond the configured loss budget;
- **watch** — evidence is too short, collapse remains, graph growth is absent, branch survival is poor, or adaptive rollbacks are frequent;
- **pass** — held-out strength is safe and the tree shows net growth with acceptable branch survival.

The verdict is intentionally not an Elo estimate and does not promote a champion. It only answers whether the OpenTree curriculum is healthy enough to advance to the next migration gate.

## Branch survival

Raw node growth alone can be misleading: a system may create thousands of branches that disappear immediately. The Mac harness should therefore compute a mature/cohort branch-survival ratio between rounds and emit it as a scalar. V2.1.5 treats persistently low survival as a `watch` condition even when total node count rises.

## Storage

JSONL is used so an overnight experiment can append one row per round without keeping historical traces in RAM. The report module can write/read the file and the standalone `ANALYZE_V215_TRACE.py` script prints a machine-readable summary.

## Next integration gate

The remaining work is to wire trace emission into the isolated real-Mac multi-round harness. That harness should keep a fixed reference model, run paired held-out Arena each round, compute the SQLite health snapshot plus branch survival, record policy trial decisions, and emit `opentree-trace.jsonl`.

Only after a real Mac trace passes should V2.1 be packaged as a preview migration over the stable V2.0.1 state.
