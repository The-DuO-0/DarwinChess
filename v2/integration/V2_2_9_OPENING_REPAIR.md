# V2.2.9 Opening Repair Lab

## Why this exists

The production Champion can be strong overall while still entering some openings badly. The first live Strength bridge deliberately skipped the first six plies so stochastic self-play exploration was not mislabeled as a mistake. That protected exploration, but it also created a blind spot: persistent early-position errors could fail to receive enough targeted repair work.

V2.2.9 adds a separate opening-evidence lane. It does **not** add an opening book.

## Core rule: labels are not moves

`opening_name` / `opening_bucket` is only a telemetry and curriculum label. No named opening injects a legal move into AlphaBeta. Search still chooses every move.

For games that do not map to a known/named opening, the first short move trace receives a stable `frontier:<hash>` bucket. Novel openings therefore remain measurable and trainable instead of being discarded as `unknown`.

UI payloads explicitly expose:

- `book_moves_injected = false`
- `novel_openings_allowed = true`

## Early opening evidence

`LiveGameEvidenceBridge` now has two lanes:

1. ordinary hard-position lane: still skips the stochastic opening window;
2. opening lane: observes roughly the first 12 plies and persists only sufficiently strong early value/failure evidence.

A deliberate stochastic move is not treated as a policy error. Production replay stores both `move_uci` (search-best) and `played_move_uci` (actual exploration move). If they differ in the early lane, played-vs-best centipawn regret is suppressed. Value error and repeated failure can still identify a genuinely bad early position.

This distinction is essential: exploration must create new openings without the repair system immediately punishing the experiment for being different.

## Weakness evidence

`OpeningWeaknessController` combines two sources:

- current-Champion specialist gap: a preserved specialist that was actually measured against the **current** Champion and performs materially better in one opening;
- persistent early-opening hard-position pressure from `StrengthStore`.

Historical specialist evidence against an old Champion is never reused as proof that the current Champion has the same weakness. Old specialists remain valuable replay/donor/sparring assets, but their historical score is not silently reinterpreted.

`StrengthStore.opening_bucket_stats()` intentionally aggregates only the dedicated `*_opening` evidence lane. A middlegame blunder in a game labeled `Queen's Gambit` does not by itself prove that the Queen's Gambit opening was bad.

## Repair curriculum

When opening evidence is strong enough, the Strength recipe reserves part of the targeted hard-position and deep-self-teacher quota for up to three weak opening buckets.

Default focus fraction: **60%**.

Hard safety ceiling: **75%**.

The remaining targeted quota prefers other opening buckets. If diverse evidence is unavailable, the system backfills with natural self-play rather than silently turning 100% of training into one opening drill.

This gives the system an exploitation/exploration balance:

```text
weak opening evidence
        |
        +--> targeted early hard replay
        +--> deeper AlphaBeta self-teacher requests
        +--> preserved specialist examples/donors
        |
        +--> broad natural self-play remains alive
        +--> other opening buckets retain quota
        +--> frontier/new openings remain allowed
```

## What happens to Gen54

The live/frozen Gen54 checkpoint is never overwritten in place. Opening repair changes the training pressure on descendants inherited from the current Champion. A repaired descendant must still survive League/Arena/promotion before it can replace Gen54.

So the intended path is:

```text
Gen54 Champion
  -> expose early-opening weaknesses
  -> descendants train on focused evidence
  -> specialists contribute useful traits/examples
  -> held-out evaluation
  -> only a proven descendant replaces Gen54
```

This preserves the safety property that the Champion is immutable until a challenger proves itself.

## Current validation status

Pure-Python tests cover:

- early opening failures are captured;
- deliberate stochastic move mismatch is not counted as policy surprise;
- unnamed openings receive stable frontier buckets;
- opening statistics ignore ordinary later-game hard rows;
- focused recipes preserve exact batch totals and keep non-focused openings represented;
- opening focus cannot exceed 75%;
- stale specialist evidence measured against an old Champion is ignored for current weakness targeting.

The feature still needs a copied-state Mac run to observe Gen54's real opening buckets before live installation. Teacher replay persistence remains independently gated OFF until its dedicated copied-state write validation passes.
