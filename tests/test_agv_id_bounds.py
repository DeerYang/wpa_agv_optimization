"""Regression tests for AGV ID wrap-around guards in initializer / original_wpa."""

from __future__ import annotations

import unittest

import numpy as np

from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.initializer import PopulationInitializer
from src.wpa_agv_optimization.original_wpa import _open_next_agv as original_open_next_agv


class AgvIdBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        grid = np.zeros((20, 20), dtype=int)
        self.initializer = PopulationInitializer(grid, [])
        self.last_idx = len(Config.START_NODES) - 1

    def test_initializer_opens_next_slot_monotonically(self) -> None:
        next_id, agv = self.initializer._open_next_agv(0)
        self.assertEqual(next_id, 1)
        self.assertEqual(agv.id, 1)
        self.assertEqual(agv.start_pos, Config.START_NODES[1])

    def test_initializer_reaches_last_slot_without_raising(self) -> None:
        next_id, agv = self.initializer._open_next_agv(self.last_idx - 1)
        self.assertEqual(next_id, self.last_idx)
        self.assertEqual(agv.id, self.last_idx)

    def test_initializer_raises_when_last_slot_is_exhausted(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.initializer._open_next_agv(self.last_idx)
        self.assertIn("起点槽位上限", str(ctx.exception))

    def test_original_wpa_helper_reaches_last_slot_without_raising(self) -> None:
        next_id, agv = original_open_next_agv(self.last_idx - 1)
        self.assertEqual(next_id, self.last_idx)
        self.assertEqual(agv.start_pos, Config.START_NODES[self.last_idx])

    def test_original_wpa_helper_raises_when_last_slot_is_exhausted(self) -> None:
        with self.assertRaises(ValueError):
            original_open_next_agv(self.last_idx)


if __name__ == "__main__":
    unittest.main()
