"""Paper-faithful original wolf pack algorithm with minimal discrete decoding."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .config import Config
from .evaluator import WolfEvaluator
from .models import AGV, Wolf


@dataclass
class OriginalWPAConfig:
    """Configuration for the paper-faithful original WPA."""

    alpha: int = 4
    beta: int = 6
    max_walks: int = 8
    omega: float = 500.0
    step_factor: float = 1000.0
    h_min: int = 4
    h_max: int = 8
    max_summon_steps: int = 300
    summon_order_patience: int = 6
    max_new_orders_per_summon: int = 30


@dataclass
class PaperWolfState:
    """Continuous-state wolf used by the original WPA."""

    position: np.ndarray
    wolf: Wolf | None
    fitness: float
    smell: float


@dataclass
class OriginalWPARunResult:
    """Optimization result for the original WPA run."""

    best_wolf: Wolf
    convergence: list[dict[str, float | int]]



def compute_step_sizes(mins: np.ndarray, maxs: np.ndarray, step_factor: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute step_a, step_b, step_c from the paper relationship."""
    spans = np.abs(maxs - mins)
    spans = np.where(spans > 0.0, spans, 1.0)
    step_a = spans / step_factor
    step_b = step_a * 2.0
    step_c = step_a / 2.0
    return step_a, step_b, step_c



def compute_d_near(mins: np.ndarray, maxs: np.ndarray, omega: float) -> float:
    """Compute d_near = sum(|max-min|) / (D * omega)."""
    spans = np.abs(maxs - mins)
    if spans.size == 0:
        return 0.0
    return float(spans.sum() / (spans.size * omega))



def _open_next_agv(curr_agv_id: int) -> tuple[int, AGV]:
    next_id = curr_agv_id + 1
    if next_id >= len(Config.START_NODES):
        raise ValueError(
            f"AGV 数超出起点槽位上限 {len(Config.START_NODES)}，"
            f"任务过多或容量过小；需扩展 Config.START_NODES 或调整任务集"
        )
    return next_id, AGV(agv_id=next_id, start_pos=Config.START_NODES[next_id])



def _decode_task_order(ordered_tasks: Sequence[object]) -> list[AGV]:
    if not ordered_tasks:
        return []

    agv_list: list[AGV] = []
    curr_agv_id = 0
    current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])

    for task in ordered_tasks:
        if current_agv.tasks and current_agv.load + task.weight > Config.AGV_CAPACITY:
            agv_list.append(current_agv)
            curr_agv_id, current_agv = _open_next_agv(curr_agv_id)

        current_agv.tasks.append(task)
        current_agv.load += task.weight

    if current_agv.tasks:
        agv_list.append(current_agv)
    return agv_list



def decode_priority_vector(keys: np.ndarray, task_list: Sequence[object]) -> list[AGV]:
    """Decode continuous keys to a task order, then greedily split only by capacity."""
    if len(keys) != len(task_list):
        raise ValueError("priority vector dimension must equal task count")

    ordered_tasks = [
        task for _, _, task in sorted((float(keys[idx]), idx, task) for idx, task in enumerate(task_list))
    ]
    return _decode_task_order(ordered_tasks)



def _choose_leader_index(
    population: Sequence[PaperWolfState],
    *,
    rng: random.Random | None = None,
) -> int:
    """Choose one leader at random among the wolves with maximal smell."""
    if not population:
        raise ValueError("population must not be empty")
    if rng is None:
        rng = random

    max_smell = max(state.smell for state in population)
    tied = [idx for idx, state in enumerate(population) if state.smell == max_smell]
    return rng.choice(tied)



def select_role_indices(
    population: Sequence[PaperWolfState],
    config: OriginalWPAConfig,
    *,
    rng: random.Random | None = None,
) -> tuple[int, list[int], list[int]]:
    """Select leader, scouts, and fierce wolves according to the paper."""
    if not population:
        raise ValueError("population must not be empty")

    if rng is None:
        rng = random

    leader_idx = _choose_leader_index(population, rng=rng)
    if len(population) == 1:
        return leader_idx, [], []

    ranked_others = sorted(
        (idx for idx in range(len(population)) if idx != leader_idx),
        key=lambda idx: population[idx].smell,
        reverse=True,
    )
    scout_low = max(1, math.floor(len(population) / (config.alpha + 1)))
    scout_high = max(scout_low, math.floor(len(population) / config.alpha))
    scout_high = min(len(population) - 1, scout_high)
    scout_num = rng.randint(scout_low, scout_high)

    scout_indices = ranked_others[:scout_num]
    fierce_indices = ranked_others[scout_num:]
    return leader_idx, scout_indices, fierce_indices


class OriginalWPAOptimizer:
    """Original WPA rebuilt to follow the paper, with only minimal discrete decoding."""

    def __init__(
        self,
        grid_map: np.ndarray,
        task_list: Sequence[object],
        *,
        evaluator: WolfEvaluator | None = None,
        config: OriginalWPAConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.grid_map = grid_map
        self.task_list = list(task_list)
        self.evaluator = evaluator or WolfEvaluator(grid_map)
        self.config = config or OriginalWPAConfig()
        self.rng = rng or random.Random()

        self.dimension = len(self.task_list)
        self.mins = np.zeros(self.dimension, dtype=float)
        upper_bound = float(max(1, self.dimension))
        self.maxs = np.full(self.dimension, upper_bound, dtype=float)
        self.step_a, self.step_b, self.step_c = compute_step_sizes(
            self.mins,
            self.maxs,
            step_factor=self.config.step_factor,
        )
        self.d_near = compute_d_near(self.mins, self.maxs, omega=self.config.omega)
        self._order_cache: dict[tuple[int, ...], Wolf] = {}

    def run(self, *, max_iter: int, pop_size: int, verbose: bool = True) -> OriginalWPARunResult:
        population = self._initialize_population(pop_size)
        convergence: list[dict[str, float | int]] = []

        for iter_idx in range(max_iter):
            if verbose:
                print(f"\n--- 第 {iter_idx + 1}/{max_iter} 代原始WPA迭代开始 ---")
            population = self._iterate(population, verbose=verbose)
            leader = self._leader(population)
            convergence.append({"iter": iter_idx + 1, "best_fitness": round(float(leader.fitness), 2)})
            if verbose:
                print(f"--- 第 {iter_idx + 1}/{max_iter} 代原始WPA迭代结束 ---")
                print(f"    当前头狼 F={leader.fitness:.2f}")

        return OriginalWPARunResult(best_wolf=self._leader(population).wolf, convergence=convergence)

    def _initialize_population(self, pop_size: int) -> list[PaperWolfState]:
        population = []
        for _ in range(pop_size):
            position = np.array(
                [self.rng.uniform(float(self.mins[idx]), float(self.maxs[idx])) for idx in range(self.dimension)],
                dtype=float,
            )
            population.append(self._evaluate_position(position))
        return population

    def _order_signature(self, position: np.ndarray) -> tuple[int, ...]:
        return tuple(idx for _, idx in sorted((float(position[idx]), idx) for idx in range(self.dimension)))

    def _evaluate_position(self, position: np.ndarray, base_wolf: Wolf | None = None) -> PaperWolfState:
        clipped = self._clip(position)
        order_signature = self._order_signature(clipped)
        cached_wolf = self._order_cache.get(order_signature)

        if cached_wolf is None:
            ordered_tasks = [self.task_list[idx] for idx in order_signature]
            wolf = Wolf()
            wolf.agv_list = _decode_task_order(ordered_tasks)
            cached_wolf = self.evaluator.rebuild_wolf(wolf, base_wolf=base_wolf)
            self._order_cache[order_signature] = cached_wolf

        return PaperWolfState(
            position=clipped,
            wolf=cached_wolf,
            fitness=float(cached_wolf.fitness),
            smell=float(-cached_wolf.fitness),
        )

    def _clip(self, position: np.ndarray) -> np.ndarray:
        return np.clip(position.astype(float, copy=False), self.mins, self.maxs)

    @staticmethod
    def _distance(state_a: PaperWolfState, state_b: PaperWolfState) -> float:
        return float(np.abs(state_a.position - state_b.position).sum())

    @staticmethod
    def _position_signature(state: PaperWolfState) -> tuple[float, ...]:
        return tuple(np.round(state.position.astype(float), 12))

    def _leader(self, population: Sequence[PaperWolfState]) -> PaperWolfState:
        return population[self._leader_index(population)]

    def _leader_index(self, population: Sequence[PaperWolfState]) -> int:
        return _choose_leader_index(population, rng=self.rng)

    @staticmethod
    def _promote_new_leader(
        new_leader_idx: int,
        current_leader_idx: int,
        scout_indices: Sequence[int],
        fierce_indices: list[int],
    ) -> tuple[int, list[int]]:
        updated_fierce = list(fierce_indices)
        if (
            current_leader_idx != new_leader_idx
            and current_leader_idx not in scout_indices
            and current_leader_idx not in updated_fierce
        ):
            updated_fierce.append(current_leader_idx)
        return new_leader_idx, updated_fierce

    def _iterate(self, population: Sequence[PaperWolfState], *, verbose: bool) -> list[PaperWolfState]:
        next_population = list(population)
        leader_idx, scout_indices, fierce_indices = select_role_indices(next_population, self.config, rng=self.rng)

        if verbose:
            print(
                f"> 头狼={leader_idx} | 探狼数={len(scout_indices)} | 猛狼数={len(fierce_indices)} | d_near={self.d_near:.6f}"
            )

        next_population, leader_idx, fierce_indices = self._scouting_phase(
            next_population,
            leader_idx=leader_idx,
            scout_indices=scout_indices,
            fierce_indices=fierce_indices,
        )
        next_population, leader_idx, besiege_indices, fierce_indices = self._summoning_phase(
            next_population,
            leader_idx=leader_idx,
            scout_indices=scout_indices,
            fierce_indices=fierce_indices,
        )

        current_leader = next_population[leader_idx]
        for idx in sorted(besiege_indices):
            if idx == leader_idx:
                continue
            candidate = self._besieging(next_population[idx], current_leader)
            next_population[idx] = candidate
            if candidate.smell > current_leader.smell:
                leader_idx, fierce_indices = self._promote_new_leader(idx, leader_idx, scout_indices, fierce_indices)
                current_leader = candidate

        next_population = self._survival_update(next_population)
        return next_population

    def _scouting_phase(
        self,
        population: list[PaperWolfState],
        *,
        leader_idx: int,
        scout_indices: Sequence[int],
        fierce_indices: list[int],
    ) -> tuple[list[PaperWolfState], int, list[int]]:
        for _ in range(self.config.max_walks):
            leader_state = population[leader_idx]
            for idx in scout_indices:
                scout_state = population[idx]
                if scout_state.smell > leader_state.smell:
                    leader_idx, fierce_indices = self._promote_new_leader(idx, leader_idx, scout_indices, fierce_indices)
                    return population, leader_idx, fierce_indices

                candidate = self._scout_step(scout_state)
                population[idx] = candidate
                leader_state = population[leader_idx]
                if candidate.smell > leader_state.smell:
                    leader_idx, fierce_indices = self._promote_new_leader(idx, leader_idx, scout_indices, fierce_indices)
                    return population, leader_idx, fierce_indices
        return population, leader_idx, fierce_indices

    def _scout_step(self, scout: PaperWolfState) -> PaperWolfState:
        h = self.rng.randint(self.config.h_min, self.config.h_max)
        best_candidate = scout
        for p in range(1, h + 1):
            offset = math.sin((2.0 * math.pi * p) / h) * self.step_a
            candidate = self._evaluate_position(scout.position + offset, base_wolf=scout.wolf)
            if candidate.smell > best_candidate.smell:
                best_candidate = candidate
        return best_candidate

    def _summoning_phase(
        self,
        population: list[PaperWolfState],
        *,
        leader_idx: int,
        scout_indices: Sequence[int],
        fierce_indices: list[int],
    ) -> tuple[list[PaperWolfState], int, set[int], list[int]]:
        besiege_indices = set(scout_indices)
        current_fierce = list(fierce_indices)

        while True:
            leader_changed = False
            leader_state = population[leader_idx]
            for idx in list(current_fierce):
                if idx == leader_idx:
                    continue
                candidate, entered_besiege, became_leader = self._summoning(population[idx], leader_state)
                population[idx] = candidate
                if became_leader:
                    leader_idx, current_fierce = self._promote_new_leader(idx, leader_idx, scout_indices, current_fierce)
                    leader_changed = True
                    break
                if entered_besiege:
                    besiege_indices.add(idx)
            if not leader_changed:
                return population, leader_idx, besiege_indices, current_fierce

    def _summoning(self, fierce: PaperWolfState, leader: PaperWolfState) -> tuple[PaperWolfState, bool, bool]:
        current = fierce
        steps = 0
        stagnant_order_steps = 0
        seen_orders = {self._order_signature(current.position)}
        recent_positions = [self._position_signature(current)]
        while self._distance(current, leader) > self.d_near and steps < self.config.max_summon_steps:
            delta = leader.position - current.position
            direction = np.sign(delta)
            if np.array_equal(direction, np.zeros_like(direction)):
                break

            current_order = self._order_signature(current.position)
            next_position = self._clip(current.position + (self.step_b * direction))
            next_order = self._order_signature(next_position)
            if next_order == current_order:
                stagnant_order_steps += 1
            else:
                stagnant_order_steps = 0
                seen_orders.add(next_order)

            candidate = self._evaluate_position(next_position, base_wolf=current.wolf)
            current = candidate
            if current.smell > leader.smell:
                return current, False, True

            if stagnant_order_steps >= self.config.summon_order_patience:
                return current, True, False
            if len(seen_orders) >= self.config.max_new_orders_per_summon:
                return current, True, False

            recent_positions.append(self._position_signature(current))
            if len(recent_positions) >= 3 and recent_positions[-1] == recent_positions[-3]:
                return current, True, False

            steps += 1
        return current, self._distance(current, leader) <= self.d_near, False

    def _besieging(self, wolf_state: PaperWolfState, leader: PaperWolfState) -> PaperWolfState:
        lam = self.rng.uniform(-1.0, 1.0)
        candidate = self._evaluate_position(
            wolf_state.position + (lam * self.step_c * np.abs(leader.position - wolf_state.position)),
            base_wolf=wolf_state.wolf,
        )
        if candidate.smell > wolf_state.smell:
            return candidate
        return wolf_state

    def _survival_update(self, population: Sequence[PaperWolfState]) -> list[PaperWolfState]:
        ranked = sorted(population, key=lambda state: state.smell, reverse=True)
        replace_low = max(1, math.floor(len(ranked) / (2 * self.config.beta)))
        replace_high = max(replace_low, math.floor(len(ranked) / self.config.beta))
        replace_high = min(len(ranked) - 1, replace_high)
        replace_num = self.rng.randint(replace_low, replace_high)

        survivors = ranked[:-replace_num]
        newcomers = self._initialize_population(replace_num)
        return survivors + newcomers
