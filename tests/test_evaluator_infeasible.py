"""Regression tests for the infeasible-plan abort behavior in WolfEvaluator."""

from __future__ import annotations

import unittest
from unittest import mock

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


class EvaluatorInfeasibleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        self.tasks = [
            Task(1, 2, 2, 10, 60),
            Task(2, 6, 4, 10, 90),
            Task(3, 7, 6, 10, 120),
        ]

    def test_unreachable_task_aborts_agv_without_teleport(self) -> None:
        """Planner always fails — AGV must stop, no fake teleport segment written."""
        evaluator = WolfEvaluator(self.grid_map)
        wolf = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])

        with mock.patch.object(evaluator.planner, "plan", return_value=None):
            result = evaluator.rebuild_wolf(wolf)

        # All three customer tasks are marked unfinished (depot doesn't count here).
        self.assertEqual(result.unfinished_count, 3)
        # No real path was produced — AGV never moved from start.
        self.assertEqual(result.agv_list[0].path, [])
        # No target position was teleported into the reservation table.
        # (Wait nodes at start_pos are legitimate — AGV sat there during retries.)
        agv = result.agv_list[0]
        for task in self.tasks:
            for node in agv._reserved_nodes:
                self.assertNotEqual(
                    (node[0], node[1]),
                    (task.x, task.y),
                    msg=f"task pos should never appear in reserved_nodes after abort: {node}",
                )
        # Fitness must include the W7 penalty — the whole point of the fix.
        self.assertGreaterEqual(result.fitness, Config.W7_UNFINISHED * 3)

    def test_depot_unreachable_does_not_count_as_unfinished(self) -> None:
        """If customer tasks succeed and only the return-to-depot fails, it's not unfinished."""
        evaluator = WolfEvaluator(self.grid_map)
        wolf = _build_wolf([[self.tasks[0]]])
        original_plan = evaluator.planner.plan

        def plan_wrap(start_pos, end_pos, *args, **kwargs):
            if tuple(end_pos) == tuple(Config.DEPOT_NODE):
                return None
            return original_plan(start_pos, end_pos, *args, **kwargs)

        with mock.patch.object(evaluator.planner, "plan", side_effect=plan_wrap):
            result = evaluator.rebuild_wolf(wolf)

        # Customer task completed — no unfinished customer tasks.
        self.assertEqual(result.unfinished_count, 0)
        # Real path was produced for the customer leg.
        self.assertGreater(len(result.agv_list[0].path), 0)
        # Fitness does NOT carry the W7 penalty for this case.
        self.assertLess(result.fitness, Config.W7_UNFINISHED)

    def test_partial_failure_counts_only_remaining_customer_tasks(self) -> None:
        """First task succeeds, second task fails — only the second (and any later) count."""
        evaluator = WolfEvaluator(self.grid_map)
        wolf = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])
        original_plan = evaluator.planner.plan
        call_index = {"n": 0}

        def plan_wrap(start_pos, end_pos, *args, **kwargs):
            call_index["n"] += 1
            # First successful call is for task 1; fail everything afterwards.
            if call_index["n"] == 1:
                return original_plan(start_pos, end_pos, *args, **kwargs)
            return None

        with mock.patch.object(evaluator.planner, "plan", side_effect=plan_wrap):
            result = evaluator.rebuild_wolf(wolf)

        # Task 1 done, tasks 2 and 3 unfinished.
        self.assertEqual(result.unfinished_count, 2)
        # Path reflects only the completed leg.
        self.assertGreater(len(result.agv_list[0].path), 0)

    def test_incremental_rebuild_waits_past_default_window_for_feasible_task(self) -> None:
        evaluator = WolfEvaluator(self.grid_map)
        task = Task(10, 1, 1, 10, 500)

        blocker = AGV(agv_id=0, start_pos=(0, 0))
        blocker._task_signature = ()
        blocker._reserved_nodes = {(1, 1, t) for t in range(1, 61)}
        blocker._reserved_edges = set()
        blocker._cached_metrics = {
            "dist": 0,
            "wait_time": 0,
            "service_time": 0,
            "time_penalty": 0,
            "conflict_count": 0,
            "deadlock_count": 0,
            "deadlock_risk_count": 0,
            "replan_count": 0,
            "reroute_count": 0,
            "unfinished_count": 0,
        }
        base_second = AGV(agv_id=1, start_pos=(0, 1))

        base_wolf = Wolf()
        base_wolf.agv_list = [blocker, base_second]
        base_wolf._cache_ready = True

        candidate_blocker = AGV(agv_id=0, start_pos=(0, 0))
        candidate = AGV(agv_id=1, start_pos=(0, 1))
        candidate.tasks = [task]
        candidate.load = task.weight
        wolf = Wolf()
        wolf.agv_list = [candidate_blocker, candidate]

        result = evaluator.rebuild_wolf(wolf, base_wolf=base_wolf)

        self.assertEqual(result.unfinished_count, 0)
        self.assertGreaterEqual(result.agv_list[1].task_completion_times[task.id], 63)


if __name__ == "__main__":
    unittest.main()
