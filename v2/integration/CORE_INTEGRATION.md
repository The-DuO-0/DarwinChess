# Core integration slice (from the live Mac source)

This is the first patch plan against the actual dog_matist training core supplied from the Mac on 2026-08-19. It is staged separately because the public repository currently contains Studio but not every live core module (`locks.py`, `reflection.py`, `teacher.py`, `dialogue.py`, `exporter.py` are still local-only).

## What is now implemented in the integration patch

### 1. One GPU budget, several candidates

The old cycle spent all `training.steps_per_cycle` on one challenger. The population cycle spends approximately the same number of optimizer steps as:

- a shared base update (default 55% of the old budget), then
- short role-specific branches whose combined fine-tune steps consume the remainder.

With `night.training_steps_per_cycle = 240` and population size 3 this becomes roughly:

- 132 shared steps
- 36 balanced steps
- 36 explorer steps
- 36 specialist steps

Total: 240 optimizer steps. Only one MPS trainer is active at a time, so several full GPU trainers never fight over Apple Silicon memory bandwidth.

### 2. Parallel CPU self-play at night

Night mode can spawn three CPU self-play processes. Every worker pins Torch to one thread and loads the same champion checkpoint independently. SQLite is written only by the parent process. If process spawning fails, the runtime falls back to sequential self-play instead of killing the overnight run.

### 3. Cheap league screening + unchanged final gate

Candidates first play paired-opening anchor games against the champion. Only the two strongest challengers receive an extra playoff pair. This is intentionally not a full O(n^2) round robin.

The league never promotes directly. The strongest challenger still has to pass the existing held-out `Arena.compare()` promotion rule, preserving the atomic champion safety boundary.

### 4. Specialist inheritance is real replay, not just an archived file

League matches are grouped by opening. A candidate that has a large enough opening-specific edge can be written to the specialist archive even if it loses the overall promotion race.

For each newly detected specialist, the runtime creates a small amount of self-play from that opening using the specialist checkpoint and inserts those examples into lifetime replay as `specialist_selfplay`. Future explorer/specialist branches can explicitly sample those opening buckets.

That means a failed generation can influence descendants without neural-weight averaging.

### 5. Forward-only SQLite migration

New tables:

- `population_rounds`
- `population_members`
- `league_matches`
- `specialists`

New replay columns:

- `opening_name`
- `opening_family`
- `origin_generation`

Existing champion rows, games, replay examples, checkpoints, metrics, and insights are not reset.

### 6. Status/UI bridge

`runtime.status()` is extended to expose the latest population round, its members, and active specialists so Studio can render a league/battle-royale dashboard without inventing a second state store.

## Validation performed in the development sandbox

- Every modified/new Python file passes `py_compile`.
- SQLite migration, population/member persistence, opening-tagged replay sampling, league-match persistence, population status lookup, and specialist upsert/query paths pass a local smoke test.
- Full chess execution was not run in the sandbox because the sandbox Python environment does not have the `chess` package installed and has no network access to install it. The Mac project already declares `chess==1.11.2` in `pyproject.toml`.

## Still needed before replacing the live core

We need the small local-only modules used by the actual runtime/CLI (`locks.py`, `reflection.py`, `teacher.py`; later `dialogue.py`/`exporter.py` for a complete source snapshot) so the branch can be assembled and smoke-tested as a runnable package instead of a patch set.
