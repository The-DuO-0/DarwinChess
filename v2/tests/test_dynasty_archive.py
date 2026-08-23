from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dogmatist_v2.archive import (
    ArchiveEntry,
    ArchivePolicy,
    ArchiveTier,
    CompactCheckpointPlan,
    choose_archive_tier,
)
from dogmatist_v2.dynasty import ChampionReign, GenerationLife, build_lineage_path


UTC = timezone.utc


def test_lifetime_and_reign_are_separate_clocks():
    born = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)
    life = GenerationLife(
        generation_id=31,
        parent_id=15,
        born_at=born,
        retired_at=born + timedelta(hours=10),
    )
    reign = ChampionReign(
        generation_id=31,
        started_at=born + timedelta(hours=2),
        ended_at=born + timedelta(hours=7),
        dethroned_by=42,
        challengers_faced=12,
        games_during_reign=144,
    )

    assert life.lifetime_seconds() == 10 * 3600
    assert reign.duration_seconds() == 5 * 3600
    assert not reign.active


def test_lineage_returns_oldest_ancestor_first():
    now = datetime(2026, 8, 20, tzinfo=UTC)
    generations = [
        GenerationLife(15, None, now),
        GenerationLife(31, 15, now),
        GenerationLife(42, 31, now),
    ]
    assert build_lineage_path(42, generations) == (15, 31, 42)


def test_lineage_cycle_is_rejected():
    now = datetime(2026, 8, 20, tzinfo=UTC)
    generations = [
        GenerationLife(1, 2, now),
        GenerationLife(2, 1, now),
    ]
    with pytest.raises(ValueError, match="cycle"):
        build_lineage_path(1, generations)


def test_historical_champion_is_never_auto_pruned():
    entries = [
        ArchiveEntry(
            15,
            ArchiveTier.IMMORTAL,
            Path("gen15.pt"),
            checkpoint_bytes=900,
            ever_champion=True,
        ),
        ArchiveEntry(
            31,
            ArchiveTier.COLD,
            Path("gen31.pt"),
            checkpoint_bytes=500,
            specialist_score=0.4,
        ),
    ]
    policy = ArchivePolicy(disk_budget_bytes=950, minimum_specialist_score=0.8)
    assert policy.prune_plan(entries) == (31,)


def test_prune_prefers_redundant_low_value_specimen():
    entries = [
        ArchiveEntry(20, ArchiveTier.COLD, Path("20.pt"), 400, specialist_score=0.1),
        ArchiveEntry(21, ArchiveTier.COLD, Path("21.pt"), 300, specialist_score=1.2),
        ArchiveEntry(22, ArchiveTier.PRESERVED, Path("22.pt"), 250, specialist_score=0.5, protected=True),
    ]
    policy = ArchivePolicy(disk_budget_bytes=600, minimum_specialist_score=0.8)
    assert policy.prune_plan(entries) == (20,)


def test_archive_tier_priority():
    assert choose_archive_tier(
        active=True,
        ever_champion=True,
        preserve_requested=True,
        specialist_score=99,
        minimum_specialist_score=1,
    ) is ArchiveTier.ACTIVE
    assert choose_archive_tier(
        active=False,
        ever_champion=True,
        preserve_requested=False,
        specialist_score=0,
        minimum_specialist_score=1,
    ) is ArchiveTier.IMMORTAL
    assert choose_archive_tier(
        active=False,
        ever_champion=False,
        preserve_requested=False,
        specialist_score=2,
        minimum_specialist_score=1,
    ) is ArchiveTier.COLD
    assert choose_archive_tier(
        active=False,
        ever_champion=False,
        preserve_requested=False,
        specialist_score=0,
        minimum_specialist_score=1,
    ) is ArchiveTier.HISTORY_ONLY


def test_cold_checkpoint_drops_optimizer_state():
    plan = CompactCheckpointPlan.for_tier(31, ArchiveTier.COLD)
    assert plan.keep_model_weights
    assert not plan.keep_optimizer_state
    assert plan.compression

    active = CompactCheckpointPlan.for_tier(42, ArchiveTier.ACTIVE)
    assert active.keep_model_weights
    assert active.keep_optimizer_state
    assert not active.compression
