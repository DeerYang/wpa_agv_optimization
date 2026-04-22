"""Tests ensuring fixed scenarios respect the shelf-adjacency contract."""

from __future__ import annotations

import unittest

from src.wpa_agv_optimization.main import load_scenario
from src.wpa_agv_optimization.scenario_inputs import SCENARIO_LIBRARY
from src.wpa_agv_optimization.utils import is_valid_pick_location


class ScenarioTaskPositionTests(unittest.TestCase):
    def test_all_scenarios_load_without_error(self) -> None:
        for idx in range(1, len(SCENARIO_LIBRARY) + 1):
            load_scenario(idx)

    def test_every_task_is_shelf_adjacent(self) -> None:
        for idx, scenario in enumerate(SCENARIO_LIBRARY, start=1):
            obstacles = {tuple(p) for p in scenario["obstacles"]}
            for i, task in enumerate(scenario["tasks"], start=1):
                pos = (task["x"], task["y"])
                self.assertTrue(
                    is_valid_pick_location(pos, obstacles),
                    msg=f"Scenario {idx} task#{i} {pos} is not shelf-adjacent",
                )

    def test_no_duplicate_task_positions(self) -> None:
        for idx, scenario in enumerate(SCENARIO_LIBRARY, start=1):
            positions = [(t["x"], t["y"]) for t in scenario["tasks"]]
            self.assertEqual(
                len(set(positions)),
                len(positions),
                msg=f"Scenario {idx} has duplicate task positions",
            )


if __name__ == "__main__":
    unittest.main()
