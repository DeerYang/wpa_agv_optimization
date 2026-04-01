"""Planner behavior regression tests."""

from __future__ import annotations

import unittest

import numpy as np

from src.wpa_agv_optimization.pathfinding import TentDFSPlanner


def _tent_iter():
    while True:
        yield 0.0


class PlannerBehaviorTests(unittest.TestCase):
    def test_empty_grid_returns_shortest_arrival(self) -> None:
        planner = TentDFSPlanner(np.zeros((20, 20), dtype=int))
        path = planner.plan((0, 0), (3, 0), 0, set(), _tent_iter())

        self.assertIsNotNone(path)
        self.assertEqual(path[-1], (3, 0, 3))

    def test_corridor_uses_wait_when_reservation_blocks_next_cell(self) -> None:
        grid = np.ones((20, 20), dtype=int)
        for x in range(4):
            grid[x][0] = 0

        planner = TentDFSPlanner(grid)
        path = planner.plan((0, 0), (3, 0), 0, {(1, 0, 1)}, _tent_iter())

        self.assertIsNotNone(path)
        self.assertEqual(path[:3], [(0, 0, 0), (0, 0, 1), (1, 0, 2)])
        self.assertEqual(path[-1], (3, 0, 4))

    def test_wall_with_single_gap_keeps_near_optimal_arrival(self) -> None:
        grid = np.zeros((20, 20), dtype=int)
        for y in range(5):
            if y != 4:
                grid[1][y] = 1

        planner = TentDFSPlanner(grid)
        path = planner.plan((0, 0), (2, 0), 0, set(), _tent_iter())

        self.assertIsNotNone(path)
        self.assertEqual(path[-1], (2, 0, 10))

    def test_static_distance_map_tracks_obstacle_detour(self) -> None:
        grid = np.zeros((20, 20), dtype=int)
        for y in range(5):
            if y != 4:
                grid[1][y] = 1

        planner = TentDFSPlanner(grid)
        distance_map = planner._distance_map((2, 0))

        self.assertEqual(distance_map[(2, 0)], 0)
        self.assertEqual(distance_map[(0, 0)], 10)


if __name__ == "__main__":
    unittest.main()
