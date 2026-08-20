from dogmatist_v2.opentree_policy import (
    CurriculumMix,
    OpenTreeCurriculumController,
    TreeHealth,
)


def _health(**overrides):
    data = dict(
        root_visits=100,
        root_top_move_share=0.50,
        root_effective_branches=3.5,
        viable_frontier=120,
        strict_holdout=40,
        branch_revisit_ratio=0.25,
        collapse_warning=False,
    )
    data.update(overrides)
    return TreeHealth(**data)


def test_nominal_policy_keeps_baseline():
    ctl = OpenTreeCurriculumController()
    policy = ctl.update(_health())
    assert policy.mix == CurriculumMix(0.45, 0.30, 0.15, 0.10)
    assert policy.early_temperature_scale == 1.0
    assert policy.frontier_gap_cp == 110
    assert not ctl.collapsed


def test_collapse_increases_frontier_without_forcing_named_opening():
    ctl = OpenTreeCurriculumController()
    policy = ctl.update(
        _health(
            root_top_move_share=0.84,
            root_effective_branches=1.7,
            collapse_warning=True,
        )
    )
    assert ctl.collapsed
    assert policy.mix.frontier > 0.30
    assert policy.mix.specialist >= 0.08
    assert policy.mix.anchor >= 0.06
    assert policy.early_temperature_scale > 1.0
    assert 110 <= policy.frontier_gap_cp <= 150
    assert abs(sum(policy.mix.as_dict().values()) - 1.0) < 1e-9


def test_hysteresis_prevents_one_round_flip_flop_then_recovers():
    ctl = OpenTreeCurriculumController()
    ctl.update(_health(root_top_move_share=0.82, root_effective_branches=1.8))
    assert ctl.collapsed

    # Improved, but not beyond the stricter recovery thresholds.
    mid = ctl.update(_health(root_top_move_share=0.68, root_effective_branches=2.6))
    assert ctl.collapsed
    assert mid.mix.frontier >= 0.30

    recovered = ctl.update(_health(root_top_move_share=0.60, root_effective_branches=3.1))
    assert not ctl.collapsed
    assert recovered.mix.frontier >= 0.30
    assert recovered.early_temperature_scale == 1.0


def test_recovery_moves_monotonically_toward_baseline():
    ctl = OpenTreeCurriculumController()
    for _ in range(3):
        ctl.update(_health(root_top_move_share=0.85, root_effective_branches=1.6))
    high_frontier = ctl.mix.frontier
    assert high_frontier > 0.30

    p1 = ctl.update(_health(root_top_move_share=0.60, root_effective_branches=3.2))
    p2 = ctl.update(_health(root_top_move_share=0.58, root_effective_branches=3.4))
    assert 0.30 <= p2.mix.frontier <= p1.mix.frontier < high_frontier
    assert abs(sum(p2.mix.as_dict().values()) - 1.0) < 1e-9


def test_empty_frontier_falls_back_to_natural_without_retry_loop():
    ctl = OpenTreeCurriculumController()
    policy = ctl.update(_health(viable_frontier=0))
    assert policy.mix.frontier == 0.0
    assert policy.mix.natural == 0.75
    assert abs(sum(policy.mix.as_dict().values()) - 1.0) < 1e-9


def test_small_sample_does_not_trigger_collapse():
    ctl = OpenTreeCurriculumController(min_root_visits=40)
    policy = ctl.update(
        _health(
            root_visits=8,
            root_top_move_share=1.0,
            root_effective_branches=1.0,
            collapse_warning=True,
        )
    )
    assert not ctl.collapsed
    assert policy.mix == CurriculumMix(0.45, 0.30, 0.15, 0.10)
