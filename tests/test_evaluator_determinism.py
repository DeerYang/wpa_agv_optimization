"""Determinism regression: same wolf structure must yield the same fitness."""

from __future__ import annotations

import unittest

import numpy as np

from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.evaluator import WolfEvaluator
from src.wpa_agv_optimization.models import AGV, Task, Wolf


def _build_wolf(task_groups: list[list[Task]]) -> Wolf:
    wolf = Wolf()
    agvs = []
    for agv_id, tasks in enumerate(task_groups):
        agv = AGV(agv_id=agv_id, start_pos=(0, agv_id))
        agv.tasks = list(tasks)
        agv.load = sum(task.weight for task in tasks)
        agvs.append(agv)
    wolf.agv_list = agvs
    return wolf


class DeterministicEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        self.tasks = [
            Task(1, 2, 2, 10, 60),
            Task(2, 6, 4, 10, 90),
            Task(3, 7, 6, 10, 120),
        ]

    def test_repeated_rebuild_on_fresh_evaluator_matches_fitness(self) -> None:
        """Two fresh evaluators rebuilding the same wolf structure must agree.

        Evaluator and planner are now free of any random state, so identical
        wolf structures yield identical fitness / dist / penalty / path.
        """
        wolf1 = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])
        wolf2 = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])
        r1 = WolfEvaluator(self.grid_map).rebuild_wolf(wolf1)
        r2 = WolfEvaluator(self.grid_map).rebuild_wolf(wolf2)
        self.assertEqual(r1.fitness, r2.fitness)
        self.assertEqual(r1.total_dist, r2.total_dist)
        self.assertEqual(r1.time_penalty, r2.time_penalty)
        self.assertEqual(r1.agv_list[0].path, r2.agv_list[0].path)

    def test_two_agv_layout_is_also_deterministic(self) -> None:
        wolf1 = _build_wolf([[self.tasks[0]], [self.tasks[1], self.tasks[2]]])
        wolf2 = _build_wolf([[self.tasks[0]], [self.tasks[1], self.tasks[2]]])
        r1 = WolfEvaluator(self.grid_map).rebuild_wolf(wolf1)
        r2 = WolfEvaluator(self.grid_map).rebuild_wolf(wolf2)
        self.assertEqual(r1.fitness, r2.fitness)
        self.assertEqual(r1.agv_list[1].path, r2.agv_list[1].path)

    def test_total_dist_counts_movement_edges_not_path_nodes(self) -> None:
        task = Task(10, 2, 0, 10, 500)
        wolf = _build_wolf([[task]])

        result = WolfEvaluator(self.grid_map).rebuild_wolf(wolf)

        expected_distance = 2 + abs(Config.DEPOT_NODE[0] - task.x) + abs(Config.DEPOT_NODE[1] - task.y)
        self.assertEqual(result.total_dist, expected_distance)
        self.assertEqual(result.agv_list[0].travel_distance, expected_distance)
        self.assertEqual(result.agv_list[0].task_completion_times[task.id], 2 + Config.SERVICE_TIME)
        self.assertEqual(result.agv_list[0].finish_time, result.agv_list[0].path[-1][2] + Config.SERVICE_TIME)


if __name__ == "__main__":
    unittest.main()
