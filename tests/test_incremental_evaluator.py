"""Regression tests for incremental evaluator and candidate prefiltering."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

import numpy as np

from src.wpa_agv_optimization.config import Config
from src.wpa_agv_optimization.evaluator import WolfEvaluator
from src.wpa_agv_optimization.models import AGV, Task, Wolf
from src.wpa_agv_optimization.traffic_manager import ConflictEvent
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


class IncrementalEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
        self.tasks = [
            Task(1, 2, 2, 10, 20),
            Task(2, 6, 4, 10, 35),
            Task(3, 7, 6, 10, 45),
        ]

    def test_incremental_rebuild_reuses_unchanged_prefix(self) -> None:
        base_wolf = _build_wolf([[self.tasks[0]], [self.tasks[1], self.tasks[2]]])
        base_evaluator = WolfEvaluator(self.grid_map)
        base_result = base_evaluator.rebuild_wolf(base_wolf)

        full_candidate = _build_wolf([[self.tasks[0]], [self.tasks[2], self.tasks[1]]])
        full_evaluator = WolfEvaluator(self.grid_map)
        full_plan_calls = 0
        full_plan = full_evaluator.planner.plan

        def full_plan_wrap(*args, **kwargs):
            nonlocal full_plan_calls
            full_plan_calls += 1
            return full_plan(*args, **kwargs)

        full_evaluator.planner.plan = full_plan_wrap
        full_result = full_evaluator.rebuild_wolf(full_candidate)

        incremental_candidate = _build_wolf([[self.tasks[0]], [self.tasks[2], self.tasks[1]]])
        incremental_evaluator = WolfEvaluator(self.grid_map)
        incremental_plan_calls = 0
        incremental_plan = incremental_evaluator.planner.plan

        def incremental_plan_wrap(*args, **kwargs):
            nonlocal incremental_plan_calls
            incremental_plan_calls += 1
            return incremental_plan(*args, **kwargs)

        incremental_evaluator.planner.plan = incremental_plan_wrap
        incremental_result = incremental_evaluator.rebuild_wolf(
            incremental_candidate,
            base_wolf=copy.deepcopy(base_result),
        )

        self.assertEqual(incremental_result.fitness, full_result.fitness)
        self.assertEqual(incremental_result.total_dist, full_result.total_dist)
        self.assertEqual(incremental_result.time_penalty, full_result.time_penalty)
        self.assertEqual(incremental_result.conflict_count, full_result.conflict_count)
        self.assertEqual(
            incremental_result.agv_list[0].path,
            base_result.agv_list[0].path,
        )
        self.assertLess(incremental_plan_calls, full_plan_calls)

    def test_prefilter_only_strictly_evaluates_top_candidates(self) -> None:
        operators = WPAOperators(evaluator=None)
        strict_calls: list[str] = []

        prepared_candidates = [
            ("slow", object(), 30.0),
            ("best", object(), 10.0),
            ("mid", object(), 20.0),
        ]

        def strict_eval(name, candidate_payload):
            strict_calls.append(name)
            return {"name": name, "fitness": {"slow": 300.0, "best": 100.0, "mid": 200.0}[name]}

        best = operators._evaluate_prepared_candidates(
            prepared_candidates=prepared_candidates,
            strict_eval=strict_eval,
            top_k=2,
        )

        self.assertEqual(strict_calls, ["best", "mid"])
        self.assertEqual(best["name"], "best")

    def test_adaptive_budget_evaluates_single_clear_winner(self) -> None:
        operators = WPAOperators(evaluator=None)
        strict_calls: list[str] = []
        prepared_candidates = [
            ("best", object(), 10.0),
            ("mid", object(), 30.0),
            ("slow", object(), 60.0),
        ]

        def strict_eval(name, candidate_payload):
            strict_calls.append(name)
            return {"name": name, "fitness": {"best": 100.0, "mid": 200.0, "slow": 300.0}[name]}

        best = operators._evaluate_prepared_candidates(
            prepared_candidates=prepared_candidates,
            strict_eval=strict_eval,
            top_k=None,
        )

        self.assertEqual(strict_calls, ["best"])
        self.assertEqual(best["name"], "best")

    def test_stable_decoder_preserves_unchanged_prefix_segment(self) -> None:
        operators = WPAOperators(evaluator=None)
        base_wolf = _build_wolf([[self.tasks[0]], [self.tasks[1], self.tasks[2]]])

        decoded = operators._decode_sequence_to_agvs_stable(
            [self.tasks[0], self.tasks[2], self.tasks[1]],
            base_wolf=base_wolf,
        )

        self.assertEqual(
            [[task.id for task in agv.tasks] for agv in decoded],
            [[1], [3, 2]],
        )

    def test_stable_prepare_candidate_pushes_first_changed_index_back(self) -> None:
        operators = WPAOperators(evaluator=None)
        base_wolf = _build_wolf([[self.tasks[0]], [self.tasks[1], self.tasks[2]]])
        evaluator = WolfEvaluator(self.grid_map)
        base_result = evaluator.rebuild_wolf(copy.deepcopy(base_wolf))

        prepared = operators._prepare_candidate(
            "stable",
            [self.tasks[0], self.tasks[2], self.tasks[1]],
            decoder="stable",
            base_wolf=base_result,
        )

        self.assertIsNotNone(prepared)
        _, decoded_agvs, _ = prepared
        candidate = Wolf()
        candidate.agv_list = decoded_agvs

        state = evaluator._build_initial_state(candidate, base_wolf=base_result)
        self.assertEqual(state["start_idx"], 1)

    def test_reserve_wait_window_stops_before_foreign_reservation(self) -> None:
        reservation_table = {(3, 10, 13)}
        reservation_owner = {(3, 10, 13): 0}
        agv_reserved_nodes = set()

        actual_end_time, conflict = WolfEvaluator._reserve_wait_window(
            agv_id=6,
            pos=(3, 10),
            start_time=7,
            end_time=15,
            reservation_table=reservation_table,
            reservation_owner=reservation_owner,
            agv_reserved_nodes=agv_reserved_nodes,
        )

        self.assertEqual(actual_end_time, 12)
        self.assertEqual(conflict["holder_id"], 0)
        self.assertEqual(conflict["time"], 13)
        self.assertEqual(reservation_owner[(3, 10, 13)], 0)
        self.assertNotIn((3, 10, 13), agv_reserved_nodes)
        self.assertIn((3, 10, 12), agv_reserved_nodes)

    def test_detect_conflict_event_prioritizes_foreign_edge_over_self_start_reservation(self) -> None:
        evaluator = WolfEvaluator(self.grid_map)
        agv = AGV(agv_id=5, start_pos=(0, 5))
        holder = AGV(agv_id=1, start_pos=(0, 1))
        holder.path = [(6, 10, 15), (6, 11, 16), (6, 12, 17)]
        segment_path = [(6, 12, 16), (6, 11, 17), (6, 10, 18)]
        reservation_table = {(6, 12, 16), (6, 11, 16)}
        reservation_owner = {(6, 12, 16): 5, (6, 11, 16): 1}
        occupied_edges = {(((6, 11), (6, 12), 17))}
        edge_owner = {((6, 11), (6, 12), 17): 1}

        conflict = evaluator._detect_conflict_event(
            agv=agv,
            segment_path=segment_path,
            reservation_table=reservation_table,
            reservation_owner=reservation_owner,
            occupied_edges=occupied_edges,
            edge_owner=edge_owner,
            agv_map={1: holder, 5: agv},
        )

        self.assertIsNotNone(conflict)
        self.assertEqual(conflict["kind"], "edge")
        self.assertEqual(conflict["holder_id"], 1)
        self.assertEqual(conflict["time"], 17)

    def test_rebuild_wolf_drops_segment_when_conflict_never_resolves(self) -> None:
        evaluator = WolfEvaluator(self.grid_map)
        wolf = Wolf()
        current = AGV(agv_id=0, start_pos=(0, 0))
        current.tasks = [self.tasks[0]]
        current.load = self.tasks[0].weight
        holder = AGV(agv_id=1, start_pos=(0, 1))
        wolf.agv_list = [current, holder]

        with mock.patch.object(evaluator.planner, "plan", return_value=[(0, 0, 0), (1, 0, 1)]), \
             mock.patch.object(
                 evaluator,
                 "_detect_conflict_event",
                 side_effect=lambda agv, *args, **kwargs: (
                     {"kind": "node", "time": 1, "holder_id": 1, "node": (1, 0), "edge": None}
                     if agv.id == 0 else None
                 ),
             ), \
             mock.patch.object(evaluator, "_detect_service_window_conflict", return_value=None), \
             mock.patch.object(
                 evaluator.traffic_manager,
                 "resolve_conflict",
                 return_value=ConflictEvent(
                     conflict_type="node",
                     conflict_subtype="node_shared_generic",
                     time_step=1,
                     agv_high=1,
                     agv_low=0,
                     action="wait",
                     risk_score=0.0,
                     node=(1, 0),
                 ),
             ):
            result = evaluator.rebuild_wolf(wolf)

        self.assertEqual(result.unfinished_count, 1)
        self.assertEqual(result.agv_list[0].path, [])

    def test_high_priority_current_agv_wait_conflict_is_upgraded_to_reroute(self) -> None:
        evaluator = WolfEvaluator(self.grid_map)
        wolf = Wolf()
        current = AGV(agv_id=0, start_pos=(0, 0))
        current.tasks = [self.tasks[0]]
        current.load = self.tasks[0].weight
        holder = AGV(agv_id=1, start_pos=(0, 1))
        wolf.agv_list = [current, holder]

        with mock.patch.object(evaluator.planner, "plan", return_value=[(0, 0, 0), (1, 0, 1)]), \
             mock.patch.object(
                 evaluator,
                 "_detect_conflict_event",
                 side_effect=lambda agv, *args, **kwargs: (
                     {"kind": "node", "time": 1, "holder_id": 1, "node": (1, 0), "edge": None}
                     if agv.id == 0 else None
                 ),
             ), \
             mock.patch.object(evaluator, "_detect_service_window_conflict", return_value=None), \
             mock.patch.object(
                 evaluator.traffic_manager,
                 "resolve_conflict",
                 return_value=ConflictEvent(
                     conflict_type="node",
                     conflict_subtype="node_shared_generic",
                     time_step=1,
                     agv_high=0,
                     agv_low=1,
                     action="wait",
                     risk_score=0.0,
                     node=(1, 0),
                 ),
             ):
            result = evaluator.rebuild_wolf(wolf)

        self.assertGreater(result.reroute_count, 0)
        self.assertEqual(result.replan_count, 0)

    def test_original_summoning_uses_shared_prepare_pipeline(self) -> None:
        operators = WPAOperators(evaluator=None)
        wolf = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])
        alpha = _build_wolf([[self.tasks[2], self.tasks[0], self.tasks[1]]])
        wolf.fitness = 100.0
        alpha.fitness = 80.0
        better = copy.deepcopy(wolf)
        better.fitness = 90.0
        prepared_calls = []

        def fake_prepare(name, task_seq, decoder="cost_based", base_wolf=None):
            prepared_calls.append((name, decoder, base_wolf is wolf, [task.id for task in task_seq]))
            return (name, object(), 10.0)

        def fake_evaluate(prepared_candidates, strict_eval, top_k=2):
            return better

        with mock.patch.object(operators, "_prepare_candidate", side_effect=fake_prepare), \
             mock.patch.object(operators, "_evaluate_prepared_candidates", side_effect=fake_evaluate), \
             mock.patch.object(operators, "_rebuild_from_task_sequence", side_effect=AssertionError("legacy rebuild path should not be used")):
            result = operators.original_summoning(wolf, alpha)

        self.assertIs(result, better)
        self.assertEqual(len(prepared_calls), 1)
        self.assertEqual(prepared_calls[0][1], "stable")
        self.assertTrue(prepared_calls[0][2])

    def test_original_besieging_uses_shared_prepare_pipeline(self) -> None:
        operators = WPAOperators(evaluator=None)
        wolf = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])
        alpha = _build_wolf([[self.tasks[0], self.tasks[2], self.tasks[1]]])
        wolf.fitness = 100.0
        alpha.fitness = 80.0
        better = copy.deepcopy(wolf)
        better.fitness = 90.0
        prepared_calls = []

        def fake_prepare(name, task_seq, decoder="cost_based", base_wolf=None):
            prepared_calls.append((name, decoder, base_wolf is wolf, [task.id for task in task_seq]))
            return (name, object(), 10.0)

        def fake_evaluate(prepared_candidates, strict_eval, top_k=2):
            return better

        with mock.patch.object(operators, "_prepare_candidate", side_effect=fake_prepare), \
             mock.patch.object(operators, "_evaluate_prepared_candidates", side_effect=fake_evaluate), \
             mock.patch.object(operators, "_rebuild_from_task_sequence", side_effect=AssertionError("legacy rebuild path should not be used")), \
             mock.patch("random.sample", return_value=[0, 1]):
            result = operators.original_besieging(wolf, alpha)

        self.assertIs(result, better)
        self.assertEqual(len(prepared_calls), 1)
        self.assertEqual(prepared_calls[0][1], "stable")
        self.assertTrue(prepared_calls[0][2])

    def test_dominant_objective_component_uses_weighted_cost_pressure(self) -> None:
        operators = WPAOperators(evaluator=None)
        wolf = _build_wolf([[self.tasks[0], self.tasks[1]], [self.tasks[2]]])
        wolf.vehicle_num = 2
        wolf.total_dist = 120
        wolf.time_penalty = 35
        wolf.conflict_count = 4
        wolf.replan_count = 1
        wolf.deadlock_risk_count = 0

        self.assertEqual(operators._dominant_objective_component(wolf), "time")

    def test_prepare_strategy_candidate_separates_decode_and_eval_bases(self) -> None:
        operators = WPAOperators(evaluator=None)
        wolf = _build_wolf([[self.tasks[0], self.tasks[1], self.tasks[2]]])
        alpha = _build_wolf([[self.tasks[2], self.tasks[0], self.tasks[1]]])
        prepare_calls = []

        def fake_prepare(name, task_seq, decoder="cost_based", base_wolf=None):
            prepare_calls.append((name, decoder, base_wolf, [task.id for task in task_seq]))
            return (name, object(), 10.0)

        with mock.patch.object(operators, "_prepare_candidate", side_effect=fake_prepare):
            prepared = operators._prepare_strategy_candidate(
                "alpha-follow",
                [self.tasks[0], self.tasks[1], self.tasks[2]],
                decoder="stable",
                decode_base_wolf=alpha,
                eval_base_wolf=wolf,
            )

        self.assertIsNotNone(prepared)
        self.assertEqual(prepare_calls[0][0], "alpha-follow")
        self.assertEqual(prepare_calls[0][1], "stable")
        self.assertIs(prepare_calls[0][2], alpha)
        self.assertIs(prepared["eval_base_wolf"], wolf)

    def test_follow_shape_base_prefers_lower_vehicle_layout(self) -> None:
        operators = WPAOperators(evaluator=None)
        low_vehicle = _build_wolf([[self.tasks[0], self.tasks[1]], [self.tasks[2]]])
        high_vehicle = _build_wolf([[self.tasks[0]], [self.tasks[1]], [self.tasks[2]]])
        low_vehicle.vehicle_num = 2
        high_vehicle.vehicle_num = 3

        self.assertIs(operators._follow_shape_base(low_vehicle, high_vehicle), low_vehicle)
        self.assertIs(operators._follow_shape_base(high_vehicle, low_vehicle), low_vehicle)

    def test_shorten_bottleneck_route_reorders_tasks_to_reduce_route_cost(self) -> None:
        operators = WPAOperators(evaluator=None)
        t1 = Task(10, 1, 1, 10, 50)
        t2 = Task(11, 9, 9, 10, 80)
        t3 = Task(12, 2, 2, 10, 60)
        wolf = _build_wolf([[t1, t2, t3]])
        agv = wolf.agv_list[0]
        before = operators._estimate_route_cost(agv.tasks, agv.start_pos)

        candidate = operators._shorten_bottleneck_route_sequence(wolf)

        self.assertIsNotNone(candidate)
        after = operators._estimate_route_cost(candidate, agv.start_pos)
        self.assertLess(after, before)
        self.assertEqual(sorted(task.id for task in candidate), [10, 11, 12])


if __name__ == "__main__":
    unittest.main()

