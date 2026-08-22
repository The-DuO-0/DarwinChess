from dogmatist_v2.opening_stability import (
    OpeningSearchObservation,
    build_stability_report,
)


def test_stable_opening_search_report():
    rows = [
        OpeningSearchObservation(
            ply=i,
            fen=f"fen-{i}",
            baseline_move="e2e4",
            deeper_move="e2e4",
            baseline_score_cp=15.0,
            deeper_score_cp=30.0,
        )
        for i in range(1, 7)
    ]
    report = build_stability_report(54, 2, 3, rows)
    assert report.move_flips == 0
    assert report.horizon_sensitive == 0
    assert report.early_search_unstable is False


def test_repeated_deeper_move_flips_mark_horizon_instability():
    rows = [
        OpeningSearchObservation(
            ply=1,
            fen="fen-1",
            baseline_move="a2a3",
            deeper_move="e2e4",
            baseline_score_cp=-80.0,
            deeper_score_cp=30.0,
        ),
        OpeningSearchObservation(
            ply=2,
            fen="fen-2",
            baseline_move="a7a6",
            deeper_move="e7e5",
            baseline_score_cp=-70.0,
            deeper_score_cp=40.0,
        ),
        OpeningSearchObservation(
            ply=3,
            fen="fen-3",
            baseline_move="b2b3",
            deeper_move="b2b3",
            baseline_score_cp=5.0,
            deeper_score_cp=15.0,
        ),
        OpeningSearchObservation(
            ply=4,
            fen="fen-4",
            baseline_move="g8f6",
            deeper_move="g8f6",
            baseline_score_cp=10.0,
            deeper_score_cp=20.0,
        ),
    ]
    report = build_stability_report(54, 2, 3, rows)
    assert report.move_flips == 2
    assert report.horizon_sensitive == 2
    assert report.early_search_unstable is True


def test_move_flip_with_small_score_delta_is_visible_but_not_overcalled_alone():
    row = OpeningSearchObservation(
        ply=2,
        fen="fen",
        baseline_move="g8f6",
        deeper_move="b8c6",
        baseline_score_cp=20.0,
        deeper_score_cp=35.0,
    )
    report = build_stability_report(54, 2, 3, [row])
    assert row.status() == "MOVE_FLIP"
    assert report.move_flips == 1
    assert report.early_search_unstable is False
