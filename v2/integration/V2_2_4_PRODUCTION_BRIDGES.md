# V2.2.4 Production bridge slice

Status: implemented as pure-Python integration primitives on `v2-dynasty-archive`; not installed into the live Mac runtime yet.

## What this slice closes

### Confirmed promotion -> Chronicle
`PromotionChronicleBridge` accepts only an existing `PromotionDecision(action="promote")`. It cannot calculate or bypass promotion itself.

A succession is committed in one SQLite transaction:

1. verify the active reign is the expected outgoing Champion;
2. close the outgoing reign at one timestamp;
3. open the incoming Champion reign at the same timestamp;
4. mark the outgoing Champion `IMMORTAL`, protected and cold on disk;
5. mark the incoming Champion `ACTIVE`;
6. write one `champion_succession` historical event;
7. commit all changes together.

If the production callback is retried after an uncertain acknowledgement, the same already-applied succession is a no-op instead of creating duplicate reigns/events.

### Specialist -> Chronicle/archive
`SpecialistChronicleBridge` records every accepted opening-specialist trait even when the model body is unavailable.

If a checkpoint exists, a qualifying specialist becomes a protected `COLD` archive body. If no checkpoint exists, its trait and metadata survive as `HISTORY_ONLY`; the bridge never fabricates a checkpoint.

### Real game trace -> StrengthStore
`StrengthEvidenceBridge` is the narrow adapter expected from the production self-play/Arena runner. The production side only needs to emit, for selected positions:

- FEN;
- opening bucket;
- source generation and round;
- predicted value from the side-to-move perspective;
- eventual outcome value from the same perspective;
- normalized policy uncertainty.

The bridge derives normalized value error and loss severity, selects only high-value mistakes/uncertain positions, caps positions per game, and then uses the existing bounded/deduplicating `StrengthStore`.

This means the live trainer does **not** need to know the database schema.

## Why this boundary is deliberate

The GitHub repository still does not contain the complete production chess trainer/search implementation used on the Mac. Wiring directly against guessed class names would risk breaking the existing Gen15 state. These bridges therefore define the smallest stable interface the live runtime must satisfy once the complete source is available.

## Remaining live wiring

1. At the end of each real game, convert the trainer's search/value data to `PositionObservation` and call `StrengthEvidenceBridge.ingest_game`.
2. Feed the resulting `StrengthPipelinePlanner` recipe quotas into the real replay sampler.
3. Execute `DeepSearchTeacherRequest` with the same current model and increased search budget, then convert teacher targets into the trainer's native replay-example format.
4. After `OpenTreePromotionCoordinator` returns `promote`, atomically switch the live Champion checkpoint and call `PromotionChronicleBridge.apply` at the same safe boundary.
5. After League specialist discovery, pass `SpecialistRecord` rows and any durable checkpoint paths to `SpecialistChronicleBridge`.
6. Run the frozen-checkpoint engine A/B plan on the real Mac before activating any search revision.

Do not migrate or overwrite `~/.darwinchess` until the real local Python path, checkpoint format and trainer source have been verified and backed up.
