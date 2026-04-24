"""Planner behavior regression tests."""

from __future__ import annotations

import unittest

import numpy as np

from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.pathfinding import TentDFSPlanner


class PlannerBehaviorTests(unittest.TestCase):
    def test_empty_grid_returns_shortest_arrival(self) -> None:
        planner = TentDFSPlanner(np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int))
        path = planner.plan((0, 0), (3, 0), 0, set())

        self.assertIsNotNone(path)
        self.assertEqual(path[-1], (3, 0, 3))

    def test_corridor_uses_wait_when_reservation_blocks_next_cell(self) -> None:
        grid = np.ones((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        for x in range(4):
            grid[x][0] = 0

        planner = TentDFSPlanner(grid)
        path = planner.plan((0, 0), (3, 0), 0, {(1, 0, 1)})

        self.assertIsNotNone(path)
        self.assertEqual(path[:3], [(0, 0, 0), (0, 0, 1), (1, 0, 2)])
        self.assertEqual(path[-1], (3, 0, 4))

    def test_corridor_avoids_opposite_edge_conflict_inside_search(self) -> None:
        grid = np.ones((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        for x in range(3):
            grid[x][0] = 0

        planner = TentDFSPlanner(grid)
        path = planner.plan(
            (0, 0),
            (2, 0),
            0,
            set(),
            occupied_edges={((1, 0), (0, 0), 1)},
        )

        self.assertIsNotNone(path)
        self.assertEqual(path[:3], [(0, 0, 0), (0, 0, 1), (1, 0, 2)])
        self.assertEqual(path[-1], (2, 0, 3))

    def test_custom_max_time_allows_long_but_feasible_wait(self) -> None:
        planner = TentDFSPlanner(np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int))
        reservations = {(1, 0, t) for t in range(1, 61)}

        path = planner.plan((0, 0), (1, 0), 0, reservations, max_time=80)

        self.assertIsNotNone(path)
        self.assertEqual(path[-1], (1, 0, 61))

    def test_wall_with_single_gap_keeps_near_optimal_arrival(self) -> None:
        grid = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        for y in range(5):
            if y != 4:
                grid[1][y] = 1

        planner = TentDFSPlanner(grid)
        path = planner.plan((0, 0), (2, 0), 0, set())

        self.assertIsNotNone(path)
        self.assertEqual(path[-1], (2, 0, 10))

    def test_static_distance_map_tracks_obstacle_detour(self) -> None:
        grid = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        for y in range(5):
            if y != 4:
                grid[1][y] = 1

        planner = TentDFSPlanner(grid)
        distance_map = planner._distance_map((2, 0))

        self.assertEqual(distance_map[(2, 0)], 0)
        self.assertEqual(distance_map[(0, 0)], 10)


if __name__ == "__main__":
    unittest.main()
