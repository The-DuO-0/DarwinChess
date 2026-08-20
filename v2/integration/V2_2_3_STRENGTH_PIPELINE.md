# V2.2.3 — Strength Lab production integration contract

This slice turns the earlier Strength Lab policy into persistent evidence and an executable training recipe. It still does **not** claim that the installed Mac engine is stronger until the real trainer/search adapters are wired and measured.

## Persistent strength memory

`StrengthStore` is a small SQLite store that never loads model checkpoints. It records:

- fixed-reference round evidence used by the plateau detector;
- deduplicated hard positions, keyed from the first four FEN fields so move clocks do not create duplicates;
- per-opening-bucket bounded retention so one repeated opening failure cannot grow without limit;
- engine revision metadata and A/B trial results;
- the currently adopted engine/search revision.

This keeps strength-growth memory cheap in RAM and small on disk.

## Exact curriculum recipes

`StrengthLabPlan.batch_budget(N)` converts the curriculum fractions into exact integer quotas with deterministic largest-remainder allocation. `StrengthPipelinePlanner` then builds a real recipe:

- natural self-play examples;
- hard-position replay examples;
- specialist-sparring examples;
- sparse deep-search-teacher requests.

If the hard-position pool or specialist pool is too small, the missing quota is backfilled with ordinary self-play instead of blocking the overnight run or fabricating evidence. The total requested training size is preserved exactly.

## Deep-search teacher contract

Each `DeepSearchTeacherRequest` contains a FEN, opening bucket, source generation and a search multiplier. The production adapter must:

1. run the **same dog_matist model** with the requested larger search budget;
2. collect improved policy/value targets from that deeper search;
3. write those targets into replay using a dedicated provenance tag;
4. count the extra search work against the active compute budget;
5. never silently substitute an external pretrained chess engine.

The controller currently requests roughly 2x search in normal mode and 3x in plateau mode, only on a sparse subset of high-value positions.

## Hard-position ingestion contract

The real match/trainer trace should feed positions after games with at least these signals when available:

- FEN;
- opening bucket / branch id;
- source generation;
- source kind (`selfplay_loss`, `league_loss`, `arena_loss`, `value_miss`, etc.);
- severity / game-loss pressure;
- policy uncertainty or surprise;
- value prediction error.

The current persistence layer accepts generic scalar scores so we can wire the exact production metrics once the live trainer source is available.

## Engine/search revision A/B contract

`EngineABTrialPlan` guarantees the important invariant for engine evolution:

- one frozen model checkpoint;
- one baseline search revision;
- one candidate search revision;
- the exact same start positions;
- two games per position with colours swapped.

Only search/runtime behavior changes. Model weights stay fixed, so an accepted gain can be attributed to the engine revision instead of a lucky new generation.

After the paired games, `EngineRevisionGate` decides accept/reject/defer using strength and compute cost. Accepted revisions are recorded in `StrengthStore` before the active engine pointer is changed.

## UI contract

The structured `DOGMATIST_UI` snapshot can now include the effective Strength Lab recipe, not just percentages. The Evolution page can show, for example:

- mode: `plateau`;
- hard positions: 30;
- specialist examples: 15;
- deep-search teacher examples: 15;
- teacher depth multiplier: 3.0x;
- backfilled examples when targeted evidence was unavailable.

This should make it obvious whether a long-running Gen15 dynasty is still producing useful strength work.

## Remaining production gates

Before live installation:

1. commit or provide the missing production trainer/search source and Studio `pages/` source;
2. wire real position traces into `StrengthStore`;
3. wire recipe quotas into replay/training sampling;
4. implement killable worker boundaries for deep-search teacher jobs and League games;
5. run a fixed-Gen15 A/B search-revision experiment on the real Mac;
6. verify compute cost, thermal behavior and fixed-reference strength;
7. only then mark a search revision as adopted.

The key product rule is now explicit: **a long-lived Champion may remain Gen15, but the system is not allowed to interpret that as permission to stop learning.**
