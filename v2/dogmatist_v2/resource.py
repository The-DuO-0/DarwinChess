from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSample:
    cpu_percent: float
    memory_percent: float
    thermal_pressure: str = "nominal"  # nominal/fair/serious/critical


@dataclass(frozen=True)
class ResourceBudget:
    selfplay_workers: int
    arena_workers: int
    trainer_slots: int = 1


class ResourceController:
    """Conservative adaptive controller for one-Mac overnight training.

    The important invariant is trainer_slots == 1: MPS batch training gets an
    exclusive lane while CPU-heavy self-play/arena work may scale in parallel.
    This avoids the known failure mode where several full neural trainers fight
    over the same Apple GPU and memory bandwidth.
    """

    def __init__(
        self,
        *,
        min_selfplay_workers: int = 1,
        max_selfplay_workers: int = 4,
        min_arena_workers: int = 1,
        max_arena_workers: int = 2,
        cpu_soft_limit: float = 72.0,
        memory_soft_limit: float = 72.0,
    ) -> None:
        self.min_selfplay_workers = min_selfplay_workers
        self.max_selfplay_workers = max_selfplay_workers
        self.min_arena_workers = min_arena_workers
        self.max_arena_workers = max_arena_workers
        self.cpu_soft_limit = cpu_soft_limit
        self.memory_soft_limit = memory_soft_limit
        self._budget = ResourceBudget(min_selfplay_workers, min_arena_workers, 1)

    @property
    def budget(self) -> ResourceBudget:
        return self._budget

    def update(self, sample: ResourceSample) -> ResourceBudget:
        thermal = sample.thermal_pressure.lower()
        constrained = (
            sample.cpu_percent >= self.cpu_soft_limit
            or sample.memory_percent >= self.memory_soft_limit
            or thermal in {"serious", "critical"}
        )
        comfortable = (
            sample.cpu_percent <= self.cpu_soft_limit - 18.0
            and sample.memory_percent <= self.memory_soft_limit - 15.0
            and thermal == "nominal"
        )

        sp = self._budget.selfplay_workers
        arena = self._budget.arena_workers
        if constrained:
            sp = max(self.min_selfplay_workers, sp - 1)
            arena = max(self.min_arena_workers, arena - 1)
        elif comfortable:
            # Grow slowly; hysteresis prevents constant worker churn.
            sp = min(self.max_selfplay_workers, sp + 1)
            if sp >= self.max_selfplay_workers - 1:
                arena = min(self.max_arena_workers, arena + 1)

        self._budget = ResourceBudget(sp, arena, 1)
        return self._budget
