"""DogMatist v2: population/league/OpenTree evolution primitives."""

from .league import Candidate, MatchResult, LeagueTable, select_survivors
from .opentree_guard import GuardDecision, OpenTreeStrengthGuard, TrialEvidence
from .opentree_policy import (
    CurriculumMix,
    OpenTreeCurriculumController,
    OpenTreePolicy,
    TreeHealth,
)
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
    "ResourceBudget",
    "ResourceController",
    "ResourceSample",
    "OpeningBucket",
    "SpecialistArchive",
    "SpecialistRecord",
]
