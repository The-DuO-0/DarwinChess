import pytest

from dogmatist_v2.opening_lab import OpeningRepairPlan, OpeningWeaknessController


def test_specialist_gap_and_hard_pressure_create_opening_focus():
    controller = OpeningWeaknessController(max_focus_openings=2, minimum_weakness=0.08)
    plan = controller.plan(
        specialists=[
            {"generation": 71, "opening_name": "Queen's Gambit", "score": 0.75, "games": 6},
            {"generation": 72, "opening_name": "Ruy Lopez", "score": 0.52, "games": 2},
        ],
        hard_bucket_stats=[
            {
                "opening_bucket": "Queen's Gambit",
                "hard_positions": 9,
                "hard_times_seen": 21,
                "mean_priority": 0.42,
                "max_priority": 0.81,
                "last_seen_round": 18,
            },
            {
                "opening_bucket": "frontier:abc",
                "hard_positions": 3,
                "hard_times_seen": 3,
                "mean_priority": 0.18,
                "max_priority": 0.22,
                "last_seen_round": 18,
            },
        ],
    )
    assert plan.active
    assert plan.focus_openings[0] == "Queen's Gambit"
    assert plan.signals[0].specialist_generation == 71
    assert plan.signals[0].weakness_score > 0.3


def test_weak_evidence_preserves_broad_exploration():
    plan = OpeningWeaknessController(minimum_weakness=0.5).plan(
        specialists=[{"generation": 70, "opening_name": "Reti", "score": 0.51, "games": 2}],
        hard_bucket_stats=[],
    )
    assert not plan.active
    assert plan.focus_openings == ()
    payload = plan.ui_payload()
    assert payload["book_moves_injected"] is False
    assert payload["novel_openings_allowed"] is True


def test_opening_focus_can_never_take_over_entire_curriculum():
    with pytest.raises(ValueError, match="0 and 0.75"):
        OpeningRepairPlan(("A",), (), focus_fraction=0.9)
