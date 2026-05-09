"""Tests for classic baseline optimizers."""

from __future__ import annotations

import random
import sys
import unittest
from unittest import mock

import numpy as np

from src.wpa_agv_optimization.classic_baselines import (
    ClassicBaselineConfig,
    _decode_task_order,
    run_classic_baseline,
)
from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.models import Task
from src.wpa_agv_optimization import main as main_mod
import scripts.run_fixed_benchmarks as bench_mod


class FakeEvaluator:
    def rebuild_wolf(self, wolf, base_wolf=None):
        flat_ids = [task.id for agv in wolf.agv_list for task in agv.tasks]
        wolf.fitness = float(sum((idx + 1) * task_id for idx, task_id in enumerate(flat_ids)))
        wolf.vehicle_num = sum(1 for agv in wolf.agv_list if agv.tasks)
        wolf.total_dist = int(wolf.fitness)
        wolf.total_wait_time = 0
        wolf.total_service_time = 0
        wolf.time_penalty = 0
        wolf.conflict_count = 0
        wolf.deadlock_count = 0
        wolf.deadlock_risk_count = 0
        wolf.replan_count = 0
        wolf.reroute_count = 0
        wolf.unfinished_count = 0
        return wolf


def _tasks(count: int) -> list[Task]:
    return [Task(task_id=i, x=i, y=1, weight=30, deadline=100 + i) for i in range(1, count + 1)]


class ClassicBaselineTests(unittest.TestCase):
    def test_decode_task_order_preserves_tasks_and_capacity(self) -> None:
        ordered_tasks = _tasks(5)

        agvs = _decode_task_order(ordered_tasks)

        decoded_ids = [task.id for agv in agvs for task in agv.tasks]
        self.assertEqual(decoded_ids, [1, 2, 3, 4, 5])
        self.assertTrue(all(agv.load <= Config.AGV_CAPACITY for agv in agvs))

    def test_sa_baseline_is_deterministic_for_fixed_rng(self) -> None:
        config = ClassicBaselineConfig(max_iter=20, pop_size=6)

        first = run_classic_baseline(
            algorithm="sa",
            grid_map=np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int),
            task_list=_tasks(5),
            evaluator=FakeEvaluator(),
            config=config,
            rng=random.Random(7),
        )
        second = run_classic_baseline(
            algorithm="sa",
            grid_map=np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int),
            task_list=_tasks(5),
            evaluator=FakeEvaluator(),
            config=config,
            rng=random.Random(7),
        )

        self.assertEqual(first.best_wolf.fitness, second.best_wolf.fitness)
        self.assertEqual(first.convergence, second.convergence)

    def test_ga_baseline_returns_complete_task_permutation(self) -> None:
        result = run_classic_baseline(
            algorithm="ga",
            grid_map=np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int),
            task_list=_tasks(6),
            evaluator=FakeEvaluator(),
            config=ClassicBaselineConfig(max_iter=8, pop_size=6),
            rng=random.Random(3),
        )

        decoded_ids = [task.id for agv in result.best_wolf.agv_list for task in agv.tasks]
        self.assertEqual(sorted(decoded_ids), [1, 2, 3, 4, 5, 6])
        self.assertEqual(len(decoded_ids), len(set(decoded_ids)))
        self.assertEqual(len(result.convergence), 8)

    def test_main_cli_accepts_classic_baseline_algorithms(self) -> None:
        with mock.patch.object(sys, "argv", ["wpa-agv", "--algorithm", "ga"]):
            self.assertEqual(main_mod.parse_args().algorithm, "ga")
        with mock.patch.object(sys, "argv", ["wpa-agv", "--algorithm", "sa"]):
            self.assertEqual(main_mod.parse_args().algorithm, "sa")

    def test_benchmark_cli_accepts_classic_baseline_algorithms(self) -> None:
        with mock.patch.object(sys, "argv", ["bench", "--algorithm", "ga"]):
            self.assertEqual(bench_mod.parse_args().algorithm, "ga")
        with mock.patch.object(sys, "argv", ["bench", "--algorithm", "sa"]):
            self.assertEqual(bench_mod.parse_args().algorithm, "sa")


if __name__ == "__main__":
    unittest.main()
