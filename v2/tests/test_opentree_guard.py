import pytest

from dogmatist_v2.opentree_guard import OpenTreeStrengthGuard, TrialEvidence


def ev(score, games=16, branches=3.0, frontier=100, collapsed=False, reference="champion"):
    return TrialEvidence(
        arena_score=score,
        arena_games=games,
        effective_branches=branches,
        viable_frontier=frontier,
        collapse_warning=collapsed,
        reference_id=reference,
    )


def test_rejects_diversity_gain_when_strength_drop_is_too_large():
    guard = OpenTreeStrengthGuard(max_strength_drop=0.06)
    baseline = ev(0.60, branches=2.0, frontier=40)
    trial = ev(0.50, branches=4.0, frontier=300)
    decision = guard.decide(baseline, trial)
    assert not decision.accept_policy
    assert "strength regression" in decision.reason


def test_accepts_strength_safe_diversity_gain():
    guard = OpenTreeStrengthGuard()
    baseline = ev(0.58, branches=2.4, frontier=80)
    trial = ev(0.56, branches=3.0, frontier=130)
    decision = guard.decide(baseline, trial)
    assert decision.accept_policy
    assert decision.diversity_delta > 0


def test_insufficient_arena_keeps_baseline():
    guard = OpenTreeStrengthGuard(minimum_games=12)
    baseline = ev(0.55)
    trial = ev(0.70, games=8, branches=4.5, frontier=300)
    decision = guard.decide(baseline, trial)
    assert not decision.accept_policy
    assert "insufficient" in decision.reason


def test_collapsed_baseline_allows_strength_safe_recovery_trial():
    guard = OpenTreeStrengthGuard()
    baseline = ev(0.57, branches=1.7, frontier=20, collapsed=True)
    trial = ev(0.54, branches=1.75, frontier=25)
    decision = guard.decide(baseline, trial)
    assert decision.accept_policy
    assert "recovering" in decision.reason


def test_clear_strength_gain_can_win_even_with_flat_diversity():
    guard = OpenTreeStrengthGuard()
    baseline = ev(0.52, branches=3.4, frontier=120)
    trial = ev(0.58, branches=3.35, frontier=115)
    decision = guard.decide(baseline, trial)
    assert decision.accept_policy
    assert "strength improvement" in decision.reason


def test_no_material_gain_rolls_back_policy():
    guard = OpenTreeStrengthGuard(minimum_diversity_gain=0.05)
    baseline = ev(0.55, branches=3.0, frontier=100)
    trial = ev(0.56, branches=3.01, frontier=101)
    decision = guard.decide(baseline, trial)
    assert not decision.accept_policy
    assert "no meaningful" in decision.reason


def test_reference_change_makes_scores_non_comparable():
    guard = OpenTreeStrengthGuard()
    baseline = ev(0.55, reference="gen15")
    trial = ev(0.62, reference="gen23")
    decision = guard.decide(baseline, trial)
    assert not decision.accept_policy
    assert "reference changed" in decision.reason


def test_paired_arena_requires_even_game_count():
    with pytest.raises(ValueError):
        ev(0.55, games=15)


def test_guard_minimum_games_must_preserve_pairs():
    with pytest.raises(ValueError):
        OpenTreeStrengthGuard(minimum_games=11)
