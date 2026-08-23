# V2.2.7 — Live evolution runner

This slice composes the real-source adapters into one non-invasive execution path for the supplied `dog_matist-2.0` runtime.

## What changed

### 1. Training replay can now be intercepted without editing `trainer.py`

`LiveReplayOverride` temporarily replaces the live `MemoryStore.replay_sample` bound method while the existing `ContinualTrainer` runs.

It preserves the trainer's current arguments:

- `recent_fraction`
- `opening_names`
- `opening_fraction`
- `generations`

so explorer/specialist population branches keep their opening identity.

The Strength Lab mixer selects:

- original hard-position replay rows by FEN;
- specialist rows by the live `origin_generation + opening_name` metadata;
- self-teacher rows by `games.source='strength_teacher'`;
- ordinary lifetime replay as the fallback.

No second optimizer or tensor pipeline is introduced.

### 2. Full selfplay -> Strength -> unchanged train_population seam

`LiveStrengthCycleOverride` wraps only two methods on the existing `DarwinRuntime` instance:

```text
selfplay()
train_population()
```

It remembers the game ids returned by self-play. Immediately before `train_population`, it:

1. mines difficult positions from the already-saved live SQLite examples;
2. creates the Strength Lab recipe;
3. optionally runs bounded alpha-beta self-teacher requests;
4. temporarily routes the unchanged production trainer through the Strength replay mix.

The wrapper restores the original methods on exit.

By default it **fails open**: if the experimental adapter raises, the original production training path still runs so an overnight session is not wasted. Strict mode exists for copied-state validation.

### 3. Active compute clock is suspension-aware

`HeartbeatComputeClock` uses a small background heartbeat rather than trusting platform-specific wall/monotonic sleep semantics.

While the process is runnable, heartbeats continue and time counts toward the budget. During lid-close, system sleep, SIGSTOP-like process suspension, or another long process suspension, the heartbeat cannot run; the long gap is excluded on resume.

A conservative threshold prevents ordinary scheduling jitter, alpha-beta search, PyTorch work, or child-process waits from being treated as sleep.

### 4. League now has a real color-pair drain seam

The supplied production `PopulationArena._play_paired_set` already guarantees one opening seed is played twice with colors swapped.

`LiveLeagueDrainOverride` subclasses that real implementation dynamically and calls it **one seed at a time**:

```text
opening A: candidate White
opening A: candidate Black
-- pair boundary --
opening B: ...
```

If the compute budget expires during opening A's first game, the reverse-color game still finishes. Opening B is never admitted.

A partial League also:

- does not mint new specialists;
- skips specialist-harvest self-play;
- skips the final promotion gate;
- leaves the current Champion untouched.

No chess/game implementation is copied.

### 5. `LiveEvolutionRunner`

The new runner calls the existing `DarwinRuntime.evolve_cycle()` instead of `DarwinRuntime.evolve(hours=...)`.

This avoids the current production wall deadline:

```python
deadline = monotonic() + hours * 3600
```

and replaces it with the suspension-aware active compute clock.

Conceptually:

```text
Heartbeat active-compute clock
        |
        +-- Strength cycle override
        |     selfplay -> mine -> teacher -> replay mix -> unchanged trainer
        |
        +-- League drain override
        |     finish current color pair -> no new pair
        |
        +-- existing DarwinRuntime.evolve_cycle()
```

## Exact future production shape

Against a copied Mac state, the adapter can be exercised as:

```python
with StrengthStore(copy_root / "strength_lab.sqlite3") as store:
    strength = LiveStrengthCoordinator(runtime, store)
    runner = LiveEvolutionRunner.from_hours(
        runtime,
        10,
        strength_coordinator=strength,
        targeted_examples=64,
        teacher_request_cap=8,
        persist_teacher=False,  # first dry run
    )
    report = runner.run()
```

The first validation run intentionally keeps teacher persistence disabled. Hard-position mining and recipe construction can be inspected before allowing any new replay labels.

## Important remaining limitations

This is still **not installed on the live Gen15 state**.

Two production gaps remain before the runtime-safety promise is complete:

1. The final held-out `Arena.compare()` is still an internal pair loop. The current guard will skip that Arena if the budget is already exhausted before it begins, but if the budget expires *after* the final Arena starts, the production Arena can still finish more than the current pair. We need the same pair-boundary callback/process adapter there.
2. The supplied production `PopulationArena` is still sequential. Generic V2 scheduling/watchdog primitives exist, but the real 2–3 concurrent League worker-process bridge has not yet replaced the synchronous live loop.

Those are the next runtime integration targets.

The unique Gen15 checkpoint and live `~/.darwinchess` database remain untouched.
