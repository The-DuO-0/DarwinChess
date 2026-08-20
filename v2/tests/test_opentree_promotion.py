from dogmatist_v2.opentree_promotion import OpenTreePromotionCoordinator, PromotionEvidence


def test_no_trial_follows_ordinary_gate():
    decision = OpenTreePromotionCoordinator().decide(
        PromotionEvidence(23, 15, True, 0.61)
    )
    assert decision.action == "promote"


def test_failed_ordinary_gate_rejects_even_if_trial_guard_would_accept():
    decision = OpenTreePromotionCoordinator().decide(
        PromotionEvidence(
            23, 15, False, 0.48,
            policy_trial_active=True,
            policy_guard_accepts=True,
        )
    )
    assert decision.action == "reject"


def test_trial_candidate_is_deferred_until_fixed_reference_evidence_exists():
    decision = OpenTreePromotionCoordinator().decide(
        PromotionEvidence(
            23, 15, True, 0.62,
            policy_trial_active=True,
            policy_guard_accepts=None,
        )
    )
    assert decision.action == "defer"


def test_trial_requires_both_gates():
    coordinator = OpenTreePromotionCoordinator()
    rejected = coordinator.decide(
        PromotionEvidence(
            23, 15, True, 0.62,
            policy_trial_active=True,
            policy_guard_accepts=False,
            policy_guard_reason="fixed-reference regression",
        )
    )
    accepted = coordinator.decide(
        PromotionEvidence(
            24, 15, True, 0.63,
            policy_trial_active=True,
            policy_guard_accepts=True,
            policy_guard_reason="strength-safe curriculum trial",
        )
    )
    assert rejected.action == "reject"
    assert accepted.action == "promote"
