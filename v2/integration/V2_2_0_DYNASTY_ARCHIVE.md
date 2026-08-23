# DogMatist V2.2.0 — Dynasty Archive

Status: **R&D branch implementation started; not yet installed into the live Mac runtime.**

Branch: `v2-dynasty-archive`

## Why this exists

DogMatist should not merely remember the current strongest checkpoint.  It should
retain an inspectable evolutionary history: champions, reigns, lineages,
specialists, unusual descendants, and the reason important models survived or
were replaced.

At the same time, historical preservation must not turn the Mac into a model
warehouse.  History and model bodies are therefore separate concepts.

## Non-negotiable invariants

1. Every generation may leave durable historical metadata even when its model
   weights are deleted.
2. Generation lifetime and champion reign duration are separate clocks.
3. Every historical champion is protected from automatic model-body deletion.
4. Strong opening/position/endgame specialists may survive without ever being
   champion.
5. Cold archived models are not RAM-resident.  Chronicle/UI queries must never
   load a checkpoint.
6. The active training checkpoint may retain optimizer state; cold historical
   checkpoints should be compact model-only artifacts by default.
7. Archive storage obeys a configurable disk budget.  Redundant non-champion
   specimens are the first automatic pruning candidates.
8. Existing `~/.darwinchess` history/champion state must be migrated, never
   reset.
9. The Dynasty feature must not bypass the existing V2.1 OpenTree strength
   guard or promotion gates.

## Storage tiers

- `ACTIVE`: currently participating in training/evaluation and allowed in RAM.
- `IMMORTAL`: historical Champion model body; cold on disk and never auto-pruned.
- `PRESERVED`: explicitly protected notable model; cold on disk.
- `COLD`: useful specialist retained under the storage budget; lazy-loaded.
- `HISTORY_ONLY`: metadata, lineage, scores, and events remain; model body gone.

A generation can remain fully visible in the Chronicle after becoming
`HISTORY_ONLY`.

## Chronicle schema — first slice

The new isolated SQLite store contains:

- `champion_reigns`
  - generation
  - promotion/start timestamp
  - dethroning timestamp
  - dethroned-by generation
  - challengers faced
  - games during reign
  - replacement reason
- `generation_archive`
  - storage tier
  - model path/bytes
  - ever-champion flag
  - specialist score
  - protected flag
  - preservation reason
  - archive / last-used timestamps
- `generation_traits`
  - trait kind (`opening`, `endgame`, `position`, etc.)
  - trait key/bucket
  - score
  - sample count
  - compact evidence JSON
- `historical_events`
  - timestamp
  - event kind
  - subject and related generation
  - human-readable Chronicle text
  - evidence JSON

The first implementation is deliberately separate from the live DB so its
migration can be validated before touching lifetime data.

## Compact checkpoints

V2.2.0 starts with **model-only cold checkpoints** rather than delta chains.
This is intentional.  Optimizer state can be much larger than the useful model
artifact, and removing it is a simple low-risk saving.  Delta checkpoints may
be evaluated later only if profiling shows model-only archives are still too
large.

We do **not** want deep `GenN -> parent delta -> grandparent delta -> ...`
chains that make old champions fragile or slow to load.

## Intended Chronicle UI

A dedicated `Chronicle` / `Dynasty Archive` tab will be added after the storage
and migration primitives are validated.  It should expose:

### Dynasty view

- chronological Champion cards
- lifetime vs reign duration
- challengers/games survived
- promoter/dethroner
- replacement reason
- rating/strength movement where evidence exists

### Lineage view

- ancestor/descendant graph
- inherited specialist traits
- Champion and specialist markers
- filters to control visual density

### Specialist museum

- opening/position/endgame specialty
- evidence/sample count
- current archive tier and bytes
- descendants that inherited the trait
- manual Preserve / Release controls

### Storage panel

- archive bytes / configured budget
- active vs cold model count
- model-only vs history-only count
- what would be pruned next
- historical Champions explicitly marked protected

## Migration plan

Do not modify live state until the current V2.1.7 isolated end-to-end gate has
been inspected.

After that gate:

1. Snapshot/backup the live SQLite DB and checkpoint directory.
2. Create Chronicle tables with idempotent migration code.
3. Backfill known generations from the existing `generations` table.
4. Backfill the currently known Champion as an active reign, marking the start
   timestamp as inferred when historical evidence cannot establish it exactly.
5. Import existing specialist records without loading their checkpoints.
6. Wire future promotion transactions to close the old reign and open the new
   one atomically.
7. Add compact cold-checkpoint export and verify a cold model can be loaded for
   evaluation, then unloaded.
8. Add the Chronicle UI only after the DB path is proven durable.

Never invent historical timestamps that the old system did not record.  Unknown
history should be labeled inferred/unknown rather than silently fabricated.

## Next implementation slices

1. **Promotion bridge** — transactionally record Champion succession and events.
2. **Specialist bridge** — convert specialist evidence into durable traits and
   archive-tier decisions.
3. **Checkpoint compactor** — export weight-only cold checkpoints, checksum
   them, verify reload, then remove redundant optimizer-heavy historical files.
4. **Budget manager** — dry-run pruning report first; destructive pruning only
   after verification and protected-model checks.
5. **Chronicle UI** — Dynasty, lineage, specialists, and storage views.
6. **Live migration** — only after tests + isolated Mac validation pass.
