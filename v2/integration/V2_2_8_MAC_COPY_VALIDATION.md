# V2.2.8 — First real-Mac validation without touching the live lineage

This is the hard gate before any V2 overlay is allowed to touch the installed DogMatist lifetime state.

## Non-negotiable timing rule

The requested 8/10-hour Evolution value is an **admission budget, not a chess clock**.

When the active-compute budget is reached:

1. no new pairing is opened;
2. every already-started chess game finishes naturally;
3. if one leg of a colour-balanced pair has started, its reverse-colour fairness leg also finishes naturally;
4. only then may the run stop.

A game process may be terminated only by the independent bug watchdog. The copied-state safety floor is intentionally extreme:

- **at least 60 minutes** with no completed move/search progress;
- **at least 24 hours** total for one single game as a last-resort process-leak ceiling;
- terminate, wait 2 seconds, then kill only if still alive.

Older or accidental configuration values cannot lower those two safety floors. They may only be raised after real-Mac measurements. A healthy game finishing after the nominal Night budget is normal and must not count as a validation failure.

## Safety model

The first Mac run uses **two copies**:

- a source-code copy with the V2 overlay installed;
- a state copy under a fake HOME at `<validation_home>/.darwinchess`.

The live `~/.darwinchess` database/checkpoints are never opened for writing by the validation process.

`DOGMATIST_V2_COPY_VALIDATION=1` adds a second runtime guard: DogMatist refuses to start unless its resolved state root is exactly `$HOME/.darwinchess` inside the isolated validation HOME.

During this first copied-state run:

- Strength teacher replay persistence is forcibly OFF even if configuration accidentally enables it;
- League is forcibly limited to 2 game processes;
- frozen-reference measurement remains enabled;
- run-budget expiry never kills an active game.

## Preparation

From the V2 checkout/branch, create a new empty validation HOME. Do not manually choose the `.darwinchess` child; the preparer creates the required layout itself.

```bash
python v2/integration/production_overlay/prepare_mac_validation.py \
  ~/.darwinchess \
  ~/dogmatist-v2-validation \
  --spawn-probe
```

This performs only read/copy checks:

- SQLite backup API snapshot, safe for WAL mode;
- copies referenced generation checkpoints;
- rewrites copied DB paths to copied checkpoint paths;
- verifies no generation path points back into live state;
- SQLite integrity check;
- champion checkpoint existence/path check;
- optional macOS `multiprocessing spawn` probe.

Expected copied state:

```text
~/dogmatist-v2-validation/
└── .darwinchess/
    ├── darwinchess.sqlite3
    ├── checkpoints/
    └── SNAPSHOT_MANIFEST.json
```

The preflight is deliberately read-only and does not create a frozen reference yet.

## Install the overlay only on a source copy

Use `install_on_copy.py` against a disposable/copy `dog_matist-2.0` source tree. It defaults to dry-run and creates `.pre_v2` source backups when applied.

After applying the overlay, reinstall that source copy into its own `.venv` before validation.

Do not run the installer against the current live source tree for the first test.

## Dry-run the actual validation launch

The launch harness also defaults to dry-run:

```bash
python v2/integration/production_overlay/run_copied_state.py \
  /path/to/dog_matist-2.0-copy \
  ~/dogmatist-v2-validation/.darwinchess \
  --mode normal \
  --cycles 1
```

Review the printed fields before adding `--run`:

- `validation_home` must be the fake HOME;
- `snapshot_state` must end in `/.darwinchess`;
- `live_source_state` is informational only and must differ from the snapshot;
- environment must contain `DOGMATIST_V2_COPY_VALIDATION=1`;
- teacher persistence must be shown as forced off;
- initial League parallelism must be shown as 2;
- healthy-game budget interruption must be false.

## First real copied-state cycle

Only after the dry-run paths are correct:

```bash
python v2/integration/production_overlay/run_copied_state.py \
  /path/to/dog_matist-2.0-copy \
  ~/dogmatist-v2-validation/.darwinchess \
  --mode normal \
  --cycles 1 \
  --run
```

The harness sets an isolated `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and `PYTHONNOUSERSITE` before launching the copied source's `.venv/bin/darwinchess`.

## Automatic validation report

During the run, structured `DOGMATIST_UI` events are parsed into telemetry. The report records:

- maximum League process count;
- maximum simultaneously active games;
- longest observed per-game runtime;
- failed game IDs;
- watchdog timeout IDs;
- watchdog policy;
- copied-state safety event;
- fixed-reference result/trend;
- final active-compute snapshot.

After the child exits, a read-only postflight audit checks:

- copied SQLite integrity;
- no generation checkpoint points back into live state;
- frozen reference lives inside the copy and passes SHA-256 verification;
- `strength_v2.sqlite3` is healthy;
- at least one fixed-reference strength round exists for the normal one-cycle validation;
- **zero `source='strength_teacher'` rows** were inserted during the first safety run.

Reports are written under:

```text
~/dogmatist-v2-validation/dogmatist_v2_validation_reports/
├── validation_<timestamp>.log
└── validation_<timestamp>.json
```

A copied-state PASS requires all of the following:

- child process exit code 0;
- postflight audit passes;
- copied-validation structured event was observed;
- teacher persistence was reported OFF;
- process parallelism never exceeded 2;
- watchdog policy reports `budget_interrupts_games=false`;
- no watchdog timeout occurred.

A run may go beyond its nominal active-compute budget while finishing a healthy game and still PASS.

## What this first run does **not** prove

One successful cycle does not yet prove that V2 is stronger or ready for live installation. It only proves the production bridge is safe enough for the next validation layer.

After this gate:

1. inspect real per-game runtimes and CPU/RAM/thermal pressure;
2. run a matched 2-vs-3 League resource test on copied state;
3. validate longer overnight sleep/resume behavior;
4. run frozen-weight engine-revision A/B trials;
5. only then consider enabling self-teacher replay persistence;
6. only after those gates consider a live-state migration/install.

The live Champion and lifetime database remain outside this experiment until those gates pass.
