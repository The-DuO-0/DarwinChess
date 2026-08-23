from dogmatist_v2.search_handoff import HandoffBranchEvidence, HandoffDiagnosis


def test_candidate_supported_when_not_worse_under_common_continuations():
    evidence = HandoffBranchEvidence(0.5, 1.0, 0.5, 0.5)
    assert evidence.shallow_delta == 0.5
    assert evidence.deep_delta == 0.0
    assert evidence.diagnosis is HandoffDiagnosis.CANDIDATE_SUPPORTED


def test_continuation_mismatch_when_deeper_move_needs_deeper_followup():
    evidence = HandoffBranchEvidence(1.0, 0.0, 0.5, 1.0)
    assert evidence.diagnosis is HandoffDiagnosis.CONTINUATION_MISMATCH


def test_candidate_harmful_when_both_common_continuations_dislike_it():
    evidence = HandoffBranchEvidence(1.0, 0.5, 1.0, 0.0)
    assert evidence.diagnosis is HandoffDiagnosis.CANDIDATE_HARMFUL


def test_mixed_when_shallow_likes_candidate_but_deep_does_not():
    evidence = HandoffBranchEvidence(0.0, 1.0, 1.0, 0.5)
    assert evidence.diagnosis is HandoffDiagnosis.MIXED


def test_scores_are_bounded():
    try:
        HandoffBranchEvidence(-0.1, 0.5, 0.5, 0.5)
    except ValueError:
        pass
    else:
        raise AssertionError("expected score validation")
