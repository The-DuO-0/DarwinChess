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
from .hard_positions import HardPositionCandidate, HardPositionMiner
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
from .promotion_bridge import ChampionCheckpoint, PromotionChronicleBridge
from .resource import ResourceBudget, ResourceController, ResourceSample
from .runtime import (
    ColorPairing,
    ComputeBudgetClock,
    GameState,
    GameWatchdog,
    LeagueGameSpec,
    LeagueGameStatus,
    LeaguePairScheduler,
    WatchdogTrip,
)
from .specialist_bridge import (
    SpecialistCheckpoint,
    SpecialistChronicleBridge,
    parse_generation_id,
)
from .specialists import OpeningBucket, SpecialistArchive, SpecialistRecord
from .strength_bridge import PositionObservation, StrengthCapturePolicy, StrengthEvidenceBridge
from .strength_lab import (
    EngineGateAction,
    EngineGateDecision,
    EngineRevisionGate,
    EngineTrialEvidence,
    PlateauDetector,
    RoundStrengthEvidence,
    StrengthCurriculumMix,
    StrengthLabController,
    StrengthLabPlan,
    StrengthMode,
    TrainingBatchBudget,
)
from .strength_pipeline import (
    DeepSearchTeacherRequest,
    EngineABTrialPlan,
    StrengthPipelinePlanner,
    StrengthRoundRecipe,
)
from .strength_store import HardPositionEvidence, StrengthStore
from .ui_flow import (
    EvolutionFlowSnapshot,
    EvolutionStage,
    build_evolution_flow_snapshot,
    encode_ui_event,
)

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
    "HardPositionCandidate",
    "HardPositionMiner",
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
    "ChampionCheckpoint",
    "PromotionChronicleBridge",
    "ResourceBudget",
    "ResourceController",
    "ResourceSample",
    "ColorPairing",
    "ComputeBudgetClock",
    "GameState",
    "GameWatchdog",
    "LeagueGameSpec",
    "LeagueGameStatus",
    "LeaguePairScheduler",
    "WatchdogTrip",
    "SpecialistCheckpoint",
    "SpecialistChronicleBridge",
    "parse_generation_id",
    "OpeningBucket",
    "SpecialistArchive",
    "SpecialistRecord",
    "PositionObservation",
    "StrengthCapturePolicy",
    "StrengthEvidenceBridge",
    "EngineGateAction",
    "EngineGateDecision",
    "EngineRevisionGate",
    "EngineTrialEvidence",
    "PlateauDetector",
    "RoundStrengthEvidence",
    "StrengthCurriculumMix",
    "StrengthLabController",
    "StrengthLabPlan",
    "StrengthMode",
    "TrainingBatchBudget",
    "DeepSearchTeacherRequest",
    "EngineABTrialPlan",
    "StrengthPipelinePlanner",
    "StrengthRoundRecipe",
    "HardPositionEvidence",
    "StrengthStore",
    "EvolutionFlowSnapshot",
    "EvolutionStage",
    "build_evolution_flow_snapshot",
    "encode_ui_event",
]
