# Core integration slice (from the live Mac source)

This integration plan is now based on the actual dog_matist training core supplied from the Mac on 2026-08-19, including the local `locks.py`, `reflection.py`, and `teacher.py` modules.

## Implemented in the V2 preview patch

### 1. One GPU budget, several candidates

The old cycle spent all `training.steps_per_cycle` on one challenger. The population cycle spends approximately the same optimizer-step budget as one shared base update plus short role-specific branches.

With night mode at 240 steps and population size 3 the default split is roughly 132 shared + 36 balanced + 36 explorer + 36 specialist. Only one MPS trainer is active at a time.

### 2. Faster parallel CPU self-play

Night mode can spawn CPU self-play workers while SQLite remains single-writer in the parent process. Each worker uses one Torch thread and now loads the pinned champion checkpoint **once per worker**, rather than once per game. If multiprocessing fails, the runtime falls back to the proven sequential path.

### 3. Adaptive Mac headroom

A standard-library resource controller samples load, memory headroom, and macOS thermal throttling signals before each self-play batch. Night mode can back off workers under pressure while keeping the trainer-slot invariant at exactly one. Existing POSIX `EvolutionLock` remains the lineage writer boundary.

### 4. Cheap league screening

Candidates first play paired-opening anchor games against the champion. Only the two strongest challengers receive an extra playoff pair. This avoids a full O(n^2) round robin. League games never directly promote a model.

### 5. Adaptive held-out final Arena

The V1 fixed small Arena plus Wilson confidence guard was too underpowered: with only 8–10 games it could require a very large observed edge before the confidence lower bound exceeded 0.5. V2 evaluates sequentially in paired-color batches.

- clear losers can stop early;
- clear winners can stop early once the existing confidence condition is satisfied;
- ambiguous candidates can receive up to 30 held-out games instead of being rejected merely because the sample was too small.

Promotion still requires both `score >= promotion_score` and the confidence lower bound above 0.5, and held-out Arena games are never inserted into training replay.

### 6. Specialist inheritance is donor-aware

League matches are grouped by opening. A candidate can enter the specialist archive even if it loses the overall race. The runtime then creates `specialist_selfplay` from that opening and stores those examples in lifetime replay.

The next specialist branch does not only focus the same opening name; it also preferentially samples replay whose `origin_generation` matches active specialist donors. This makes opening-specific inheritance materially stronger than merely keeping an old checkpoint on disk.

### 7. Reflection sees inherited learning

`ReflectionEngine` now treats `specialist_selfplay` as genuine self-play and reports how many recent games came from specialist inheritance, so useful failed-generation experience is not invisible in the agent's own insights.

### 8. Forward-only SQLite migration

New tables: `population_rounds`, `population_members`, `league_matches`, `specialists`.

New replay columns: `opening_name`, `opening_family`, `origin_generation`, plus the previously added search-target columns. Existing champion rows, games, replay examples, checkpoints, metrics, and insights are not reset.

### 9. Status/UI bridge

`runtime.status()` exposes the latest population round, members, active specialists, and last adaptive resource budget for the upcoming Studio Battle Royale dashboard.

## Validation performed in the development sandbox

- Every modified/new Python file passes `py_compile`.
- Forward migration from a V1-like SQLite schema passes.
- Specialist replay can be sampled by both opening and donor generation.
- Population/member/specialist persistence paths pass smoke tests.
- The supplied `EvolutionLock` correctly blocks a second writer while allowing the first writer to release cleanly.
- Full chess execution cannot be run in this sandbox because the environment lacks the `chess` package and has no network access; the user's Mac project already declares and runs that dependency.

## Safety packaging

A compact preview installer has been produced locally. It refuses to patch while the evolution lock is held, backs up modified source files, and creates a consistent SQLite backup before first live migration. A separate smoke command uses a temporary `DARWINCHESS_HOME` so doctor/status checks do not touch the real champion.

## Next validation step

Install the preview only after the current Evolution process has stopped safely, run the isolated smoke command, then run one real eco/normal population cycle before enabling an overnight V2 league run. Studio Battle Royale visualization comes after that one-cycle validation.