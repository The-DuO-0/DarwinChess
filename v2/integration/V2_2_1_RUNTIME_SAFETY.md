# V2.2.1 — active compute budget, parallel League, watchdog and safe drain

This slice fixes the runtime-control bugs found in the previous long-run build.  It is part of the V2.2 R&D branch and is intentionally implemented as reusable primitives before touching the live `~/.darwinchess` state.

## 1. Ten hours means active computation, not wall time

Long runs now use `ComputeBudgetClock` rather than a wall-clock deadline.

- the budget advances while the run is active;
- explicit pause/suspend time does not consume the configured budget;
- UI payloads expose `elapsed_compute_seconds` and `remaining_compute_seconds`;
- the payload explicitly declares `wall_sleep_counts: false` so Studio does not present the value as elapsed real-world time.

The Mac integration should pause the clock whenever the experiment itself is paused and resume it with the worker set.  `time.monotonic()` is used as the default time source so wall-clock corrections cannot move the budget.

## 2. League concurrency is 2–3 games

`ResourceBudget` now has a dedicated `league_games` lane rather than overloading Arena workers.

- minimum: 2 concurrent League games;
- maximum: 3 concurrent League games;
- adaptive resource control may move between 2 and 3 based on CPU/memory/thermal headroom;
- MPS training remains exactly one trainer slot.

The scheduler rejects any League concurrency outside 2–3.

## 3. Per-game progress visible to Studio

Every active League game snapshot contains:

- game id and colour-pair id;
- colour leg (1 or 2);
- White / Black generation ids;
- opening tag when available;
- current ply count;
- completed full-move count;
- active runtime in seconds;
- state.

`ui_flow.encode_ui_event()` emits a one-line `DOGMATIST_UI {...}` event that can coexist with normal stdout.  Studio should parse only this prefix for structured progress while continuing to display ordinary logs.

## 4. Single-game watchdog

`GameWatchdog` has two independent limits:

1. hard game runtime;
2. no-move-progress timeout.

Repeating the same ply count does not reset the stall timer.  When a trip occurs, `LeaguePairScheduler.poll_watchdogs()` marks the game `timed_out` and returns a `WatchdogTrip`.

**Important integration rule:** each League game must run behind a killable worker-process boundary.  The caller must terminate/kill the corresponding worker on a watchdog trip.  Cancelling a Python future alone is not accepted because a wedged engine/search call can ignore it forever.

A timed-out game is terminal evidence for that colour leg and cannot block the scheduler indefinitely.

## 5. Budget expiry drains only current colour pairs

The previous loop could reach the time limit and then continue a large outer cycle.  V2.2.1 changes admission semantics.

When the compute clock expires:

1. scheduler enters `draining`;
2. no **new** opponent pairing may start;
3. if a pairing already started, its missing reverse-colour leg is still allowed to run;
4. watchdog remains active while draining;
5. once every already-started pair has both colour legs terminal and no games remain active, `safe_to_stop == true`;
6. the outer evolution controller must stop immediately instead of entering Arena / promotion / another round unless those operations are required to atomically commit already-produced state.

This makes the safe boundary a colour-balanced pair, not an entire tournament or evolution round.

## 6. New Studio flow

The Evolution page should render the V2 pipeline as:

`Self-play → Population train → League (2–3 parallel games) → Arena → Fixed-reference strength guard → Promote / Reject → Archive + Chronicle → Next round`

During League, Studio additionally renders one live row/card per game with:

`White vs Black | colour leg | move/ply | runtime | opening | state`

The top run clock is labelled **Compute time** and shows both used and remaining budget.  It must not be labelled wall time.

When the budget is exhausted, the banner changes to:

> Compute budget reached — finishing the current colour pair(s), then stopping safely.

No new round should become highlighted after that point.

## Validation added in this slice

Pure-Python tests cover:

- an eight-hour paused/sleep interval consuming zero compute budget;
- three-game League admission;
- drain mode completing the missing reverse-colour leg but never opening a new pairing;
- automatic budget-expiry drain;
- stall watchdog terminal state;
- UI payload containing current plies/full moves/runtime;
- adaptive resource budget remaining inside the 2–3 League safety band.

## Remaining production wiring

The repository's historical Studio upload contains `app.py` imports for `pages.evolution`, but the `pages/` source directory itself was never committed to GitHub.  Therefore this branch provides the structured UI protocol and exact flow contract now; the final PySide Evolution-page wiring must be overlaid from the complete local Studio source (or that missing page source must first be committed) before the next installable Mac snapshot is produced.
