from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .archive import ArchiveEntry, ArchiveTier
from .dynasty import ChampionReign, HistoricalEvent


SCHEMA_VERSION = 1


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chronicle_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS champion_reigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    dethroned_by INTEGER,
    challengers_faced INTEGER NOT NULL DEFAULT 0,
    games_during_reign INTEGER NOT NULL DEFAULT 0,
    replacement_reason TEXT,
    UNIQUE(generation_id, started_at)
);
CREATE INDEX IF NOT EXISTS idx_champion_reigns_generation
    ON champion_reigns(generation_id);
CREATE INDEX IF NOT EXISTS idx_champion_reigns_started
    ON champion_reigns(started_at);

CREATE TABLE IF NOT EXISTS generation_archive (
    generation_id INTEGER PRIMARY KEY,
    tier TEXT NOT NULL,
    checkpoint_path TEXT,
    checkpoint_bytes INTEGER NOT NULL DEFAULT 0,
    ever_champion INTEGER NOT NULL DEFAULT 0,
    specialist_score REAL NOT NULL DEFAULT 0.0,
    protected INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    archived_at TEXT,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_generation_archive_tier
    ON generation_archive(tier);

CREATE TABLE IF NOT EXISTS generation_traits (
    generation_id INTEGER NOT NULL,
    trait_kind TEXT NOT NULL,
    trait_key TEXT NOT NULL,
    score REAL NOT NULL,
    sample_games INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY(generation_id, trait_kind, trait_key)
);
CREATE INDEX IF NOT EXISTS idx_generation_traits_lookup
    ON generation_traits(trait_kind, trait_key, score DESC);

CREATE TABLE IF NOT EXISTS historical_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    generation_id INTEGER,
    related_generation_id INTEGER,
    text TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_historical_events_time
    ON historical_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_historical_events_generation
    ON historical_events(generation_id, occurred_at DESC);
"""


class ChronicleStore:
    """Small SQLite store for durable evolutionary history.

    This store is intentionally independent from model loading. Querying the
    Chronicle must never cause a checkpoint to enter RAM.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR REPLACE INTO chronicle_meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ChronicleStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def upsert_archive_entry(
        self,
        entry: ArchiveEntry,
        *,
        archived_at: datetime | None = None,
        last_used_at: datetime | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO generation_archive(
                generation_id, tier, checkpoint_path, checkpoint_bytes,
                ever_champion, specialist_score, protected, reason,
                archived_at, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generation_id) DO UPDATE SET
                tier=excluded.tier,
                checkpoint_path=excluded.checkpoint_path,
                checkpoint_bytes=excluded.checkpoint_bytes,
                ever_champion=excluded.ever_champion,
                specialist_score=excluded.specialist_score,
                protected=excluded.protected,
                reason=excluded.reason,
                archived_at=COALESCE(excluded.archived_at, generation_archive.archived_at),
                last_used_at=COALESCE(excluded.last_used_at, generation_archive.last_used_at)
            """,
            (
                entry.generation_id,
                entry.tier.value,
                str(entry.checkpoint_path) if entry.checkpoint_path else None,
                entry.checkpoint_bytes,
                int(entry.ever_champion),
                entry.specialist_score,
                int(entry.protected),
                entry.reason,
                _iso(archived_at),
                _iso(last_used_at),
            ),
        )
        self._conn.commit()

    def archive_entries(self) -> tuple[ArchiveEntry, ...]:
        rows = self._conn.execute(
            "SELECT * FROM generation_archive ORDER BY generation_id"
        ).fetchall()
        return tuple(
            ArchiveEntry(
                generation_id=row["generation_id"],
                tier=ArchiveTier(row["tier"]),
                checkpoint_path=Path(row["checkpoint_path"]) if row["checkpoint_path"] else None,
                checkpoint_bytes=row["checkpoint_bytes"],
                ever_champion=bool(row["ever_champion"]),
                specialist_score=row["specialist_score"],
                protected=bool(row["protected"]),
                reason=row["reason"],
            )
            for row in rows
        )

    def start_reign(self, reign: ChampionReign) -> None:
        if not reign.active:
            raise ValueError("start_reign expects an active reign")
        self._conn.execute(
            """
            INSERT INTO champion_reigns(
                generation_id, started_at, challengers_faced, games_during_reign
            ) VALUES (?, ?, ?, ?)
            """,
            (
                reign.generation_id,
                _iso(reign.started_at),
                reign.challengers_faced,
                reign.games_during_reign,
            ),
        )
        self._conn.commit()

    def end_reign(
        self,
        generation_id: int,
        *,
        ended_at: datetime,
        dethroned_by: int | None,
        replacement_reason: str = "",
    ) -> None:
        cursor = self._conn.execute(
            """
            UPDATE champion_reigns
            SET ended_at=?, dethroned_by=?, replacement_reason=?
            WHERE id=(
                SELECT id FROM champion_reigns
                WHERE generation_id=? AND ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1
            )
            """,
            (_iso(ended_at), dethroned_by, replacement_reason, generation_id),
        )
        if cursor.rowcount != 1:
            self._conn.rollback()
            raise LookupError(f"no active reign found for generation {generation_id}")
        self._conn.commit()

    def increment_reign_activity(
        self,
        generation_id: int,
        *,
        challengers: int = 0,
        games: int = 0,
    ) -> None:
        if challengers < 0 or games < 0:
            raise ValueError("activity increments must be non-negative")
        cursor = self._conn.execute(
            """
            UPDATE champion_reigns
            SET challengers_faced=challengers_faced + ?,
                games_during_reign=games_during_reign + ?
            WHERE id=(
                SELECT id FROM champion_reigns
                WHERE generation_id=? AND ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1
            )
            """,
            (challengers, games, generation_id),
        )
        if cursor.rowcount != 1:
            self._conn.rollback()
            raise LookupError(f"no active reign found for generation {generation_id}")
        self._conn.commit()

    def record_trait(
        self,
        generation_id: int,
        trait_kind: str,
        trait_key: str,
        score: float,
        *,
        sample_games: int = 0,
        evidence: dict[str, Any] | None = None,
        updated_at: datetime,
    ) -> None:
        if sample_games < 0:
            raise ValueError("sample_games must be non-negative")
        self._conn.execute(
            """
            INSERT INTO generation_traits(
                generation_id, trait_kind, trait_key, score,
                sample_games, evidence_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generation_id, trait_kind, trait_key) DO UPDATE SET
                score=excluded.score,
                sample_games=excluded.sample_games,
                evidence_json=excluded.evidence_json,
                updated_at=excluded.updated_at
            """,
            (
                generation_id,
                trait_kind,
                trait_key,
                score,
                sample_games,
                json.dumps(evidence or {}, separators=(",", ":"), sort_keys=True),
                _iso(updated_at),
            ),
        )
        self._conn.commit()

    def record_event(
        self,
        event: HistoricalEvent,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO historical_events(
                occurred_at, kind, generation_id, related_generation_id,
                text, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _iso(event.occurred_at),
                event.kind,
                event.generation_id,
                event.related_generation_id,
                event.text,
                json.dumps(evidence or {}, separators=(",", ":"), sort_keys=True),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def recent_events(self, limit: int = 50) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            return ()
        rows = self._conn.execute(
            "SELECT * FROM historical_events ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return tuple(dict(row) for row in rows)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("chronicle datetimes must be timezone-aware")
    return value.isoformat()
