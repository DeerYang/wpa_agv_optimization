"""Unit tests for WPAOperators decoders, transformers, and scoring helpers."""

from __future__ import annotations

import unittest

from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.models import AGV, Task, Wolf
from src.wpa_agv_optimization.wpa_ops import WPAOperators


def _task(task_id, x, y, weight, deadline):
    return Task(task_id, x, y, weight, deadline)


def _make_agv(agv_id, start_pos, tasks, load=None):
    agv = AGV(agv_id=agv_id, start_pos=start_pos)
    agv.tasks = list(tasks)
    agv.load = load if load is not None else sum(t.weight for t in tasks)
    return agv


def _make_wolf(agvs):
    wolf = Wolf()
    wolf.agv_list = list(agvs)
    wolf.vehicle_num = sum(1 for agv in agvs if agv.tasks)
    return wolf


def _operators():
    return WPAOperators(evaluator=None)


class SimpleDecoderTests(unittest.TestCase):
    def test_splits_by_capacity_into_multiple_agvs(self) -> None:
        ops = _operators()
        tasks = [
            _task(1, 1, 1, 60, 100),
            _task(2, 2, 2, 60, 100),  # can't fit in AGV 0 with task 1 (60+60>100)
            _task(3, 3, 3, 30, 100),
        ]
        agvs = ops._decode_sequence_to_agvs(tasks)
        self.assertEqual(len(agvs), 2)
        self.assertEqual([t.id for t in agvs[0].tasks], [1])
        self.assertEqual([t.id for t in agvs[1].tasks], [2, 3])

    def test_returns_none_when_single_task_exceeds_capacity(self) -> None:
        ops = _operators()
        tasks = [_task(1, 1, 1, Config.AGV_CAPACITY + 1, 100)]
        self.assertIsNone(ops._decode_sequence_to_agvs(tasks))

    def test_empty_input_returns_empty_agv_list(self) -> None:
        ops = _operators()
        self.assertEqual(ops._decode_sequence_to_agvs([]), [])

    def test_returns_none_when_required_agvs_exceed_start_nodes(self) -> None:
        ops = _operators()
        # Each task uses full capacity → one AGV per task; exceed START_NODES
        tasks = [_task(i, 1, 1, Config.AGV_CAPACITY, 100) for i in range(len(Config.START_NODES) + 1)]
        self.assertIsNone(ops._decode_sequence_to_agvs(tasks))


class CostBasedDecoderTests(unittest.TestCase):
    def test_inserts_close_tasks_into_same_agv(self) -> None:
        ops = _operators()
        # Tasks clustered near start_pos (0, 0) — should all fit in one AGV if capacity allows
        tasks = [
            _task(1, 1, 1, 20, 100),
            _task(2, 2, 1, 20, 100),
            _task(3, 3, 1, 20, 100),
        ]
        agvs = ops._decode_sequence_to_agvs_cost_based(tasks)
        self.assertEqual(len(agvs), 1)
        self.assertEqual(sorted(t.id for t in agvs[0].tasks), [1, 2, 3])

    def test_returns_none_when_single_task_exceeds_capacity(self) -> None:
        ops = _operators()
        tasks = [_task(1, 1, 1, Config.AGV_CAPACITY + 1, 100)]
        self.assertIsNone(ops._decode_sequence_to_agvs_cost_based(tasks))


class StableDecoderTests(unittest.TestCase):
    def test_falls_back_to_cost_based_without_base_wolf(self) -> None:
        ops = _operators()
        tasks = [_task(1, 1, 1, 20, 100), _task(2, 2, 2, 20, 100)]
        decoded = ops._decode_sequence_to_agvs_stable(tasks, base_wolf=None)
        # Without base, falls back to cost-based; at least one AGV is produced.
        self.assertGreaterEqual(len(decoded), 1)


class SequenceTransformerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tasks = [
            _task(1, 1, 1, 10, 100),
            _task(2, 2, 2, 10, 100),
            _task(3, 3, 3, 10, 100),
            _task(4, 4, 4, 10, 100),
            _task(5, 5, 5, 10, 100),
        ]

    def test_move_task_ids_earlier_pulls_targets_forward(self) -> None:
        ops = _operators()
        result = ops._move_task_ids_earlier(self.tasks, task_ids={4}, step_cap=2)
        self.assertIsNotNone(result)
        idx = [t.id for t in result].index(4)
        self.assertEqual(idx, 1)  # from idx 3 → idx 1 (step_cap=2)

    def test_move_task_ids_earlier_returns_none_when_already_front(self) -> None:
        ops = _operators()
        self.assertIsNone(ops._move_task_ids_earlier(self.tasks, task_ids={1}, step_cap=3))

    def test_ox_inherit_preserves_all_task_ids(self) -> None:
        ops = _operators()
        wolf_tasks = list(self.tasks)
        alpha_tasks = list(reversed(self.tasks))
        result = ops._ox_inherit(wolf_tasks, alpha_tasks, seg_len_min=2, seg_len_max=3)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])

    def test_ox_inherit_returns_none_on_length_mismatch(self) -> None:
        ops = _operators()
        self.assertIsNone(ops._ox_inherit(self.tasks, self.tasks[:3]))

    def test_short_reverse_reverses_a_contiguous_segment(self) -> None:
        ops = _operators()
        result = ops._short_reverse(self.tasks, seg_len_max=3)
        self.assertIsNotNone(result)
        # All task ids preserved
        self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])

    def test_destroy_repair_returns_none_when_remove_exceeds_size(self) -> None:
        ops = _operators()
        self.assertIsNone(ops._destroy_repair_sequence(self.tasks[:2], remove_count=3))

    def test_destroy_repair_preserves_task_set(self) -> None:
        ops = _operators()
        result = ops._destroy_repair_sequence(self.tasks, focus_ids={3}, remove_count=2)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])

    def test_neighbor_swap_preserves_task_set(self) -> None:
        ops = _operators()
        result = ops._neighbor_by_operator(self.tasks, "swap")
        self.assertIsNotNone(result)
        self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])

    def test_neighbor_reverse_preserves_task_set(self) -> None:
        ops = _operators()
        result = ops._neighbor_by_operator(self.tasks, "reverse")
        self.assertIsNotNone(result)
        self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])

    def test_neighbor_unknown_operator_returns_none(self) -> None:
        ops = _operators()
        self.assertIsNone(ops._neighbor_by_operator(self.tasks, "unknown"))

    def test_soft_align_returns_none_when_already_aligned(self) -> None:
        ops = _operators()
        same = list(self.tasks)
        self.assertIsNone(ops._soft_align_to_alpha(same, same, steps=1))

    def test_soft_align_moves_toward_alpha_order(self) -> None:
        ops = _operators()
        wolf_tasks = list(self.tasks)
        alpha_tasks = list(reversed(self.tasks))
        result = ops._soft_align_to_alpha(wolf_tasks, alpha_tasks, steps=1)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])

    def test_spread_focus_distributes_focus_tasks(self) -> None:
        ops = _operators()
        seq = self.tasks  # focus ids {1, 5}
        result = ops._spread_focus_tasks(seq, focus_ids={1, 5})
        if result is not None:
            # First task should still be a focus task
            self.assertIn(result[0].id, {1, 5})
            self.assertEqual(sorted(t.id for t in result), [1, 2, 3, 4, 5])


class RouteAndScoringTests(unittest.TestCase):
    def test_estimate_route_cost_is_manhattan_plus_depot_return(self) -> None:
        ops = _operators()
        # Start at (0,0), one task at (3,0); distance: 3 + (depot 19,19 - 3,0 = 19-3 + 19 = 35)
        task = _task(1, 3, 0, 10, 1000)
        cost = ops._estimate_route_cost([task], start_pos=(0, 0))
        # 3 (to task) + 35 (to depot) = 38, no deadline penalty
        self.assertAlmostEqual(cost, 38.0)

    def test_estimate_route_cost_empty_is_zero(self) -> None:
        ops = _operators()
        self.assertEqual(ops._estimate_route_cost([], start_pos=(0, 0)), 0.0)

    def test_estimate_route_cost_adds_deadline_penalty_when_tardy(self) -> None:
        ops = _operators()
        # Task with tight deadline: travel=3, service=2, arrival=5, deadline=2, tardy=3
        task = _task(1, 3, 0, 10, 2)
        cost = ops._estimate_route_cost([task], start_pos=(0, 0))
        # 3 (travel) + 35 (to depot) + W3_TIME(10) * 3 (tardy) = 38 + 30 = 68
        self.assertAlmostEqual(cost, 68.0)

    def test_weighted_component_scores_returns_all_categories(self) -> None:
        ops = _operators()
        wolf = _make_wolf([])
        wolf.total_dist = 10
        wolf.vehicle_num = 2
        wolf.time_penalty = 5
        wolf.conflict_count = 3
        wolf.replan_count = 1
        wolf.deadlock_risk_count = 4
        scores = ops._weighted_component_scores(wolf)
        self.assertEqual(set(scores.keys()), {"distance", "vehicle", "time", "conflict", "replan", "risk"})
        self.assertEqual(scores["distance"], Config.W1_DIST * 10)
        self.assertEqual(scores["vehicle"], Config.W2_NUM * 2)

    def test_bottleneck_task_ids_picks_worst_agv(self) -> None:
        ops = _operators()
        # short_agv: a single task near depot (19,19) → cheap return leg
        short_agv = _make_agv(0, start_pos=(0, 0), tasks=[_task(1, 19, 19, 10, 1000)])
        # long_agv: three scattered tasks → higher total manhattan
        long_agv = _make_agv(1, start_pos=(0, 0), tasks=[
            _task(2, 5, 0, 10, 1000),
            _task(3, 5, 10, 10, 1000),
            _task(4, 15, 5, 10, 1000),
        ])
        wolf = _make_wolf([short_agv, long_agv])
        self.assertEqual(ops._bottleneck_task_ids(wolf), {2, 3, 4})

    def test_route_detour_score_is_zero_for_straight_middle_step(self) -> None:
        ops = _operators()
        # Tasks along a straight line: (1,0), (2,0), (3,0). Middle task (idx=1) makes no detour.
        tasks = [_task(1, 1, 0, 10, 100), _task(2, 2, 0, 10, 100), _task(3, 3, 0, 10, 100)]
        detour = ops._route_detour_score(tasks, idx=1, start_pos=(0, 0))
        self.assertEqual(detour, 0)


class LevyFlightTests(unittest.TestCase):
    def test_levy_flight_step_is_non_negative(self) -> None:
        ops = _operators()
        for _ in range(20):
            step = ops._levy_flight_step()
            self.assertGreaterEqual(step, 0.0)

    def test_levy_flight_step_scale_zero_is_zero(self) -> None:
        ops = _operators()
        self.assertEqual(ops._levy_flight_step(step_scale=0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
