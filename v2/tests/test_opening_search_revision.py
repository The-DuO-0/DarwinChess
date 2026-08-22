from dogmatist_v2.opening_search_revision import (
    OpeningSearchEvidence,
    OpeningSearchR2Policy,
    OpeningSearchR2Session,
    OpeningSearchRevisionPlan,
    absolute_game_ply,
    candidate_scores,
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


def test_real_gen54_probe_activates_revision_candidate():
    report = _gen54_probe_report()
    assert report.move_flips == 6
    assert report.flip_rate == 0.75
    assert report.horizon_sensitive == 2
    plan = OpeningSearchRevisionPlan.from_stability_report(report)
    assert plan.enabled is True
    assert plan.generation == 54
    assert plan.policy.extra_depth == 1
    assert plan.as_dict()["policy"]["book_moves_injected"] is False


def test_first_four_plies_are_verified_without_opening_book_logic():
    policy = OpeningSearchR2Policy()
    evidence = OpeningSearchEvidence(
        ply=1,
        base_depth=2,
        best_move="h2h4",
        best_score_cp=-35.0,
        candidates=candidate_scores(
            [("h2h4", -35.0), ("d2d4", -49.0), ("b1a3", -49.0), ("b1c3", -52.0)]
        ),
    )
    decision = policy.decide(evidence)
    assert decision.deepen is True
    assert decision.target_depth == 3
    assert decision.reason == "root opening verification"


def test_later_opening_ply_deepens_when_candidate_margin_is_small():
    policy = OpeningSearchR2Policy(always_verify_plies=2)
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
    policy = OpeningSearchR2Policy(always_verify_plies=2)
    evidence = OpeningSearchEvidence(
        ply=6,
        base_depth=2,
        best_move="g1f3",
        best_score_cp=60.0,
        candidates=candidate_scores([("g1f3", 60.0), ("d2d3", 20.0), ("b1c3", 0.0)]),
    )
    decision = policy.decide(evidence)
    assert decision.deepen is False


def test_iterative_move_flip_or_score_swing_triggers_later_verification():
    policy = OpeningSearchR2Policy(always_verify_plies=2)
    flip = OpeningSearchEvidence(
        ply=7,
        base_depth=2,
        best_move="b2b4",
        previous_iteration_move="d2d3",
    )
    assert policy.decide(flip).deepen is True

    swing = OpeningSearchEvidence(
        ply=7,
        base_depth=2,
        best_move="d2d3",
        best_score_cp=30.0,
        previous_iteration_move="d2d3",
        previous_iteration_score_cp=-40.0,
    )
    assert policy.decide(swing).deepen is True
    assert policy.decide(swing).reason == "large iterative score swing"


def test_policy_never_deepens_after_opening_or_after_budget_exhausted():
    policy = OpeningSearchR2Policy(opening_plies=8, max_extra_searches=3)
    outside = OpeningSearchEvidence(ply=9, base_depth=2, best_move="g1f3")
    assert policy.decide(outside).deepen is False

    inside = OpeningSearchEvidence(ply=2, base_depth=2, best_move="g1f3")
    exhausted = policy.decide(inside, extra_searches_used=3)
    assert exhausted.deepen is False
    assert "budget exhausted" in exhausted.reason


def test_session_resets_budget_when_a_new_game_starts():
    session = OpeningSearchR2Session(OpeningSearchR2Policy(max_extra_searches=2))
    for ply in (1, 2):
        decision = session.decide(OpeningSearchEvidence(ply=ply, base_depth=2, best_move="g1f3"))
        assert decision.deepen is True
    exhausted = session.decide(OpeningSearchEvidence(ply=3, base_depth=2, best_move="g1f3"))
    assert exhausted.deepen is False

    # A later call at a smaller/equal absolute ply means the searcher was reused
    # for another game; the per-game compute allowance must reset.
    again = session.decide(OpeningSearchEvidence(ply=1, base_depth=2, best_move="g1f3"))
    assert again.deepen is True
    assert session.extra_searches_used == 1
    assert session.total_extra_searches == 3


def test_absolute_game_ply_matches_fen_move_counters():
    assert absolute_game_ply(fullmove_number=1, white_to_move=True) == 1
    assert absolute_game_ply(fullmove_number=1, white_to_move=False) == 2
    assert absolute_game_ply(fullmove_number=2, white_to_move=True) == 3
    assert absolute_game_ply(fullmove_number=4, white_to_move=False) == 8
