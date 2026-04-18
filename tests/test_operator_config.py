"""Tests for the ImprovedOperatorConfig activation gates in WPAOperators."""

from __future__ import annotations

import unittest

from src.wpa_agv_optimization.config import ImprovedOperatorConfig
from src.wpa_agv_optimization.models import AGV, Task, Wolf
from src.wpa_agv_optimization.wpa_ops import WPAOperators


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


class OperatorConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks = [
            Task(1, 2, 2, 10, 60),
            Task(2, 6, 4, 10, 90),
        ]

    def test_default_config_matches_pre_refactor_hardcoded_values(self) -> None:
        """Defaults must preserve the original hardcoded behavior exactly."""
        cfg = ImprovedOperatorConfig()
        self.assertEqual(cfg.summoning_gap_threshold, 120.0)
        self.assertEqual(cfg.summoning_prob_close, 0.45)
        self.assertEqual(cfg.summoning_prob_far, 0.7)
        self.assertEqual(cfg.besieging_early_phase_divisor, 3)
        self.assertEqual(cfg.besieging_prob_early, 0.35)
        self.assertEqual(cfg.besieging_prob_late, 0.6)

    def test_summoning_zero_prob_always_rejects_and_returns_wolf(self) -> None:
        cfg = ImprovedOperatorConfig(summoning_prob_close=0.0, summoning_prob_far=0.0)
        operators = WPAOperators(evaluator=None, operator_config=cfg)
        wolf = _build_wolf([self.tasks])
        alpha = _build_wolf([self.tasks])
        wolf.fitness = 100.0
        alpha.fitness = 50.0
        self.assertIs(operators.summoning(wolf, alpha), wolf)

    def test_summoning_picks_prob_close_when_gap_below_threshold(self) -> None:
        # close=0 always rejects; far=1 would pass the gate (and then crash with evaluator=None)
        # so reaching "returns wolf" proves the close branch was taken.
        cfg = ImprovedOperatorConfig(
            summoning_gap_threshold=100.0,
            summoning_prob_close=0.0,
            summoning_prob_far=1.0,
        )
        operators = WPAOperators(evaluator=None, operator_config=cfg)
        wolf = _build_wolf([self.tasks])
        alpha = _build_wolf([self.tasks])
        wolf.fitness = 180.0
        alpha.fitness = 150.0  # gap=30 < 100 → close branch

        self.assertIs(operators.summoning(wolf, alpha), wolf)

    def test_summoning_picks_prob_far_when_gap_above_threshold(self) -> None:
        # Mirror of the above — far=0 rejects, close=1 would crash if the branch chose wrong.
        cfg = ImprovedOperatorConfig(
            summoning_gap_threshold=100.0,
            summoning_prob_close=1.0,
            summoning_prob_far=0.0,
        )
        operators = WPAOperators(evaluator=None, operator_config=cfg)
        wolf = _build_wolf([self.tasks])
        alpha = _build_wolf([self.tasks])
        wolf.fitness = 300.0
        alpha.fitness = 150.0  # gap=150 > 100 → far branch

        self.assertIs(operators.summoning(wolf, alpha), wolf)

    def test_besieging_zero_prob_always_rejects_and_returns_wolf(self) -> None:
        cfg = ImprovedOperatorConfig(besieging_prob_early=0.0, besieging_prob_late=0.0)
        operators = WPAOperators(evaluator=None, operator_config=cfg)
        wolf = _build_wolf([self.tasks])
        alpha = _build_wolf([self.tasks])
        result = operators.besieging(wolf, alpha, curr_iter=5, max_iter=50)
        self.assertIs(result, wolf)

    def test_besieging_early_phase_cutoff_uses_divisor(self) -> None:
        # divisor=4, max_iter=20 → early_cutoff = 5
        # early branch rejects (prob=0); late branch would crash if reached (prob=1, evaluator=None).
        cfg = ImprovedOperatorConfig(
            besieging_early_phase_divisor=4,
            besieging_prob_early=0.0,
            besieging_prob_late=1.0,
        )
        operators = WPAOperators(evaluator=None, operator_config=cfg)
        wolf = _build_wolf([self.tasks])
        alpha = _build_wolf([self.tasks])

        # curr_iter=4 < cutoff → early branch → prob=0 → reject
        self.assertIs(operators.besieging(wolf, alpha, curr_iter=4, max_iter=20), wolf)

        # Now flip: late rejects, early would crash — curr_iter=5 must take the late branch.
        cfg_flip = ImprovedOperatorConfig(
            besieging_early_phase_divisor=4,
            besieging_prob_early=1.0,
            besieging_prob_late=0.0,
        )
        operators_flip = WPAOperators(evaluator=None, operator_config=cfg_flip)
        self.assertIs(operators_flip.besieging(wolf, alpha, curr_iter=5, max_iter=20), wolf)


if __name__ == "__main__":
    unittest.main()
