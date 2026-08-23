from dogmatist_v2.opening_search_revision import (
    OpeningSearchEvidence,
    OpeningSearchR2Policy,
    OpeningSearchRevisionPlan,
    candidate_scores,
    select_holdout_opening_names,
    select_verification_candidates,
)
from dogmatist_v2.opening_stability import OpeningSearchObservation, build_stability_report


def _gen54_probe_report():
    raw = [
        (1, "h2h4", "g1f3", -35.0, 51.0),
        (2, "h7h5", "h7h5", -20.0, 46.0),
        (3, "h1h3", "g1f3", -44.0, 48.0),
        (4, "e7e5", "g8h6", -30.0, 46.0),
        (5, "h3f3", "g1f3", 5.0, 17.0),
        (6, "b8c6", "d8h4", 10.0, 18.0),
        (7, "b2b4", "d2d3", -10.0, 30.0),
        (8, "f8b4", "f8b4", -20.0, 40.0),
    ]
    rows = [
        OpeningSearchObservation(
            ply=ply,
            fen=f"fen-{ply}",
            baseline_move=base,
            deeper_move=deep,
            baseline_score_cp=base_cp,
            deeper_score_cp=deep_cp,
            baseline_depth=2,
            deeper_depth=3,
        )
        for ply, base, deep, base_cp, deep_cp in raw
    ]
    return build_stability_report(54, 2, 3, rows)


def test_real_gen54_probe_activates_r2c_revision_candidate():
    report = _gen54_probe_report()
    assert report.move_flips == 6
    assert report.flip_rate == 0.75
    assert report.horizon_sensitive == 2
    plan = OpeningSearchRevisionPlan.from_stability_report(report)
    assert plan.enabled is True
    assert plan.generation == 54
    assert plan.revision_id == "search-r2c-selective-root"
    assert plan.policy.extra_depth == 1
    assert plan.policy.always_verify_plies == 0
    assert plan.policy.max_extra_searches == 3
    assert plan.as_dict()["policy"]["book_moves_injected"] is False


def test_real_initial_h4_case_still_deepens_from_small_margin():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=1,
        base_depth=2,
        best_move="h2h4",
        best_score_cp=-35.0,
        candidates=candidate_scores(
            [("h2h4", -35.0), ("d2d4", -49.0), ("b1a3", -49.0), ("b1c3", -52.0)]
        ),
        previous_iteration_move="g1f3",
        previous_iteration_score_cp=-10.0,
    )
    decision = policy.decide(evidence)
    assert decision.deepen is True
    assert decision.target_depth == 3
    assert decision.reason == "shallow candidate margin is small"


def test_selective_pool_is_bounded_and_keeps_previous_iteration_move():
    rows = candidate_scores(
        [
            ("h2h4", -35.0),
            ("d2d4", -49.0),
            ("b1a3", -49.0),
            ("b1c3", -52.0),
            ("a2a3", -58.0),
            ("c2c3", -61.0),
            ("g1f3", -64.0),
            ("e2e4", -66.0),
            ("f2f3", -160.0),
            ("g2g4", -190.0),
        ]
    )
    selected = select_verification_candidates(
        rows,
        previous_iteration_move="g1f3",
        min_candidates=4,
        max_candidates=8,
        score_window_cp=90.0,
    )
    assert selected[0] == "h2h4"
    assert "g1f3" in selected
    assert len(selected) <= 8
    assert "g2g4" not in selected


def test_selective_pool_can_reinsert_previous_move_when_at_capacity():
    rows = candidate_scores([(f"m{i}", 100.0 - i) for i in range(10)])
    selected = select_verification_candidates(
        rows,
        previous_iteration_move="oldpv",
        min_candidates=4,
        max_candidates=6,
        score_window_cp=200.0,
    )
    assert len(selected) == 6
    assert selected[0] == "m0"
    assert "oldpv" in selected


def test_holdout_selector_is_disjoint_unique_and_deterministic():
    names = [
        "Open Game", "Italian", "Ruy Lopez", "Scotch", "Sicilian", "French",
        "Caro-Kann", "Pirc", "Queen's Gambit", "Slav", "King's Indian",
        "Nimzo-Indian", "English", "Reti", "Bird", "Scandinavian",
    ]
    development = {
        "Nimzo-Indian", "King's Indian", "French", "Queen's Gambit", "Pirc",
    }
    first = select_holdout_opening_names(
        names,
        excluded_names=development,
        pair_count=6,
        seed=20260823,
    )
    second = select_holdout_opening_names(
        names,
        excluded_names=development,
        pair_count=6,
        seed=20260823,
    )
    assert first == second
    assert len(first) == 6
    assert len(set(first)) == 6
    assert not (set(first) & development)


def test_later_opening_ply_deepens_when_candidate_margin_is_small():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=6,
        base_depth=2,
        best_move="g1f3",
        best_score_cp=20.0,
        candidates=candidate_scores([("g1f3", 20.0), ("d2d3", 5.0), ("b1c3", -10.0)]),
    )
    decision = policy.decide(evidence)
    assert decision.deepen is True
    assert decision.reason == "shallow candidate margin is small"


def test_stable_later_opening_search_does_not_spend_extra_depth():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=6,
        base_depth=2,
        best_move="g1f3",
        best_score_cp=60.0,
        candidates=candidate_scores([("g1f3", 60.0), ("d2d3", 20.0), ("b1c3", 0.0)]),
        previous_iteration_move="g1f3",
        previous_iteration_score_cp=50.0,
    )
    decision = policy.decide(evidence)
    assert decision.deepen is False


def test_naked_iterative_move_flip_no_longer_spends_compute():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=7,
        base_depth=2,
        best_move="b2b4",
        best_score_cp=12.0,
        previous_iteration_move="d2d3",
        previous_iteration_score_cp=5.0,
        candidates=candidate_scores([("b2b4", 12.0), ("g1f3", -20.0)]),
    )
    decision = policy.decide(evidence)
    assert decision.deepen is False


def test_move_flip_with_meaningful_score_swing_still_deepens():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=7,
        base_depth=2,
        best_move="b2b4",
        best_score_cp=20.0,
        previous_iteration_move="d2d3",
        previous_iteration_score_cp=-30.0,
        candidates=candidate_scores([("b2b4", 20.0), ("g1f3", -20.0)]),
    )
    decision = policy.decide(evidence)
    assert decision.deepen is True
    assert decision.reason == "move flip with meaningful score swing"


def test_large_score_swing_without_move_flip_can_trigger():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=7,
        base_depth=2,
        best_move="d2d3",
        best_score_cp=30.0,
        previous_iteration_move="d2d3",
        previous_iteration_score_cp=-40.0,
        candidates=candidate_scores([("d2d3", 30.0), ("g1f3", 0.0)]),
    )
    decision = policy.decide(evidence)
    assert decision.deepen is True
    assert decision.reason == "large iterative score swing"


def test_policy_never_deepens_after_opening_or_after_budget_exhausted():
    policy = OpeningSearchR2Policy(opening_plies=8, max_extra_searches=3)
    outside = OpeningSearchEvidence(ply=9, base_depth=2, best_move="g1f3")
    assert policy.decide(outside).deepen is False

    inside = OpeningSearchEvidence(
        ply=2,
        base_depth=2,
        best_move="g1f3",
        candidates=candidate_scores([("g1f3", 20.0), ("d2d3", 15.0)]),
    )
    exhausted = policy.decide(inside, extra_searches_used=3)
    assert exhausted.deepen is False
    assert "budget exhausted" in exhausted.reason
