"""Tests for the paper-faithful original WPA implementation."""

from __future__ import annotations

import random
import unittest
from unittest import mock

import numpy as np

from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.models import Task
from src.wpa_agv_optimization.original_wpa import (
    OriginalWPAConfig,
    OriginalWPAOptimizer,
    PaperWolfState,
    compute_d_near,
    compute_step_sizes,
    decode_priority_vector,
    select_role_indices,
)


class _RoleRng:
    def choice(self, seq):
        return seq[-1]

    def randint(self, low, high):
        return high


class OriginalWPAHelperTests(unittest.TestCase):
    def test_step_sizes_follow_paper_relationship(self) -> None:
        mins = np.array([0.0, 0.0, 0.0])
        maxs = np.array([10.0, 20.0, 30.0])

        step_a, step_b, step_c = compute_step_sizes(mins, maxs, step_factor=1000.0)

        np.testing.assert_allclose(step_b, step_a * 2.0)
        np.testing.assert_allclose(step_a, step_c * 2.0)
        np.testing.assert_allclose(step_a, (maxs - mins) / 1000.0)

    def test_d_near_follows_paper_formula(self) -> None:
        mins = np.array([0.0, 0.0, 0.0, 0.0])
        maxs = np.array([4.0, 4.0, 4.0, 4.0])

        d_near = compute_d_near(mins, maxs, omega=500.0)

        self.assertAlmostEqual(d_near, 16.0 / (4.0 * 500.0))

    def test_decode_priority_vector_uses_sorted_keys_and_capacity_only_split(self) -> None:
        task_list = [
            Task(1, 1, 1, 60, 10),
            Task(2, 2, 2, 50, 10),
            Task(3, 3, 3, 10, 10),
        ]
        keys = np.array([0.2, 0.1, 0.3])

        agvs = decode_priority_vector(keys, task_list)

        self.assertEqual([[task.id for task in agv.tasks] for agv in agvs], [[2], [1, 3]])
        self.assertEqual([agv.start_pos for agv in agvs], [Config.START_NODES[0], Config.START_NODES[1]])

    def test_select_role_indices_uses_paper_ranges_and_excludes_leader(self) -> None:
        population = [
            PaperWolfState(position=np.array([float(i)]), wolf=None, fitness=float(i), smell=float(10 - i))
            for i in range(10)
        ]
        config = OriginalWPAConfig(alpha=4, beta=6, max_walks=20, omega=500.0, step_factor=1000.0)

        leader_idx, scout_indices, fierce_indices = select_role_indices(population, config, rng=random.Random(0))

        self.assertEqual(leader_idx, 0)
        self.assertNotIn(leader_idx, scout_indices)
        self.assertNotIn(leader_idx, fierce_indices)
        self.assertEqual(len(scout_indices), 2)
        self.assertEqual(len(fierce_indices), len(population) - len(scout_indices) - 1)

    def test_select_role_indices_randomizes_tied_leader_choice(self) -> None:
        population = [
            PaperWolfState(position=np.array([0.0]), wolf=None, fitness=1.0, smell=9.0),
            PaperWolfState(position=np.array([1.0]), wolf=None, fitness=1.0, smell=9.0),
            PaperWolfState(position=np.array([2.0]), wolf=None, fitness=2.0, smell=7.0),
            PaperWolfState(position=np.array([3.0]), wolf=None, fitness=3.0, smell=6.0),
        ]
        config = OriginalWPAConfig(alpha=4, beta=6, max_walks=20, omega=500.0, step_factor=1000.0)

        leader_idx, scout_indices, fierce_indices = select_role_indices(population, config, rng=_RoleRng())

        self.assertEqual(leader_idx, 1)
        self.assertNotIn(leader_idx, scout_indices)
        self.assertNotIn(leader_idx, fierce_indices)


class OriginalWPAFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        self.task_list = [Task(1, 1, 1, 10, 10)]
        self.optimizer = OriginalWPAOptimizer(
            self.grid_map,
            self.task_list,
            config=OriginalWPAConfig(alpha=4, beta=6, max_walks=4, omega=500.0, step_factor=1000.0),
            rng=random.Random(0),
        )

    @staticmethod
    def _state(marker: float, smell: float) -> PaperWolfState:
        return PaperWolfState(
            position=np.array([marker], dtype=float),
            wolf=None,
            fitness=float(-smell),
            smell=float(smell),
        )

    def test_scouting_phase_stops_after_first_scout_becomes_new_leader(self) -> None:
        population = [
            self._state(0.0, 10.0),
            self._state(1.0, 9.0),
            self._state(2.0, 8.0),
            self._state(3.0, 7.0),
        ]
        calls = []

        def fake_scout_step(state):
            calls.append(int(state.position[0]))
            if int(state.position[0]) == 1:
                return self._state(1.0, 11.0)
            raise AssertionError("later scouts should not run after one scout becomes leader")

        with mock.patch.object(self.optimizer, "_scout_step", side_effect=fake_scout_step):
            next_population, leader_idx, fierce_indices = self.optimizer._scouting_phase(
                population,
                leader_idx=0,
                scout_indices=[1, 2],
                fierce_indices=[3],
            )

        self.assertEqual(calls, [1])
        self.assertEqual(leader_idx, 1)
        self.assertIn(0, fierce_indices)
        self.assertEqual(next_population[1].smell, 11.0)

    def test_summoning_phase_restarts_when_fierce_wolf_becomes_new_leader(self) -> None:
        population = [
            self._state(0.0, 10.0),
            self._state(1.0, 9.0),
            self._state(2.0, 8.0),
            self._state(3.0, 7.0),
        ]
        calls = []

        def fake_summoning(state, leader):
            calls.append((int(state.position[0]), int(leader.position[0])))
            marker = int(state.position[0])
            leader_marker = int(leader.position[0])
            if marker == 2 and leader_marker == 0:
                return self._state(2.0, 12.0), False, True
            if marker == 3 and leader_marker == 2:
                return self._state(3.0, 7.0), True, False
            return state, False, False

        with mock.patch.object(self.optimizer, "_summoning", side_effect=fake_summoning):
            next_population, leader_idx, besiege_indices, fierce_indices = self.optimizer._summoning_phase(
                population,
                leader_idx=0,
                scout_indices=[1],
                fierce_indices=[2, 3],
            )

        self.assertEqual(calls, [(2, 0), (3, 2), (0, 2)])
        self.assertEqual(leader_idx, 2)
        self.assertEqual(next_population[2].smell, 12.0)
        self.assertIn(1, besiege_indices)
        self.assertIn(3, besiege_indices)
        self.assertIn(0, fierce_indices)

    def test_summoning_detects_two_step_oscillation_and_enters_besiege(self) -> None:
        fierce = self._state(9.0, 8.0)
        leader = self._state(10.0, 10.0)
        self.optimizer.step_b = np.array([4.0], dtype=float)
        self.optimizer.d_near = 0.1

        oscillating_states = [
            self._state(13.0, 8.0),
            self._state(9.0, 8.0),
        ]

        with mock.patch.object(self.optimizer, "_evaluate_position", side_effect=oscillating_states):
            candidate, entered_besiege, became_leader = self.optimizer._summoning(fierce, leader)

        self.assertEqual(float(candidate.position[0]), 9.0)
        self.assertTrue(entered_besiege)
        self.assertFalse(became_leader)

    def test_summoning_stops_when_decoded_order_stagnates(self) -> None:
        task_list = [Task(1, 1, 1, 10, 10), Task(2, 2, 2, 10, 10), Task(3, 3, 3, 10, 10)]
        optimizer = OriginalWPAOptimizer(
            self.grid_map,
            task_list,
            config=OriginalWPAConfig(
                alpha=4,
                beta=6,
                max_walks=4,
                omega=500.0,
                step_factor=1000.0,
                max_summon_steps=2000,
                summon_order_patience=3,
                max_new_orders_per_summon=80,
            ),
            rng=random.Random(0),
        )
        optimizer.step_b = np.array([0.01, 0.01, 0.01], dtype=float)
        optimizer.d_near = 0.001
        fierce = PaperWolfState(
            position=np.array([0.0, 10.0, 20.0], dtype=float),
            wolf=None,
            fitness=10.0,
            smell=-10.0,
        )
        leader = PaperWolfState(
            position=np.array([1.0, 11.0, 21.0], dtype=float),
            wolf=None,
            fitness=1.0,
            smell=-1.0,
        )
        calls = 0

        def fake_evaluate(position, base_wolf=None):
            nonlocal calls
            calls += 1
            return PaperWolfState(
                position=np.array(position, dtype=float),
                wolf=None,
                fitness=10.0,
                smell=-10.0,
            )

        with mock.patch.object(optimizer, "_evaluate_position", side_effect=fake_evaluate):
            candidate, entered_besiege, became_leader = optimizer._summoning(fierce, leader)

        self.assertEqual(calls, 3)
        self.assertTrue(entered_besiege)
        self.assertFalse(became_leader)
        self.assertEqual(optimizer._order_signature(candidate.position), optimizer._order_signature(fierce.position))


if __name__ == "__main__":
    unittest.main()
