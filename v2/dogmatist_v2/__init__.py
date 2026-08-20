"""DogMatist v2: population/league/OpenTree evolution primitives."""

from .archive import (
    ArchiveEntry,
    ArchivePolicy,
    ArchiveTier,
    CompactCheckpointPlan,
    choose_archive_tier,
)
from .chronicle_store import ChronicleStore
from .dynasty import (
    ChampionReign,
    GenerationChronicle,
    GenerationLife,
    HistoricalEvent,
    HistoricalRole,
    build_lineage_path,
)
from .league import Candidate, MatchResult, LeagueTable, select_survivors
from .opentree_guard import GuardDecision, OpenTreeStrengthGuard, TrialEvidence
from .opentree_policy import (
    CurriculumMix,
    OpenTreeCurriculumController,
    OpenTreePolicy,
    TreeHealth,
)
from .opentree_promotion import (
    OpenTreePromotionCoordinator,
    PromotionDecision,
    PromotionEvidence,
)
from .opentree_report import (
    OpenTreeExperimentReport,
    OpenTreeExperimentSummary,
    OpenTreeRoundTrace,
)
from .opentree_trials import OpenTreePolicyTrialManager, PolicyTrial, TrialResult
from .resource import ResourceBudget, ResourceController, ResourceSample
from .specialists import OpeningBucket, SpecialistArchive, SpecialistRecord

__all__ = [
    "ArchiveEntry",
    "ArchivePolicy",
    "ArchiveTier",
    "CompactCheckpointPlan",
    "choose_archive_tier",
    "ChronicleStore",
    "ChampionReign",
    "GenerationChronicle",
    "GenerationLife",
    "HistoricalEvent",
    "HistoricalRole",
    "build_lineage_path",
    "Candidate",
    "MatchResult",
    "LeagueTable",
    "select_survivors",
    "GuardDecision",
    "OpenTreeStrengthGuard",
    "TrialEvidence",
    "CurriculumMix",
    "OpenTreeCurriculumController",
    "OpenTreePolicy",
    "TreeHealth",
    "OpenTreePromotionCoordinator",
    "PromotionDecision",
    "PromotionEvidence",
    "OpenTreeExperimentReport",
    "OpenTreeExperimentSummary",
    "OpenTreeRoundTrace",
    "OpenTreePolicyTrialManager",
    "PolicyTrial",
    "TrialResult",
    "ResourceBudget",
    "ResourceController",
    "ResourceSample",
    "OpeningBucket",
    "SpecialistArchive",
    "SpecialistRecord",
]
