"""DogMatist v2: population/league/OpenTree evolution primitives."""

from .league import Candidate, MatchResult, LeagueTable, select_survivors
from .opentree_guard import GuardDecision, OpenTreeStrengthGuard, TrialEvidence
from .opentree_policy import (
    CurriculumMix,
    OpenTreeCurriculumController,
    OpenTreePolicy,
    TreeHealth,
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
