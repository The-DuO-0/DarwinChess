# V2.2.4 — Finish the chess game; freeze the ruler

## 1. A run budget is not a chess-game timeout

The requested 8/10-hour Night budget is an **admission budget** only.

When active compute reaches the budget while a League/Arena/reference game is in progress:

1. Do **not** terminate the game.
2. Let the current game finish naturally.
3. If its reverse-colour mate belongs to an already-started pairing, let that mate finish too.
4. Do not admit a new pairing after drain begins.
5. Never use incomplete colour-pair evidence for rating, specialist creation, or Champion promotion.

Therefore a 10-hour run is allowed to finish at 10h + the natural tail of the already-started fair pairing. This is intentional.

The same rule applies to a first Ctrl-C safe-stop request. A second Ctrl-C remains the explicit emergency escape hatch.

## 2. The watchdog is a separate bug detector

A worker is force-stopped only by an independent, deliberately generous watchdog. Current production defaults:

- no completed move/search progress for **30 minutes** -> `no_move_progress_timeout`;
- one game reaches **2 hours** -> emergency abnormal-game ceiling;
- terminate, wait **2 seconds**, then kill only if the worker still exists.

These numbers are **not** derived from remaining Night time. A run with 3 seconds remaining still allows a healthy game to finish. A run with 8 hours remaining can still kill a worker that has clearly wedged for 30 minutes.

The policy is installed temporarily in the live overlay and the user's original config values are restored when the run exits.

## 3. Frozen Strength Reference

A stable Champion can hide progress: Gen15 may remain on the throne while Gen40, Gen41 and Gen42 get progressively closer.

V2.2.4 therefore adds a second ruler:

- before the first V2 live cycle, copy the current Champion checkpoint into `frozen_strength_reference/`;
- hash it with SHA-256 and write a tiny manifest;
- never replace it automatically when the Champion changes;
- verify the hash before reuse;
- evaluate the strongest League subject of each round against the same frozen checkpoint on paired colours;
- persist the resulting score into the existing `StrengthStore.strength_rounds` history.

The reference checkpoint is a copy. The original/live Champion checkpoint is never edited.

A frozen Gen15 and a later live Gen15 are intentionally given different internal participant identities during the reference games. This prevents the worker task from accidentally loading the live checkpoint for both sides merely because both have historical generation number 15.

## 4. Low-overhead first gate

The initial copied-state default is **2 colour pairs / 4 games per completed round**. This is a trend meter, not a statistically conclusive rating match. Longer validation can increase the pair count after measuring Mac cost.

If the run budget is already exhausted before the reference measurement begins, the measurement is skipped. If the budget expires during a reference pairing, that pairing finishes naturally and then drains exactly like League.

Fixed-reference integration is fail-open during copied-state validation: if the new meter cannot resolve a production checkpoint/opening interface, ordinary evolution continues and the error is surfaced instead of wasting the overnight run.

## 5. Why this matters for a long-lived Champion

The two progress axes now remain separate:

- **Throne:** did anyone actually beat the current Champion under the promotion gate?
- **Civilization strength:** is the best population subject improving against one immutable historical ruler?

A long Gen15 reign is therefore no longer automatically interpreted as either success or stagnation.

## 6. Current validation boundary

Pure-Python tests cover:

- compute-budget expiry does not time out active games;
- generous watchdog thresholds install and restore cleanly;
- frozen checkpoint immutability/checksum verification;
- complete colour-pair scoring only;
- live Gen15 vs frozen Gen15 uses distinct worker identities.

The remaining hard gate is still a **copied-state real-Mac run** with the uploaded production source and copied checkpoint/database paths. Do not install into the live state before that gate passes.
