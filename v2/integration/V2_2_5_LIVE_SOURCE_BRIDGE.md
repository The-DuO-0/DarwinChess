# V2.2.5 — Live dog_matist source bridge

This slice is based on the actual `dog_matist-2.0` source snapshot supplied from the Mac, not on guessed APIs.

## Confirmed live execution path

`run_night.command` launches:

```text
caffeinate -i .venv/bin/dog-matist --mode night evolve --hours <N>
```

The CLI constructs `DarwinRuntime` and calls `DarwinRuntime.evolve()`.

With League enabled, each cycle currently runs:

```text
DarwinRuntime.evolve
  -> _population_evolve_cycle_unlocked
     -> selfplay
     -> ReflectionEngine.reflect_recent
     -> start_population_round
     -> train_population
     -> PopulationArena.run
     -> _harvest_specialist_experience
     -> gate_challenger
     -> finish_population_round
```

## Important correction: live search is alpha-beta, not MCTS

The supplied production source uses `AlphaBetaSearcher` with iterative deepening, quiescence search, transposition table and optional policy move ordering. The Night profile currently uses search depth 2 and quiescence depth 3.

Therefore a Strength Lab `search_multiplier=3x` must **not** mean `depth *= 3`. Alpha-beta cost is exponential. The live bridge instead measures the normal search duration, allows at least one extra iterative-deepening ply, and applies a bounded wall-clock teacher budget.

## Existing production data is already sufficient for hard-position mining

`selfplay.play_game()` records, for each replay example:

- FEN
- final value target from the side to move
- played move
- best search move
- played move search score in centipawns
- best move score in centipawns

`LiveGameEvidenceBridge` converts these existing fields into StrengthStore evidence without changing the live GameRecord schema:

- `value_error`: disagreement between search score and final result
- `severity`: losing final outcome
- `uncertainty`: search regret between chosen and best move

The bridge skips the earliest opening plies by default to avoid over-learning deliberate stochastic opening exploration and keeps only a small number of high-priority positions per game.

## Sparse self-teacher adapter

`AlphaBetaTeacherAdapter` executes a production-compatible two-pass teacher operation:

1. Run the normal alpha-beta search at the current live depth to measure baseline cost.
2. Run iterative deepening with an extra depth allowance and a time cap equal to the requested multiplier of measured baseline cost, bounded by a hard maximum.
3. Convert the deeper score and move into a compact `TeacherReplayTarget`.

The result is suitable for conversion into the live `memory.ReplayExample` format and insertion through the existing `MemoryStore.add_game()` example path.

No Stockfish dependency is required for this route.

## Confirmed production trainer seam

`ContinualTrainer.train()` currently samples exclusively through `MemoryStore.replay_sample()`. Therefore the safest production integration is to inject teacher/hard-position examples into the same durable replay database rather than add a second training tensor pipeline.

This keeps one trainer, one optimizer path, and one replay sampler.

## Next production overlay

The next live overlay should modify the supplied Mac source in a small number of places only:

1. After `DarwinRuntime.selfplay()` persists each `GameRecord`, feed it to `LiveGameEvidenceBridge`.
2. Before `train_population()`, build a Strength Lab recipe from `StrengthStore`.
3. Execute sparse `DeepSearchTeacherRequest`s using the live `AlphaBetaSearcher` and convert results to ordinary `ReplayExample`s.
4. Add those examples to the existing MemoryStore replay path with `source='strength_teacher'` metadata.
5. Use the recipe to bias hard-position/specialist sampling while preserving the existing one-trainer design.
6. Replace the current wall-clock `deadline = monotonic() + hours*3600` behavior with the already tested active-compute clock and safe-pair drain contract.
7. Move League games behind killable worker processes before enabling watchdog enforcement in production.

## Safety

This commit does not touch the live `~/.darwinchess` database or the Gen15 checkpoint. It only adds tested adapter code on the R&D branch. A backup + dry-run migration remains mandatory before the production overlay is installed on the Mac.
