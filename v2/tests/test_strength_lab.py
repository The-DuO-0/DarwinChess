from dogmatist_v2.hard_positions import HardPositionCandidate, HardPositionMiner
from dogmatist_v2.strength_lab import (
    EngineGateAction,
    EngineRevisionGate,
    EngineTrialEvidence,
    RoundStrengthEvidence,
    StrengthLabController,
    StrengthMode,
)


def test_plateau_switches_to_hard_position_teacher_mode():
    history = [
        RoundStrengthEvidence(1, 15, False, 0.60, 8),
        RoundStrengthEvidence(2, 15, False, 0.61, 8),
        RoundStrengthEvidence(3, 15, False, 0.61, 8),
        RoundStrengthEvidence(4, 15, False, 0.62, 8),
    ]
    plan = StrengthLabController().plan(history)
    assert plan.mode is StrengthMode.PLATEAU
    assert plan.curriculum.hard_positions == 0.30
    assert plan.teacher_search_multiplier == 3.0
    assert plan.teacher_fraction == 0.15


def test_promotion_or_real_reference_gain_avoids_false_plateau():
    history = [
        RoundStrengthEvidence(1, 15, False, 0.50, 8),
        RoundStrengthEvidence(2, 15, False, 0.52, 8),
        RoundStrengthEvidence(3, 16, True, 0.55, 8),
        RoundStrengthEvidence(4, 16, False, 0.56, 8),
    ]
    assert StrengthLabController().plan(history).mode is StrengthMode.NORMAL


def test_hard_position_miner_deduplicates_and_preserves_opening_diversity():
    candidates = [
        HardPositionCandidate("p1", "open-A", "middle", 0.0, 0.9, 0.8, 2),
        HardPositionCandidate("p1", "open-A", "middle", 0.5, 0.2, 0.1, 1),
        HardPositionCandidate("p2", "open-A", "middle", 0.0, 0.8, 0.8, 1),
        HardPositionCandidate("p3", "open-B", "end", 0.0, 0.7, 0.7, 1),
    ]
    selected = HardPositionMiner().select(candidates, limit=3, max_per_opening_bucket=1)
    assert {row.position_key for row in selected} == {"p1", "p3"}


def test_engine_revision_requires_strength_and_compute_efficiency():
    gate = EngineRevisionGate()
    accepted = gate.decide(EngineTrialEvidence("search-r2", 16, 0.58, 0.02, 1.20))
    assert accepted.action is EngineGateAction.ACCEPT

    expensive = gate.decide(EngineTrialEvidence("search-r3", 16, 0.60, 0.03, 1.80))
    assert expensive.action is EngineGateAction.REJECT

    uncertain = gate.decide(EngineTrialEvidence("search-r4", 6, 0.70, 0.05, 1.10))
    assert uncertain.action is EngineGateAction.DEFER
