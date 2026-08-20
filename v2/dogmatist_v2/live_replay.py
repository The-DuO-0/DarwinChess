from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Iterable

from .strength_pipeline import StrengthRoundRecipe


@dataclass(frozen=True)
class ReplayBatchQuota:
    natural_selfplay: int
    hard_positions: int
    specialist_sparring: int
    deep_search_teacher: int

    @property
    def total(self) -> int:
        return self.natural_selfplay + self.hard_positions + self.specialist_sparring + self.deep_search_teacher

    def as_dict(self) -> dict[str, int]:
        return {
            "natural_selfplay": self.natural_selfplay,
            "hard_positions": self.hard_positions,
            "specialist_sparring": self.specialist_sparring,
            "deep_search_teacher": self.deep_search_teacher,
            "total": self.total,
        }


class LiveReplayMixSampler:
    """Sample the existing production replay DB using a Strength Lab recipe.

    This does not duplicate hard positions. It selects the original replay rows by
    FEN, teacher rows by their game source, and specialist rows by the metadata the
    current production MemoryStore already writes. Any unavailable quota is filled
    from the ordinary lifetime replay sampler.
    """

    def __init__(self, *, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def quota_for(self, recipe: StrengthRoundRecipe, batch_size: int) -> ReplayBatchQuota:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        weights = (
            ("natural_selfplay", recipe.natural_selfplay_examples),
            ("hard_positions", len(recipe.hard_positions)),
            ("specialist_sparring", recipe.specialist_examples),
            ("deep_search_teacher", len(recipe.teacher_requests)),
        )
        total = sum(value for _, value in weights)
        if total <= 0:
            return ReplayBatchQuota(batch_size, 0, 0, 0)
        raw = [(name, batch_size * value / total) for name, value in weights]
        counts = {name: int(value) for name, value in raw}
        left = batch_size - sum(counts.values())
        order = sorted(raw, key=lambda item: (item[1] - int(item[1]), item[1]), reverse=True)
        for index in range(left):
            counts[order[index % len(order)][0]] += 1
        return ReplayBatchQuota(
            counts["natural_selfplay"],
            counts["hard_positions"],
            counts["specialist_sparring"],
            counts["deep_search_teacher"],
        )

    def _choose(self, pool: Iterable[Any], take: int, seen: set[int]) -> list[Any]:
        if take <= 0:
            return []
        candidates = [row for row in pool if int(row["id"]) not in seen]
        if not candidates:
            return []
        chosen = self.rng.sample(candidates, min(take, len(candidates)))
        seen.update(int(row["id"]) for row in chosen)
        return chosen

    def _hard_rows(self, memory: Any, recipe: StrengthRoundRecipe, take: int, seen: set[int]) -> list[Any]:
        fens = list(dict.fromkeys(row.fen for row in recipe.hard_positions if row.fen))
        if take <= 0 or not fens:
            return []
        # Production targeted_examples is intentionally small (tens, not thousands),
        # so a bounded IN query is simpler and safer than a new schema/index here.
        fens = fens[:256]
        placeholders = ",".join("?" for _ in fens)
        pool = memory.conn.execute(
            f"SELECT * FROM examples WHERE fen IN ({placeholders}) ORDER BY priority DESC, id DESC",
            fens,
        ).fetchall()
        return self._choose(pool, take, seen)

    def _teacher_rows(self, memory: Any, take: int, seen: set[int]) -> list[Any]:
        if take <= 0:
            return []
        pool = memory.conn.execute(
            """
            SELECT e.* FROM examples e
            JOIN games g ON g.id=e.game_id
            WHERE g.source='strength_teacher'
            ORDER BY e.id DESC LIMIT ?
            """,
            (max(64, take * 12),),
        ).fetchall()
        return self._choose(pool, take, seen)

    def _specialist_rows(self, memory: Any, take: int, seen: set[int]) -> list[Any]:
        if take <= 0 or not hasattr(memory, "active_specialists"):
            return []
        specialists = list(memory.active_specialists(limit=64))
        generations = sorted({int(row["generation"]) for row in specialists})
        openings = sorted({str(row["opening_name"]) for row in specialists if row["opening_name"]})
        if not generations or not openings:
            return []
        gq = ",".join("?" for _ in generations)
        oq = ",".join("?" for _ in openings)
        pool = memory.conn.execute(
            f"""
            SELECT * FROM examples
            WHERE origin_generation IN ({gq}) AND opening_name IN ({oq})
            ORDER BY id DESC LIMIT ?
            """,
            [*generations, *openings, max(128, take * 16)],
        ).fetchall()
        return self._choose(pool, take, seen)

    def sample(
        self,
        memory: Any,
        recipe: StrengthRoundRecipe,
        *,
        batch_size: int,
        recent_fraction: float = 0.35,
    ) -> list[Any]:
        quota = self.quota_for(recipe, batch_size)
        rows: list[Any] = []
        seen: set[int] = set()

        rows.extend(self._hard_rows(memory, recipe, quota.hard_positions, seen))
        rows.extend(self._specialist_rows(memory, quota.specialist_sparring, seen))
        rows.extend(self._teacher_rows(memory, quota.deep_search_teacher, seen))

        # Missing targeted evidence is deliberately backfilled with the existing
        # lifetime replay policy instead of repeated copies of the same weakness.
        remaining = batch_size - len(rows)
        if remaining > 0:
            ordinary = memory.replay_sample(max(batch_size * 2, remaining * 3), recent_fraction)
            for row in ordinary:
                row_id = int(row["id"])
                if row_id in seen:
                    continue
                seen.add(row_id)
                rows.append(row)
                if len(rows) >= batch_size:
                    break

        if len(rows) < batch_size:
            pool = memory.conn.execute(
                "SELECT * FROM examples ORDER BY id DESC LIMIT ?",
                (batch_size * 4,),
            ).fetchall()
            for row in pool:
                row_id = int(row["id"])
                if row_id in seen:
                    continue
                seen.add(row_id)
                rows.append(row)
                if len(rows) >= batch_size:
                    break
        return rows[:batch_size]
