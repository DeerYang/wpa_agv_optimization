"""Tests for utils helpers."""

from __future__ import annotations

import unittest

from src.wpa_agv_optimization.utils import is_valid_pick_location, nearest_pick_location


class IsValidPickLocationTests(unittest.TestCase):
    def test_adjacent_to_shelf_is_valid(self) -> None:
        obstacles = {(5, 5)}
        self.assertTrue(is_valid_pick_location((4, 5), obstacles))
        self.assertTrue(is_valid_pick_location((6, 5), obstacles))
        self.assertTrue(is_valid_pick_location((5, 4), obstacles))
        self.assertTrue(is_valid_pick_location((5, 6), obstacles))

    def test_diagonal_neighbor_not_enough(self) -> None:
        obstacles = {(5, 5)}
        self.assertFalse(is_valid_pick_location((4, 4), obstacles))

    def test_on_obstacle_rejected(self) -> None:
        obstacles = {(5, 5)}
        self.assertFalse(is_valid_pick_location((5, 5), obstacles))

    def test_isolated_cell_rejected(self) -> None:
        obstacles: set[tuple[int, int]] = set()
        self.assertFalse(is_valid_pick_location((3, 3), obstacles))


class NearestPickLocationTests(unittest.TestCase):
    def test_already_valid_returns_self(self) -> None:
        obstacles = {(5, 5)}
        self.assertEqual(nearest_pick_location((4, 5), obstacles, (20, 20)), (4, 5))

    def test_isolated_snaps_to_closest_shelf_neighbor(self) -> None:
        obstacles = {(5, 5)}
        self.assertEqual(nearest_pick_location((3, 5), obstacles, (20, 20)), (4, 5))

    def test_returns_none_when_no_shelf_exists(self) -> None:
        obstacles: set[tuple[int, int]] = set()
        self.assertIsNone(nearest_pick_location((3, 3), obstacles, (20, 20)))


if __name__ == "__main__":
    unittest.main()
