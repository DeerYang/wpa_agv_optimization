"""Regression tests ensuring no two AGVs share the same (x,y,t) in final paths."""

from __future__ import annotations

import unittest

from src.wpa_agv_optimization.evaluator import WolfEvaluator
from src.wpa_agv_optimization.main import load_scenario, run_algorithm
from src.wpa_agv_optimization.models import AGV, Task, Wolf


def _collect_timespace_collisions(wolf: Wolf) -> list[tuple]:
    seen: dict[tuple, int] = {}
    collisions = []
    for agv in wolf.agv_list:
        for x, y, t in agv.path:
            key = (int(x), int(y), int(t))
            if key in seen and seen[key] != agv.id:
                collisions.append((key, seen[key], agv.id))
            else:
                seen[key] = agv.id
    return collisions


def _collect_service_window_collisions(wolf: Wolf, service_time: int) -> list[tuple]:
    """Check that AGV A's service occupancy doesn't overlap AGV B's path node."""
    owners: dict[tuple, int] = {}
    for agv in wolf.agv_list:
        for x, y, t in agv.path:
            owners[(int(x), int(y), int(t))] = agv.id

    collisions = []
    for agv in wolf.agv_list:
        if not agv.tasks:
            continue
        for task in agv.tasks:
            arrivals = [p for p in agv.path if (p[0], p[1]) == (task.x, task.y)]
            if not arrivals:
                continue
            arrive_t = arrivals[0][2]
            for extra in range(1, service_time + 1):
                key = (task.x, task.y, int(arrive_t) + extra)
                holder = owners.get(key)
                if holder is not None and holder != agv.id:
                    collisions.append((key, agv.id, holder))
    return collisions


def _collect_opposite_edge_swaps(wolf: Wolf) -> list[tuple]:
    owners: dict[tuple, int] = {}
    collisions = []
    for agv in wolf.agv_list:
        for edge in getattr(agv, "_reserved_edges", set()):
            u, v, t = edge
            reverse = (v, u, t)
            holder = owners.get(reverse)
            if holder is not None and holder != agv.id:
                collisions.append((edge, holder, agv.id))
            owners[edge] = agv.id
    return collisions


class ServiceWindowConflictRegressionTests(unittest.TestCase):
    """After the fix, no AGV should ever reuse a timed-node already held by another."""

    def test_scenario_3_has_no_timespace_collision(self) -> None:
        result = run_algorithm(
            scenario=3,
            algorithm="improved",
            seed=20263221,
            verbose=False,
            allow_interactive=False,
            export_json=False,
        )
        collisions = _collect_timespace_collisions(result.wolf)
        self.assertEqual(
            collisions, [],
            msg=f"scenario 3 produced timed-node collisions: {collisions[:5]}",
        )

    def test_scenario_3_has_no_service_window_collision(self) -> None:
        from src.wpa_agv_optimization.config import Config
        result = run_algorithm(
            scenario=3,
            algorithm="improved",
            seed=20263221,
            verbose=False,
            allow_interactive=False,
            export_json=False,
        )
        collisions = _collect_service_window_collisions(result.wolf, Config.SERVICE_TIME)
        self.assertEqual(
            collisions, [],
            msg=f"scenario 3 has service-window collisions: {collisions[:5]}",
        )

    def test_scenario_3_has_no_opposite_edge_swap(self) -> None:
        result = run_algorithm(
            scenario=3,
            algorithm="improved",
            seed=20263228,
            verbose=False,
            allow_interactive=False,
            export_json=False,
        )
        collisions = _collect_opposite_edge_swaps(result.wolf)
        self.assertEqual(
            collisions, [],
            msg=f"scenario 3 produced opposite-edge swaps: {collisions[:5]}",
        )

    def test_scenario_1_has_no_collisions(self) -> None:
        from src.wpa_agv_optimization.config import Config
        result = run_algorithm(
            scenario=1,
            algorithm="improved",
            seed=20261221,
            verbose=False,
            allow_interactive=False,
            export_json=False,
        )
        self.assertEqual(_collect_timespace_collisions(result.wolf), [])
        self.assertEqual(_collect_service_window_collisions(result.wolf, Config.SERVICE_TIME), [])


class DetectServiceWindowConflictTests(unittest.TestCase):
    """White-box: the conflict dict must carry arrive_time for block computation."""

    def test_detect_returns_arrive_time_field(self) -> None:
        import numpy as np
        evaluator = WolfEvaluator(np.zeros((20, 20), dtype=int))
        agv = AGV(agv_id=2, start_pos=(0, 2))
        last_node = (5, 5, 7)
        reservation_table = {(5, 5, 8)}
        reservation_owner = {(5, 5, 8): 1}
        agv_map = {1: AGV(agv_id=1, start_pos=(0, 1)), 2: agv}

        conflict = evaluator._detect_service_window_conflict(
            agv=agv,
            last_node=last_node,
            reservation_table=reservation_table,
            reservation_owner=reservation_owner,
            agv_map=agv_map,
        )
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict["arrive_time"], 7)
        self.assertEqual(conflict["holder_id"], 1)

    def test_temporary_blocks_include_arrive_time_when_present(self) -> None:
        conflict = {
            "kind": "node",
            "time": 10,
            "node": (5, 5),
            "edge": None,
            "arrive_time": 9,
            "holder_id": 1,
        }
        blocks = WolfEvaluator._temporary_blocks_for_conflict(conflict)
        # Service frames (time..time+2)
        self.assertIn((5, 5, 10), blocks)
        self.assertIn((5, 5, 12), blocks)
        # Arrival frames (arrive_time-1, arrive_time)
        self.assertIn((5, 5, 8), blocks)
        self.assertIn((5, 5, 9), blocks)

    def test_temporary_blocks_without_arrive_time_is_unchanged(self) -> None:
        conflict = {
            "kind": "node",
            "time": 10,
            "node": (5, 5),
            "edge": None,
            "holder_id": 1,
        }
        blocks = WolfEvaluator._temporary_blocks_for_conflict(conflict)
        self.assertEqual(blocks, {(5, 5, 10), (5, 5, 11), (5, 5, 12)})


if __name__ == "__main__":
    unittest.main()
