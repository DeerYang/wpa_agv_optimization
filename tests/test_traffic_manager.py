"""Unit tests for TrafficManager conflict detection, classification, and resolution."""

from __future__ import annotations

import unittest

from src.wpa_agv_optimization.models import AGV, Task
from src.wpa_agv_optimization.traffic_manager import TrafficManager


def _make_agv(agv_id, start_pos=(0, 0), tasks=None, load=0, path=None):
    agv = AGV(agv_id=agv_id, start_pos=start_pos)
    agv.tasks = list(tasks or [])
    agv.load = load
    agv.path = list(path or [])
    return agv


def _task(task_id, x, y, weight, deadline):
    return Task(task_id, x, y, weight, deadline)


class LocateStateTests(unittest.TestCase):
    def test_returns_prev_curr_next_at_matching_time(self) -> None:
        path = [(0, 0, 0), (1, 0, 1), (2, 0, 2), (3, 0, 3)]
        state = TrafficManager._locate_state(path, 2)
        self.assertEqual(state, ((1, 0), (2, 0), (3, 0)))

    def test_first_step_has_prev_equal_to_curr(self) -> None:
        path = [(0, 0, 0), (1, 0, 1)]
        prev, curr, _ = TrafficManager._locate_state(path, 0)
        self.assertEqual(prev, curr)

    def test_last_step_has_next_equal_to_curr(self) -> None:
        path = [(0, 0, 0), (1, 0, 1)]
        _, curr, nxt = TrafficManager._locate_state(path, 1)
        self.assertEqual(nxt, curr)

    def test_time_missing_returns_none(self) -> None:
        path = [(0, 0, 0), (1, 0, 1)]
        self.assertIsNone(TrafficManager._locate_state(path, 5))


class MovementPatternTests(unittest.TestCase):
    def test_none_state_is_unknown(self) -> None:
        self.assertEqual(TrafficManager._movement_pattern(None), "unknown")

    def test_hold_when_prev_equals_curr(self) -> None:
        self.assertEqual(
            TrafficManager._movement_pattern(((1, 1), (1, 1), (2, 1))),
            "hold",
        )

    def test_hold_when_next_equals_curr(self) -> None:
        self.assertEqual(
            TrafficManager._movement_pattern(((1, 1), (2, 1), (2, 1))),
            "hold",
        )

    def test_straight_when_direction_continues(self) -> None:
        self.assertEqual(
            TrafficManager._movement_pattern(((0, 0), (1, 0), (2, 0))),
            "straight",
        )

    def test_turn_when_direction_changes(self) -> None:
        self.assertEqual(
            TrafficManager._movement_pattern(((0, 0), (1, 0), (1, 1))),
            "turn",
        )


class CrossRelationTests(unittest.TestCase):
    def test_orthogonal_merge_is_cross(self) -> None:
        # a moves up, b moves right, meet at (1, 1)
        a = ((1, 0), (1, 1), (1, 2))
        b = ((0, 1), (1, 1), (2, 1))
        self.assertTrue(TrafficManager._cross_relation(a, b))

    def test_anti_parallel_same_node_is_not_cross(self) -> None:
        # head-on collision on the same node: not a "cross-merge"
        a = ((0, 1), (1, 1), (2, 1))
        b = ((2, 1), (1, 1), (0, 1))
        self.assertFalse(TrafficManager._cross_relation(a, b))

    def test_same_direction_same_node_is_not_cross(self) -> None:
        a = ((0, 1), (1, 1), (2, 1))
        b = ((0, 1), (1, 1), (2, 1))
        self.assertFalse(TrafficManager._cross_relation(a, b))

    def test_different_curr_is_not_cross(self) -> None:
        a = ((0, 0), (1, 0), (2, 0))
        b = ((0, 1), (1, 1), (2, 1))
        self.assertFalse(TrafficManager._cross_relation(a, b))

    def test_none_input_is_not_cross(self) -> None:
        a = ((0, 0), (1, 0), (2, 0))
        self.assertFalse(TrafficManager._cross_relation(a, None))
        self.assertFalse(TrafficManager._cross_relation(None, a))


class IsRearFollowTests(unittest.TestCase):
    def test_same_direction_follow_is_rear(self) -> None:
        # holder at (1,0) at t-1 moves to (2,0) at t; current enters (1,0) at t
        curr_t = ((0, 0), (1, 0), (2, 0))       # curr: (0,0)->(1,0)->(2,0) moving right
        holder_tm1 = ((0, 0), (1, 0), (2, 0))   # holder at (1,0) at t-1
        holder_t = ((1, 0), (2, 0), (3, 0))     # holder at (2,0) at t
        self.assertTrue(TrafficManager._is_rear_follow(curr_t, holder_tm1, holder_t))

    def test_holder_stationary_is_not_rear(self) -> None:
        curr_t = ((0, 0), (1, 0), (2, 0))
        holder_tm1 = ((1, 0), (1, 0), (1, 0))
        holder_t = ((1, 0), (1, 0), (1, 0))
        self.assertFalse(TrafficManager._is_rear_follow(curr_t, holder_tm1, holder_t))

    def test_opposite_direction_is_not_rear(self) -> None:
        curr_t = ((0, 0), (1, 0), (2, 0))
        holder_tm1 = ((2, 0), (1, 0), (0, 0))
        holder_t = ((1, 0), (0, 0), (-1, 0))
        self.assertFalse(TrafficManager._is_rear_follow(curr_t, holder_tm1, holder_t))


class ConflictDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tm = TrafficManager()

    def test_node_conflict_matches_reservation(self) -> None:
        segment = [(0, 0, 0), (1, 0, 1), (2, 0, 2)]
        reservation = {(1, 0, 1)}
        hit = self.tm.detect_node_conflict(agv_id=0, segment_path=segment, reservation_table=reservation)
        self.assertEqual(hit, (1, (1, 0)))

    def test_node_conflict_empty_path_returns_none(self) -> None:
        self.assertIsNone(self.tm.detect_node_conflict(0, [], {(1, 0, 1)}))

    def test_edge_conflict_detects_opposite_direction(self) -> None:
        segment = [(0, 0, 0), (1, 0, 1)]
        occupied = {((1, 0), (0, 0), 1)}
        hit = self.tm.detect_edge_conflict(segment, occupied)
        self.assertEqual(hit, (1, ((0, 0), (1, 0))))

    def test_edge_conflict_none_when_same_direction(self) -> None:
        segment = [(0, 0, 0), (1, 0, 1)]
        occupied = {((0, 0), (1, 0), 1)}  # same direction, same edge
        self.assertIsNone(self.tm.detect_edge_conflict(segment, occupied))

    def test_rear_conflict_uses_t_minus_one(self) -> None:
        segment = [(0, 0, 0), (1, 0, 1)]
        reservation = {(1, 0, 0)}  # holder at (1,0) at t=0; current enters at t=1
        hit = self.tm.detect_rear_conflict(segment, reservation)
        self.assertEqual(hit, (1, (1, 0)))


class ClassifyConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tm = TrafficManager()

    def test_edge_conflict_is_edge_head_on(self) -> None:
        agv_a = _make_agv(1)
        agv_b = _make_agv(2)
        result = self.tm.classify_conflict(
            conflict_type="edge",
            time_step=1,
            agv_current=agv_a,
            agv_holder=agv_b,
            segment_path=[(0, 0, 0), (1, 0, 1)],
        )
        self.assertEqual(result, "edge_head_on")

    def test_node_service_block_when_holder_is_stationary(self) -> None:
        segment = [(0, 0, 0), (1, 0, 1)]
        holder = _make_agv(2, path=[(1, 0, 0), (1, 0, 1), (1, 0, 2)])
        result = self.tm.classify_conflict(
            conflict_type="node",
            time_step=1,
            agv_current=_make_agv(1, path=segment),
            agv_holder=holder,
            segment_path=segment,
            node=(1, 0),
        )
        self.assertEqual(result, "node_service_block")

    def test_node_cross_merge_when_orthogonal(self) -> None:
        # current moves up through (1,1); holder moves right through (1,1) at same time
        current_path = [(1, 0, 0), (1, 1, 1), (1, 2, 2)]
        holder_path = [(0, 1, 0), (1, 1, 1), (2, 1, 2)]
        result = self.tm.classify_conflict(
            conflict_type="node",
            time_step=1,
            agv_current=_make_agv(1, path=current_path),
            agv_holder=_make_agv(2, path=holder_path),
            segment_path=current_path,
            node=(1, 1),
        )
        self.assertEqual(result, "node_cross_merge")

    def test_rear_follow_when_directions_match(self) -> None:
        # current steps into node that holder just vacated, both moving right
        segment = [(0, 0, 0), (1, 0, 1)]
        holder_path = [(0, 0, 0), (1, 0, 0), (2, 0, 1)]  # holder at (1,0) at t=0, (2,0) at t=1
        # Note: path entries are unique per time in normal usage; this synthetic path
        # is constructed so _locate_state can find t-1 and t for the holder.
        holder = _make_agv(2, path=[(1, 0, 0), (2, 0, 1)])
        current = _make_agv(1, path=segment)
        result = self.tm.classify_conflict(
            conflict_type="rear",
            time_step=1,
            agv_current=current,
            agv_holder=holder,
            segment_path=segment,
            node=(1, 0),
        )
        self.assertEqual(result, "rear_follow")


class PriorityAndYieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tm = TrafficManager()

    def test_priority_score_is_higher_for_urgent_deadline(self) -> None:
        urgent = _make_agv(1, tasks=[_task(1, 5, 5, 20, 10)], load=50)
        relaxed = _make_agv(2, tasks=[_task(2, 5, 5, 20, 500)], load=50)
        p_urgent = self.tm.compute_priority(urgent, current_time=0, remain_dist_est=10)
        p_relaxed = self.tm.compute_priority(relaxed, current_time=0, remain_dist_est=10)
        self.assertGreater(p_urgent, p_relaxed)

    def test_priority_no_tasks_has_zero_urgency_component(self) -> None:
        empty = _make_agv(1, tasks=[], load=0)
        # only load and remain contribute; with load=0 and remain=∞(1e9), score ≈ 0
        score = self.tm.compute_priority(empty, current_time=0, remain_dist_est=10**9)
        self.assertAlmostEqual(score, 0.0, places=6)

    def test_choose_yield_picks_higher_priority_as_high(self) -> None:
        urgent = _make_agv(1, tasks=[_task(1, 5, 5, 20, 10)], load=90)
        relaxed = _make_agv(2, tasks=[_task(2, 5, 5, 20, 500)], load=10)
        high, low = self.tm.choose_yield_agv(urgent, relaxed, time_step=0, remain_dist_a=5, remain_dist_b=5)
        self.assertEqual(high, urgent.id)
        self.assertEqual(low, relaxed.id)


class WaitGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tm = TrafficManager()

    def test_self_loop_is_ignored(self) -> None:
        self.tm.add_wait_dependency(5, 5)
        self.assertEqual(self.tm.wait_graph, {})

    def test_cycle_detection_finds_two_node_loop(self) -> None:
        self.tm.add_wait_dependency(1, 2)
        self.tm.add_wait_dependency(2, 1)
        cycle = self.tm.detect_deadlock_cycle()
        self.assertIsNotNone(cycle)
        self.assertEqual(set(cycle), {1, 2})

    def test_cycle_detection_returns_none_when_acyclic(self) -> None:
        self.tm.add_wait_dependency(1, 2)
        self.tm.add_wait_dependency(2, 3)
        self.assertIsNone(self.tm.detect_deadlock_cycle())

    def test_clear_wait_dependency_removes_edges(self) -> None:
        self.tm.add_wait_dependency(1, 2)
        self.tm.add_wait_dependency(2, 1)
        self.tm.clear_wait_dependency(1)
        self.assertIsNone(self.tm.detect_deadlock_cycle())


class DeadlockRiskTests(unittest.TestCase):
    def test_cycle_adds_large_constant_to_score(self) -> None:
        tm = TrafficManager()
        no_cycle = tm.estimate_deadlock_risk(wait_count=1, repeat_conflict_count=1, repeated_resource_count=1)
        with_cycle = tm.estimate_deadlock_risk(
            wait_count=1, repeat_conflict_count=1, repeated_resource_count=1, has_cycle=True
        )
        self.assertAlmostEqual(with_cycle - no_cycle, 3.0, places=6)

    def test_pick_victim_picks_lowest_priority_in_cycle(self) -> None:
        tm = TrafficManager()
        urgent = _make_agv(1, tasks=[_task(1, 5, 5, 20, 10)], load=90)
        relaxed = _make_agv(2, tasks=[_task(2, 5, 5, 20, 500)], load=10)
        victim = tm.pick_victim_for_deadlock([1, 2], {1: urgent, 2: relaxed})
        self.assertEqual(victim, relaxed.id)


class ResolveConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tm = TrafficManager()
        self.agv_a = _make_agv(1, tasks=[_task(1, 5, 5, 20, 60)], load=50)
        self.agv_b = _make_agv(2, tasks=[_task(2, 5, 5, 20, 60)], load=50)

    def test_has_cycle_forces_replan(self) -> None:
        event = self.tm.resolve_conflict(
            conflict_type="node",
            conflict_subtype="node_shared_generic",
            agv_a=self.agv_a,
            agv_b=self.agv_b,
            time_step=1,
            remain_dist_a=5,
            remain_dist_b=5,
            has_cycle=True,
        )
        self.assertEqual(event.action, "replan")

    def test_wait_threshold_forces_replan(self) -> None:
        event = self.tm.resolve_conflict(
            conflict_type="node",
            conflict_subtype="node_service_block",
            agv_a=self.agv_a,
            agv_b=self.agv_b,
            time_step=1,
            remain_dist_a=5,
            remain_dist_b=5,
            low_wait_count=self.tm.wait_threshold,  # hit threshold
        )
        self.assertEqual(event.action, "replan")

    def test_edge_head_on_with_low_risk_waits(self) -> None:
        event = self.tm.resolve_conflict(
            conflict_type="edge",
            conflict_subtype="edge_head_on",
            agv_a=self.agv_a,
            agv_b=self.agv_b,
            time_step=1,
            remain_dist_a=5,
            remain_dist_b=5,
        )
        self.assertEqual(event.action, "wait")

    def test_edge_head_on_with_high_risk_reroutes(self) -> None:
        # risk = 0.9 * 2 + 0.6 * 1 = 2.4, above reroute_risk (2.2) but below deadlock_risk (3.5)
        event = self.tm.resolve_conflict(
            conflict_type="edge",
            conflict_subtype="edge_head_on",
            agv_a=self.agv_a,
            agv_b=self.agv_b,
            time_step=1,
            remain_dist_a=5,
            remain_dist_b=5,
            repeat_conflict_count=2,
            repeated_resource_count=1,
        )
        self.assertEqual(event.action, "reroute")

    def test_rear_follow_reroutes_after_repeated_conflicts(self) -> None:
        event = self.tm.resolve_conflict(
            conflict_type="rear",
            conflict_subtype="rear_follow",
            agv_a=self.agv_a,
            agv_b=self.agv_b,
            time_step=1,
            remain_dist_a=5,
            remain_dist_b=5,
            repeat_conflict_count=2,
        )
        self.assertEqual(event.action, "reroute")


if __name__ == "__main__":
    unittest.main()
