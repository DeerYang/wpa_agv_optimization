"""Classic optimization baselines sharing the project evaluator."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from .config import Config
from .evaluator import WolfEvaluator
from .models import AGV, Wolf
from .utils import manhattan_dist


@dataclass
class ClassicBaselineConfig:
    max_iter: int = 50
    pop_size: int = 10
    mutation_prob: float = 0.25
    crossover_prob: float = 0.85
    tournament_size: int = 3
    initial_temperature: float = 120.0
    cooling_rate: float = 0.96


@dataclass
class ClassicBaselineResult:
    best_wolf: Wolf
    convergence: list[dict[str, float | int]]


def _decode_task_order(ordered_tasks: Sequence[object]) -> list[AGV] | None:
    if not ordered_tasks:
        return []

    agv_list: list[AGV] = []
    curr_agv_id = 0
    current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])

    for task in ordered_tasks:
        if task.weight > Config.AGV_CAPACITY:
            return None
        if current_agv.tasks and current_agv.load + task.weight > Config.AGV_CAPACITY:
            agv_list.append(current_agv)
            curr_agv_id += 1
            if curr_agv_id >= len(Config.START_NODES):
                return None
            current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])

        current_agv.tasks.append(task)
        current_agv.load += task.weight

    if current_agv.tasks:
        agv_list.append(current_agv)
    return agv_list


class _SequenceEvaluator:
    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.cache: dict[tuple[int, ...], Wolf] = {}

    @staticmethod
    def _signature(task_seq: Sequence[object]) -> tuple[int, ...]:
        return tuple(task.id for task in task_seq)

    def evaluate(self, task_seq: Sequence[object]) -> Wolf | None:
        signature = self._signature(task_seq)
        cached = self.cache.get(signature)
        if cached is not None:
            return cached

        agv_list = _decode_task_order(task_seq)
        if agv_list is None:
            return None
        wolf = Wolf()
        wolf.agv_list = agv_list
        result = self.evaluator.rebuild_wolf(wolf)
        self.cache[signature] = result
        return result


def _fitness(wolf: Wolf | None) -> float:
    return float("inf") if wolf is None else float(wolf.fitness)


def _copy_sequence(task_seq: Sequence[object]) -> list[object]:
    return list(task_seq)


def _random_neighbor(task_seq: Sequence[object], rng) -> list[object]:
    if len(task_seq) < 2:
        return _copy_sequence(task_seq)

    neighbor = _copy_sequence(task_seq)
    operator_name = rng.choice(["swap", "insert", "reverse"])
    i, j = sorted(rng.sample(range(len(neighbor)), 2))
    if operator_name == "swap":
        neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
    elif operator_name == "insert":
        task = neighbor.pop(j)
        neighbor.insert(i, task)
    else:
        neighbor[i : j + 1] = list(reversed(neighbor[i : j + 1]))
    return neighbor


def _initial_sequences(task_list: Sequence[object], pop_size: int, rng) -> list[list[object]]:
    base = list(task_list)
    sequences: list[list[object]] = []
    sequences.append(sorted(base, key=lambda task: (task.deadline, task.id)))
    sequences.append(sorted(base, key=lambda task: (manhattan_dist(Config.START_NODES[0], (task.x, task.y)), task.deadline)))

    while len(sequences) < max(1, pop_size):
        candidate = list(base)
        rng.shuffle(candidate)
        sequences.append(candidate)
    return sequences[: max(1, pop_size)]


def _run_sa(task_list: Sequence[object], evaluator: _SequenceEvaluator, config: ClassicBaselineConfig, rng) -> ClassicBaselineResult:
    current_seq = sorted(task_list, key=lambda task: (task.deadline, task.id))
    current_wolf = evaluator.evaluate(current_seq)
    best_seq = _copy_sequence(current_seq)
    best_wolf = current_wolf
    temperature = float(config.initial_temperature)
    convergence: list[dict[str, float | int]] = []

    for iter_idx in range(config.max_iter):
        candidate_seq = _random_neighbor(current_seq, rng)
        candidate_wolf = evaluator.evaluate(candidate_seq)
        delta = _fitness(candidate_wolf) - _fitness(current_wolf)
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            current_seq = candidate_seq
            current_wolf = candidate_wolf
        if _fitness(current_wolf) < _fitness(best_wolf):
            best_seq = _copy_sequence(current_seq)
            best_wolf = current_wolf
        convergence.append({"iter": iter_idx + 1, "best_fitness": round(float(_fitness(best_wolf)), 2)})
        temperature *= config.cooling_rate

    if best_wolf is None:
        best_wolf = evaluator.evaluate(best_seq)
    return ClassicBaselineResult(best_wolf=best_wolf, convergence=convergence)


def _ox_crossover(parent_a: Sequence[object], parent_b: Sequence[object], rng) -> list[object]:
    if len(parent_a) < 2:
        return _copy_sequence(parent_a)
    start, end = sorted(rng.sample(range(len(parent_a)), 2))
    child: list[object | None] = [None] * len(parent_a)
    child[start : end + 1] = parent_a[start : end + 1]
    used_ids = {task.id for task in child if task is not None}
    fill_tasks = [task for task in parent_b if task.id not in used_ids]
    fill_idx = 0
    for idx, task in enumerate(child):
        if task is None:
            child[idx] = fill_tasks[fill_idx]
            fill_idx += 1
    return [task for task in child if task is not None]


def _mutate(task_seq: Sequence[object], mutation_prob: float, rng) -> list[object]:
    if rng.random() > mutation_prob:
        return _copy_sequence(task_seq)
    return _random_neighbor(task_seq, rng)


def _select_parent(population: Sequence[list[object]], evaluator: _SequenceEvaluator, tournament_size: int, rng) -> list[object]:
    sample_size = min(max(1, tournament_size), len(population))
    candidates = rng.sample(list(population), sample_size)
    return min(candidates, key=lambda seq: _fitness(evaluator.evaluate(seq)))


def _run_ga(task_list: Sequence[object], evaluator: _SequenceEvaluator, config: ClassicBaselineConfig, rng) -> ClassicBaselineResult:
    population = _initial_sequences(task_list, config.pop_size, rng)
    best_seq = min(population, key=lambda seq: _fitness(evaluator.evaluate(seq)))
    best_wolf = evaluator.evaluate(best_seq)
    convergence: list[dict[str, float | int]] = []

    for iter_idx in range(config.max_iter):
        ranked = sorted(population, key=lambda seq: _fitness(evaluator.evaluate(seq)))
        next_population = [_copy_sequence(ranked[0])]
        while len(next_population) < len(population):
            parent_a = _select_parent(ranked, evaluator, config.tournament_size, rng)
            parent_b = _select_parent(ranked, evaluator, config.tournament_size, rng)
            if rng.random() < config.crossover_prob:
                child = _ox_crossover(parent_a, parent_b, rng)
            else:
                child = _copy_sequence(parent_a)
            next_population.append(_mutate(child, config.mutation_prob, rng))

        population = next_population
        current_best = min(population, key=lambda seq: _fitness(evaluator.evaluate(seq)))
        current_wolf = evaluator.evaluate(current_best)
        if _fitness(current_wolf) < _fitness(best_wolf):
            best_seq = _copy_sequence(current_best)
            best_wolf = current_wolf
        convergence.append({"iter": iter_idx + 1, "best_fitness": round(float(_fitness(best_wolf)), 2)})

    if best_wolf is None:
        best_wolf = evaluator.evaluate(best_seq)
    return ClassicBaselineResult(best_wolf=best_wolf, convergence=convergence)


def run_classic_baseline(
    algorithm: str,
    grid_map,
    task_list: Sequence[object],
    *,
    evaluator=None,
    config: ClassicBaselineConfig | None = None,
    rng=None,
) -> ClassicBaselineResult:
    selected_config = config or ClassicBaselineConfig()
    selected_rng = rng or random.Random()
    selected_evaluator = evaluator or WolfEvaluator(grid_map)
    sequence_evaluator = _SequenceEvaluator(selected_evaluator)

    if algorithm == "sa":
        return _run_sa(task_list, sequence_evaluator, selected_config, selected_rng)
    if algorithm == "ga":
        return _run_ga(task_list, sequence_evaluator, selected_config, selected_rng)
    raise ValueError(f"Unsupported classic baseline algorithm: {algorithm}")
