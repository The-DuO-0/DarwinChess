from dogmatist_v2.search_forensics import SearchForensicRow, summarize_search_forensics


def test_forensic_classification_helpful_and_harmful_flips():
    helpful = SearchForensicRow(
        fen="fen-a",
        ply=5,
        baseline_move="a2a3",
        candidate_move="g1f3",
        full_deeper_move="g1f3",
        full_best_score_cp=40.0,
        full_baseline_score_cp=5.0,
        full_candidate_score_cp=40.0,
    )
    harmful = SearchForensicRow(
        fen="fen-b",
        ply=6,
        baseline_move="d7d5",
        candidate_move="h7h5",
        full_deeper_move="d7d5",
        full_best_score_cp=30.0,
        full_baseline_score_cp=30.0,
        full_candidate_score_cp=-20.0,
    )
    assert helpful.classification == "helpful_flip"
    assert helpful.candidate_regret_cp == 0.0
    assert helpful.baseline_regret_cp == 35.0
    assert harmful.classification == "harmful_flip"
    assert harmful.candidate_regret_cp == 50.0
    assert harmful.baseline_regret_cp == 0.0


def test_forensics_summary_compares_candidate_and_baseline_to_full_search():
    rows = [
        SearchForensicRow("a", 1, "h2h4", "e2e4", "e2e4", 50.0, -20.0, 50.0),
        SearchForensicRow("b", 2, "d7d5", "h7h5", "d7d5", 30.0, 30.0, -10.0),
        SearchForensicRow("c", 3, "g1f3", "g1f3", "g1f3", 10.0, 10.0, 10.0),
        SearchForensicRow("d", 4, "b1c3", "d2d3", "e2e4", 20.0, 5.0, 0.0),
    ]
    summary = summarize_search_forensics(rows)
    assert summary.positions == 4
    assert summary.helpful_flips == 1
    assert summary.harmful_flips == 1
    assert summary.same_as_full == 1
    assert summary.both_differ_from_full == 1
    assert summary.candidate_full_match_rate == 0.5
    assert summary.baseline_full_match_rate == 0.5
    assert summary.mean_candidate_regret_cp == 15.0
    assert summary.mean_baseline_regret_cp == 21.25


def test_empty_forensics_summary_is_safe():
    summary = summarize_search_forensics([])
    assert summary.positions == 0
    assert summary.candidate_full_match_rate == 0.0
    assert summary.baseline_full_match_rate == 0.0
    assert summary.mean_candidate_regret_cp is None
    assert summary.mean_baseline_regret_cp is None
