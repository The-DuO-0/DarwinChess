import pytest

from dogmatist_v2.opentree_guard import OpenTreeStrengthGuard, TrialEvidence
from dogmatist_v2.opentree_policy import CurriculumMix, OpenTreePolicy
from dogmatist_v2.opentree_trials import OpenTreePolicyTrialManager


def policy(frontier, reason):
    natural = 0.70 - frontier
    return OpenTreePolicy(
        mix=CurriculumMix(natural, frontier, 0.20, 0.10),
        early_temperature_scale=1.0,
        frontier_gap_cp=110,
        reason=reason,
    )


def evidence(score, *, games=16, branches=3.0, frontier=100, collapsed=False, reference="champion"):
    return TrialEvidence(score, games, branches, frontier, collapsed, reference)


def test_accepted_trial_promotes_trial_policy():
    manager = OpenTreePolicyTrialManager()
    baseline = policy(0.30, "baseline")
    trial = policy(0.36, "expand")
    manager.start(
        baseline_policy=baseline,
        trial_policy=trial,
        baseline_evidence=evidence(0.56, branches=2.4, frontier=70),
    )
    result = manager.finish(evidence(0.55, branches=3.2, frontier=140))
    assert not result.rolled_back
    assert result.accepted_policy == trial
    assert manager.can_start


def test_rejected_trial_rolls_back_and_enters_cooldown():
    manager = OpenTreePolicyTrialManager(
        guard=OpenTreeStrengthGuard(max_strength_drop=0.05),
        rejection_cooldown_rounds=2,
    )
    baseline = policy(0.30, "baseline")
    trial = policy(0.40, "too-aggressive")
    manager.start(
        baseline_policy=baseline,
        trial_policy=trial,
        baseline_evidence=evidence(0.62, branches=2.2, frontier=60),
    )
    result = manager.finish(evidence(0.50, branches=4.0, frontier=250))
    assert result.rolled_back
    assert result.accepted_policy == baseline
    assert manager.cooldown_rounds == 2
    assert not manager.can_start

    manager.tick_round()
    assert manager.cooldown_rounds == 1
    manager.tick_round()
    assert manager.can_start


def test_cannot_overlap_trials():
    manager = OpenTreePolicyTrialManager()
    baseline = policy(0.30, "baseline")
    trial = policy(0.36, "expand")
    manager.start(
        baseline_policy=baseline,
        trial_policy=trial,
        baseline_evidence=evidence(0.55),
    )
    with pytest.raises(RuntimeError):
        manager.start(
            baseline_policy=baseline,
            trial_policy=trial,
            baseline_evidence=evidence(0.55),
        )


def test_cannot_finish_without_active_trial():
    manager = OpenTreePolicyTrialManager()
    with pytest.raises(RuntimeError):
        manager.finish(evidence(0.55))


def test_active_trial_survives_snapshot_restore():
    manager = OpenTreePolicyTrialManager(rejection_cooldown_rounds=3)
    baseline = policy(0.30, "baseline")
    trial = policy(0.36, "expand")
    started = manager.start(
        baseline_policy=baseline,
        trial_policy=trial,
        baseline_evidence=evidence(0.57, branches=2.1, frontier=50, reference="gen15"),
    )
    restored = OpenTreePolicyTrialManager.restore(manager.snapshot())
    assert restored.active is not None
    assert restored.active.trial_id == started.trial_id
    assert restored.active.baseline_policy == baseline
    assert restored.active.trial_policy == trial
    assert restored.active.baseline_evidence.reference_id == "gen15"
    assert not restored.can_start


def test_rejection_cooldown_survives_snapshot_restore():
    manager = OpenTreePolicyTrialManager(
        guard=OpenTreeStrengthGuard(max_strength_drop=0.05),
        rejection_cooldown_rounds=2,
    )
    baseline = policy(0.30, "baseline")
    trial = policy(0.40, "aggressive")
    manager.start(
        baseline_policy=baseline,
        trial_policy=trial,
        baseline_evidence=evidence(0.64, reference="gen15"),
    )
    manager.finish(evidence(0.50, branches=4.0, frontier=250, reference="gen15"))
    restored = OpenTreePolicyTrialManager.restore(manager.snapshot())
    assert restored.active is None
    assert restored.cooldown_rounds == 2
    assert not restored.can_start


def test_unknown_snapshot_version_is_rejected():
    manager = OpenTreePolicyTrialManager()
    snapshot = manager.snapshot()
    snapshot["version"] = 999
    with pytest.raises(ValueError):
        OpenTreePolicyTrialManager.restore(snapshot)
