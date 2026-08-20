from __future__ import annotations

from dataclasses import dataclass

from .opentree_guard import GuardDecision, OpenTreeStrengthGuard, TrialEvidence
from .opentree_policy import OpenTreePolicy


@dataclass(frozen=True)
class PolicyTrial:
    trial_id: int
    baseline_policy: OpenTreePolicy
    trial_policy: OpenTreePolicy
    baseline_evidence: TrialEvidence


@dataclass(frozen=True)
class TrialResult:
    trial_id: int
    accepted_policy: OpenTreePolicy
    decision: GuardDecision
    rolled_back: bool


class OpenTreePolicyTrialManager:
    """Two-phase rollout for adaptive opening curriculum changes.

    A controller proposal is not treated as permanent immediately. The runtime
    starts a trial, runs one bounded training/evaluation window, then asks the
    strength guard whether the new policy earned the right to persist.

    Rejected trials enter a short cooldown. This prevents repeatedly retrying a
    diversity-heavy policy that just failed the chess-strength gate.
    """

    def __init__(
        self,
        *,
        guard: OpenTreeStrengthGuard | None = None,
        rejection_cooldown_rounds: int = 2,
    ) -> None:
        if rejection_cooldown_rounds < 0:
            raise ValueError("rejection_cooldown_rounds must be non-negative")
        self.guard = guard or OpenTreeStrengthGuard()
        self.rejection_cooldown_rounds = rejection_cooldown_rounds
        self._active: PolicyTrial | None = None
        self._next_id = 1
        self._cooldown = 0

    @property
    def active(self) -> PolicyTrial | None:
        return self._active

    @property
    def cooldown_rounds(self) -> int:
        return self._cooldown

    @property
    def can_start(self) -> bool:
        return self._active is None and self._cooldown == 0

    def tick_round(self) -> None:
        if self._active is None and self._cooldown > 0:
            self._cooldown -= 1

    def start(
        self,
        *,
        baseline_policy: OpenTreePolicy,
        trial_policy: OpenTreePolicy,
        baseline_evidence: TrialEvidence,
    ) -> PolicyTrial:
        if self._active is not None:
            raise RuntimeError("an OpenTree policy trial is already active")
        if self._cooldown > 0:
            raise RuntimeError("OpenTree policy trials are cooling down after a rejection")
        trial = PolicyTrial(
            trial_id=self._next_id,
            baseline_policy=baseline_policy,
            trial_policy=trial_policy,
            baseline_evidence=baseline_evidence,
        )
        self._next_id += 1
        self._active = trial
        return trial

    def finish(self, trial_evidence: TrialEvidence) -> TrialResult:
        trial = self._active
        if trial is None:
            raise RuntimeError("no active OpenTree policy trial")
        decision = self.guard.decide(trial.baseline_evidence, trial_evidence)
        accepted = trial.trial_policy if decision.accept_policy else trial.baseline_policy
        rolled_back = not decision.accept_policy
        if rolled_back:
            self._cooldown = self.rejection_cooldown_rounds
        self._active = None
        return TrialResult(
            trial_id=trial.trial_id,
            accepted_policy=accepted,
            decision=decision,
            rolled_back=rolled_back,
        )
