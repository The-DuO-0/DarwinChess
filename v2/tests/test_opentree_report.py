from dogmatist_v2.opentree_report import OpenTreeExperimentReport, OpenTreeRoundTrace


def trace(
    round_id,
    *,
    score=0.56,
    games=16,
    nodes=100,
    edges=160,
    frontier=60,
    holdout=20,
    branches=3.0,
    top_share=0.45,
    survival=0.25,
    db_bytes=100_000,
    collapse=False,
    status="baseline",
    reference="gen15",
):
    return OpenTreeRoundTrace(
        round_id=round_id,
        reference_id=reference,
        arena_score=score,
        arena_games=games,
        nodes=nodes,
        edges=edges,
        viable_frontier=frontier,
        strict_holdout=holdout,
        effective_branches=branches,
        root_top_move_share=top_share,
        branch_survival_ratio=survival,
        db_bytes=db_bytes,
        collapse_warning=collapse,
        policy_trial_status=status,
    )


def test_strength_safe_growing_tree_passes():
    report = OpenTreeExperimentReport()
    report.add(trace(1, score=0.56, nodes=100, edges=160, branches=2.8, db_bytes=100_000))
    report.add(trace(2, score=0.55, nodes=145, edges=230, branches=3.0, survival=0.22, db_bytes=118_000))
    report.add(trace(3, score=0.57, nodes=190, edges=305, branches=3.2, survival=0.28, db_bytes=137_000))
    report.add(trace(4, score=0.58, nodes=240, edges=390, branches=3.3, survival=0.31, db_bytes=159_000))
    summary = report.summarize()
    assert summary.verdict == "pass"
    assert summary.strength_delta > 0
    assert summary.node_growth == 140
    assert summary.mean_branch_survival > 0.20


def test_large_strength_regression_fails_even_if_tree_is_pretty():
    report = OpenTreeExperimentReport(max_strength_drop=0.06)
    report.add(trace(1, score=0.62, nodes=100, edges=160, branches=2.0))
    report.add(trace(2, score=0.58, nodes=180, edges=260, branches=3.2, survival=0.30))
    report.add(trace(3, score=0.55, nodes=260, edges=390, branches=4.0, survival=0.35))
    report.add(trace(4, score=0.51, nodes=350, edges=520, branches=4.5, survival=0.40))
    summary = report.summarize()
    assert summary.verdict == "fail"
    assert "strength regression" in summary.reasons[0]


def test_missing_strength_evidence_never_passes():
    report = OpenTreeExperimentReport()
    report.add(trace(1, games=0, nodes=100, edges=160))
    report.add(trace(2, games=0, nodes=150, edges=230, survival=0.25))
    report.add(trace(3, games=0, nodes=200, edges=310, survival=0.25))
    report.add(trace(4, games=0, nodes=250, edges=400, survival=0.25))
    summary = report.summarize()
    assert summary.verdict == "watch"
    assert any("paired Arena evidence" in reason for reason in summary.reasons)


def test_low_branch_survival_keeps_experiment_in_watch_state():
    report = OpenTreeExperimentReport(minimum_branch_survival=0.12)
    report.add(trace(1, nodes=100, edges=160))
    report.add(trace(2, nodes=150, edges=230, survival=0.05))
    report.add(trace(3, nodes=200, edges=310, survival=0.06))
    report.add(trace(4, nodes=250, edges=400, survival=0.08))
    summary = report.summarize()
    assert summary.verdict == "watch"
    assert any("branches are not surviving" in reason for reason in summary.reasons)


def test_repeated_rollbacks_are_visible():
    report = OpenTreeExperimentReport()
    report.add(trace(1, nodes=100, edges=160))
    report.add(trace(2, nodes=140, edges=220, status="rolled_back"))
    report.add(trace(3, nodes=180, edges=280, status="rolled_back"))
    report.add(trace(4, nodes=220, edges=340, status="baseline"))
    summary = report.summarize()
    assert summary.verdict == "watch"
    assert summary.rollback_count == 2


def test_jsonl_round_trip(tmp_path):
    report = OpenTreeExperimentReport(
        [
            trace(1, nodes=100, edges=160),
            trace(2, nodes=130, edges=200),
        ],
        minimum_rounds=2,
    )
    path = tmp_path / "trace.jsonl"
    report.write_jsonl(path)
    loaded = OpenTreeExperimentReport.read_jsonl(path, minimum_rounds=2)
    assert loaded.traces == report.traces
    assert loaded.summarize().reference_id == "gen15"


def test_mixed_reference_is_rejected():
    report = OpenTreeExperimentReport()
    report.add(trace(1, reference="gen15"))
    try:
        report.add(trace(2, reference="gen23"))
    except ValueError as exc:
        assert "same fixed reference_id" in str(exc)
    else:
        raise AssertionError("mixed references must be rejected")


def test_paired_arena_game_count_is_required():
    try:
        trace(1, games=15)
    except ValueError as exc:
        assert "even paired-game count" in str(exc)
    else:
        raise AssertionError("odd Arena game count must be rejected")
