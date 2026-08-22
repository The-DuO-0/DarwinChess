from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .opening_stability import OpeningSearchStabilityReport


@dataclass(frozen=True)
class CandidateScore:
    move: str
    score_cp: float


@dataclass(frozen=True)
class OpeningSearchEvidence:
    """Cheap evidence available after the normal shallow opening search.

    This object deliberately contains no opening names or human-book concepts.
    The revision is allowed to spend more search, but it is never allowed to
    force a known opening move.
    """

    ply: int
    base_depth: int
    best_move: str
    best_score_cp: float | None = None
    candidates: tuple[CandidateScore, ...] = ()
    previous_iteration_move: str | None = None
    previous_iteration_score_cp: float | None = None

    @property
    def candidate_margin_cp(self) -> float | None:
        if len(self.candidates) < 2:
            return None
        ordered = sorted((row.score_cp for row in self.candidates), reverse=True)
        return float(ordered[0] - ordered[1])

    @property
    def iteration_move_flip(self) -> bool:
        return (
            self.previous_iteration_move is not None
            and self.previous_iteration_move != self.best_move
        )

    @property
    def iteration_score_swing_cp(self) -> float | None:
        if self.best_score_cp is None or self.previous_iteration_score_cp is None:
            return None
        return abs(float(self.best_score_cp) - float(self.previous_iteration_score_cp))


@dataclass(frozen=True)
class OpeningDeepeningDecision:
    deepen: bool
    target_depth: int
    reason: str


@dataclass(frozen=True)
class OpeningSearchR2Policy:
    """Evidence-gated opening-only +1-ply stabilization candidate.

    The policy is intentionally conservative about compute.  It can only fire
    during the first ``opening_plies`` half-moves and can deepen at most
    ``max_extra_searches`` times per game.  The first few plies are always
    verified because the real Gen54 probe showed pathological root instability;
    later opening plies are verified only when the shallow search already looks
    uncertain.

    This is an engine-revision *candidate*, not a production default.  It must
    still pass frozen-weight A/B strength and compute-cost gates before adoption.
    """

    opening_plies: int = 8
    always_verify_plies: int = 4
    extra_depth: int = 1
    candidate_margin_cp: float = 25.0
    iteration_swing_cp: float = 60.0
    max_extra_searches: int = 6

    def __post_init__(self) -> None:
        if self.opening_plies <= 0:
            raise ValueError("opening_plies must be positive")
        if self.always_verify_plies < 0 or self.always_verify_plies > self.opening_plies:
            raise ValueError("always_verify_plies must be within opening_plies")
        if self.extra_depth <= 0:
            raise ValueError("extra_depth must be positive")
        if self.candidate_margin_cp < 0 or self.iteration_swing_cp < 0:
            raise ValueError("thresholds must be non-negative")
        if self.max_extra_searches < 0:
            raise ValueError("max_extra_searches must be non-negative")

    def decide(
        self,
        evidence: OpeningSearchEvidence,
        *,
        extra_searches_used: int = 0,
    ) -> OpeningDeepeningDecision:
        target = int(evidence.base_depth) + int(self.extra_depth)
        if evidence.ply <= 0:
            raise ValueError("ply must be positive")
        if evidence.base_depth <= 0:
            raise ValueError("base_depth must be positive")
        if evidence.ply > self.opening_plies:
            return OpeningDeepeningDecision(False, target, "outside opening stabilization window")
        if extra_searches_used >= self.max_extra_searches:
            return OpeningDeepeningDecision(False, target, "per-game extra-search budget exhausted")
        if evidence.ply <= self.always_verify_plies:
            return OpeningDeepeningDecision(True, target, "root opening verification")
        if evidence.iteration_move_flip:
            return OpeningDeepeningDecision(True, target, "iterative-deepening move flip")
        swing = evidence.iteration_score_swing_cp
        if swing is not None and swing >= self.iteration_swing_cp:
            return OpeningDeepeningDecision(True, target, "large iterative score swing")
        margin = evidence.candidate_margin_cp
        if margin is not None and margin <= self.candidate_margin_cp:
            return OpeningDeepeningDecision(True, target, "shallow candidate margin is small")
        return OpeningDeepeningDecision(False, target, "shallow opening search looks stable")


@dataclass(frozen=True)
class OpeningSearchRevisionPlan:
    revision_id: str
    generation: int
    enabled: bool
    policy: OpeningSearchR2Policy
    evidence_positions: int
    observed_flip_rate: float
    observed_horizon_sensitive: int
    reason: str

    @classmethod
    def from_stability_report(
        cls,
        report: OpeningSearchStabilityReport,
        *,
        revision_id: str = "search-r2-opening-stabilization",
        policy: OpeningSearchR2Policy | None = None,
    ) -> "OpeningSearchRevisionPlan":
        chosen = policy or OpeningSearchR2Policy()
        enabled = bool(report.early_search_unstable)
        reason = (
            f"opening probe unstable: flips={report.move_flips}/{len(report.observations)}, "
            f"horizon_sensitive={report.horizon_sensitive}"
            if enabled
            else "opening probe did not justify extra search"
        )
        return cls(
            revision_id=revision_id,
            generation=int(report.generation),
            enabled=enabled,
            policy=chosen,
            evidence_positions=len(report.observations),
            observed_flip_rate=float(report.flip_rate),
            observed_horizon_sensitive=int(report.horizon_sensitive),
            reason=reason,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "revision_id": self.revision_id,
            "generation": self.generation,
            "enabled": self.enabled,
            "evidence_positions": self.evidence_positions,
            "observed_flip_rate": self.observed_flip_rate,
            "observed_horizon_sensitive": self.observed_horizon_sensitive,
            "reason": self.reason,
            "policy": {
                "opening_plies": self.policy.opening_plies,
                "always_verify_plies": self.policy.always_verify_plies,
                "extra_depth": self.policy.extra_depth,
                "candidate_margin_cp": self.policy.candidate_margin_cp,
                "iteration_swing_cp": self.policy.iteration_swing_cp,
                "max_extra_searches": self.policy.max_extra_searches,
                "book_moves_injected": False,
            },
        }


def candidate_scores(rows: Iterable[tuple[str, float]]) -> tuple[CandidateScore, ...]:
    return tuple(CandidateScore(str(move), float(score)) for move, score in rows)
