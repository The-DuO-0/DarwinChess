"""DogMatist v2: population/league evolution primitives."""

from .league import Candidate, MatchResult, LeagueTable, select_survivors
from .resource import ResourceBudget, ResourceController, ResourceSample
from .specialists import OpeningBucket, SpecialistArchive, SpecialistRecord

__all__ = [
    "Candidate",
    "MatchResult",
    "LeagueTable",
    "select_survivors",
    "ResourceBudget",
    "ResourceController",
    "ResourceSample",
    "OpeningBucket",
    "SpecialistArchive",
    "SpecialistRecord",
]
