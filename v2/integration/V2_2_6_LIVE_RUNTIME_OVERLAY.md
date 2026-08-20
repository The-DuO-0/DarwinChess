# V2.2.6 — Live Strength Lab runtime overlay

This slice moves the Strength Lab one step closer to the supplied Mac production runtime without changing the live database or checkpoint yet.

## What is now wired

`LiveStrengthCoordinator` is built against the actual `dog_matist-2.0` seams observed in the uploaded source:

- `DarwinRuntime.memory`
- `MemoryStore.conn`
- `MemoryStore.add_game()`
- `MemoryStore.active_specialists()`
- `DarwinRuntime.champion_info()`
- `DarwinRuntime.make_searcher()`
- `config['search']['depth']`

It does not import the production package at module import time, so the V2 R&D suite stays pure-Python and independently testable.

## Saved self-play -> StrengthStore

The live `DarwinRuntime.selfplay()` currently returns game ids, not `GameRecord` objects. The overlay therefore reconstructs only the minimal record needed by `LiveGameEvidenceBridge` directly from the existing `games` + `examples` SQLite rows.

No GameRecord schema change is required.

The overlay reads:

- FEN
- final value target
- played/search move fields
- search score
- best score
- opening metadata
- source generation

and writes only selected difficult positions into the separate bounded `StrengthStore`.

## Recipe before population training

`build_recipe(targeted_examples=N)` now combines:

1. durable Strength Lab round history,
2. persistent hard-position evidence,
3. the amount of specialist replay actually present in the live MemoryStore.

The first production overlay should use a deliberately small targeted work budget (for example 32–64 positions per cycle), not `training_steps * batch_size`. Deep alpha-beta teacher searches are expensive and must remain sparse.

## Self-teacher -> existing replay path

The coordinator can execute a capped subset of `DeepSearchTeacherRequest`s with the live `AlphaBetaSearcher` and write the resulting labels through the existing `MemoryStore.add_game()` path:

```text
source = strength_teacher
termination = deep_search_self_teacher
```

`LiveReplayExample` is deliberately just a structural twin of the current production ReplayExample attributes. `MemoryStore.add_game()` reads attributes, so no second trainer tensor path is introduced.

Teacher rows retain:

- FEN
- deeper-search move
- deeper-search value target
- bounded priority / policy weight
- baseline search score
- deeper teacher score
- opening bucket metadata

The existing `ContinualTrainer` can therefore see them through the same durable replay table it already uses.

## Write safety

`run_pretraining_stage(..., persist_teacher=False)` defaults to read-only behavior for the live replay database:

- self-play evidence is mined into the separate StrengthStore;
- a recipe is produced;
- no teacher replay rows are inserted unless production explicitly opts in.

This lets us run the first Mac dry-run against copied state and inspect the exact plan before enabling new training labels.

## Exact intended production call site

In the supplied League path, the eventual narrow patch is:

```text
_population_evolve_cycle_unlocked
  -> selfplay()                       # existing, returns game ids
  -> start_population_round()         # existing
  -> LiveStrengthCoordinator.run_pretraining_stage(...)
  -> train_population()               # existing one-trainer path
  -> PopulationArena.run()
  -> final gate
```

The coordinator does not promote, rename, move, or overwrite any checkpoint.

## Still not enabled live

This commit is R&D only. Before installation on the Mac we still need:

1. a copied `~/.darwinchess` dry-run with the production package on PYTHONPATH;
2. bounded hard-position sampling in `MemoryStore.replay_sample()` / `ContinualTrainer.train()` so hard replay quotas affect selection without uncontrolled duplication;
3. active-compute clock overlay in `DarwinRuntime.evolve()`;
4. killable-process League execution for watchdog enforcement;
5. backup + validation of the live Gen15 database/checkpoint paths.

The live Gen15 checkpoint remains untouched.
