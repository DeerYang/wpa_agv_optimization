"""
Conflict and deadlock coordination layer.

This module focuses on:
1. Conflict detection primitives (node/edge/rear).
2. Mutually exclusive subtype classification for strategy routing.
3. Priority/risk based action decisions (wait/reroute/replan).
4. Wait-graph cycle detection and deadlock victim selection.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .config import Config
from .utils import manhattan_dist


Node = Tuple[int, int]
Edge = Tuple[Node, Node]
TimedNode = Tuple[int, int, int]


@dataclass
class ConflictEvent:
    """Unified conflict decision payload for evaluator."""

    conflict_type: str
    conflict_subtype: str
    time_step: int
    agv_high: int
    agv_low: int
    action: str
    risk_score: float
    node: Optional[Node] = None
    edge: Optional[Edge] = None
    detail: str = ""


class TrafficManager:
    """Policy engine for conflict/deadlock handling."""

    def __init__(
        self,
        urgent_w: float = 0.5,
        load_w: float = 0.3,
        remain_w: float = 0.2,
        wait_threshold: int = 3,
        reroute_risk_threshold: float = 2.2,
        deadlock_risk_threshold: float = 3.5,
    ):
        self.urgent_w = urgent_w
        self.load_w = load_w
        self.remain_w = remain_w
        self.wait_threshold = wait_threshold
        self.reroute_risk_threshold = reroute_risk_threshold
        self.deadlock_risk_threshold = deadlock_risk_threshold
        self.wait_graph: Dict[int, Set[int]] = {}

    @staticmethod
    def _locate_state(path: Iterable[TimedNode], time_step: int) -> Optional[Tuple[Node, Node, Node]]:
        """
        Return (prev, curr, next) node triplet at a specific time.
        If path has no state at the time, return None.
        """
        seq = list(path)
        for idx, (x, y, t) in enumerate(seq):
            if t != time_step:
                continue
            curr = (x, y)
            prev = (seq[idx - 1][0], seq[idx - 1][1]) if idx > 0 else curr
            nxt = (seq[idx + 1][0], seq[idx + 1][1]) if idx + 1 < len(seq) else curr
            return prev, curr, nxt
        return None

    @staticmethod
    def _movement_pattern(state: Optional[Tuple[Node, Node, Node]]) -> str:
        """Classify local movement as hold/straight/turn/unknown."""
        if state is None:
            return "unknown"
        prev, curr, nxt = state
        if prev == curr or nxt == curr:
            return "hold"
        dir_in = (curr[0] - prev[0], curr[1] - prev[1])
        dir_out = (nxt[0] - curr[0], nxt[1] - curr[1])
        return "straight" if dir_in == dir_out else "turn"

    @staticmethod
    def _cross_relation(
        a_state: Optional[Tuple[Node, Node, Node]],
        b_state: Optional[Tuple[Node, Node, Node]],
    ) -> bool:
        """True if both agents merge into the same node from orthogonal directions."""
        if a_state is None or b_state is None:
            return False
        a_prev, a_curr, _ = a_state
        b_prev, b_curr, _ = b_state
        if a_curr != b_curr:
            return False
        a_dir = (a_curr[0] - a_prev[0], a_curr[1] - a_prev[1])
        b_dir = (b_curr[0] - b_prev[0], b_curr[1] - b_prev[1])
        return a_dir[0] != b_dir[0] and a_dir[1] != b_dir[1]

    @staticmethod
    def _is_rear_follow(
        curr_state_t: Optional[Tuple[Node, Node, Node]],
        holder_state_t_minus_1: Optional[Tuple[Node, Node, Node]],
        holder_state_t: Optional[Tuple[Node, Node, Node]],
    ) -> bool:
        """
        Strict rear-follow condition:
        - holder occupied node at t-1 and moved forward at t
        - current enters that same node at t
        - both move in the same direction
        """
        if curr_state_t is None or holder_state_t_minus_1 is None or holder_state_t is None:
            return False

        curr_prev, curr_node, _ = curr_state_t
        _, holder_node_t_minus_1, _ = holder_state_t_minus_1
        _, holder_node_t, _ = holder_state_t

        if holder_node_t_minus_1 != curr_node:
            return False
        if holder_node_t == holder_node_t_minus_1:
            return False

        back_dir = (curr_node[0] - curr_prev[0], curr_node[1] - curr_prev[1])
        front_dir = (
            holder_node_t[0] - holder_node_t_minus_1[0],
            holder_node_t[1] - holder_node_t_minus_1[1],
        )
        return back_dir == front_dir

    def detect_node_conflict(
        self,
        agv_id: int,
        segment_path: List[TimedNode],
        reservation_table: Set[TimedNode],
    ) -> Optional[Tuple[int, Node]]:
        """Detect node-time occupation conflict."""
        if not segment_path:
            return None
        for x, y, t in segment_path:
            if (x, y, t) in reservation_table:
                return t, (x, y)
        return None

    def detect_edge_conflict(
        self,
        segment_path: List[TimedNode],
        occupied_edges: Set[Tuple[Node, Node, int]],
    ) -> Optional[Tuple[int, Edge]]:
        """Detect opposite-direction edge occupation at same time."""
        if len(segment_path) < 2:
            return None
        for i in range(len(segment_path) - 1):
            u = (segment_path[i][0], segment_path[i][1])
            v = (segment_path[i + 1][0], segment_path[i + 1][1])
            t = segment_path[i + 1][2]
            if (v, u, t) in occupied_edges:
                return t, (u, v)
        return None

    def detect_rear_conflict(
        self,
        segment_path: List[TimedNode],
        reservation_table: Set[TimedNode],
    ) -> Optional[Tuple[int, Node]]:
        """Detect rear conflict candidate by t-1 reservation overlap."""
        if len(segment_path) < 2:
            return None
        for i in range(1, len(segment_path)):
            x, y, t = segment_path[i]
            if (x, y, t - 1) in reservation_table:
                return t, (x, y)
        return None

    def classify_conflict(
        self,
        conflict_type: str,
        time_step: int,
        agv_current,
        agv_holder,
        segment_path: List[TimedNode],
        node: Optional[Node] = None,
        edge: Optional[Edge] = None,
    ) -> str:
        """
        Mutually exclusive subtype set:
        - edge_head_on
        - rear_follow
        - node_service_block
        - node_cross_merge
        - node_turn_straight_mix
        - node_shared_generic
        """
        if conflict_type == "edge":
            return "edge_head_on"

        if conflict_type == "rear":
            curr_state_t = self._locate_state(segment_path, time_step)
            holder_state_t_minus_1 = self._locate_state(getattr(agv_holder, "path", []), time_step - 1)
            holder_state_t = self._locate_state(getattr(agv_holder, "path", []), time_step)
            if self._is_rear_follow(curr_state_t, holder_state_t_minus_1, holder_state_t):
                return "rear_follow"
            return "node_service_block"

        curr_state = self._locate_state(segment_path, time_step)
        holder_state = self._locate_state(getattr(agv_holder, "path", []), time_step)
        curr_pattern = self._movement_pattern(curr_state)
        holder_pattern = self._movement_pattern(holder_state)

        if holder_pattern == "hold":
            return "node_service_block"
        if self._cross_relation(curr_state, holder_state):
            return "node_cross_merge"
        if (
            (curr_pattern == "turn" and holder_pattern == "straight")
            or (curr_pattern == "straight" and holder_pattern == "turn")
        ):
            return "node_turn_straight_mix"
        return "node_shared_generic"

    def compute_priority(self, agv, current_time: int, remain_dist_est: int) -> float:
        """Compute dynamic priority score."""
        if agv.tasks:
            slack = max(1, agv.tasks[-1].deadline - current_time)
            urgent_score = 1.0 / slack
        else:
            urgent_score = 0.0

        load_score = agv.load / max(1, Config.AGV_CAPACITY)
        remain_score = 1.0 / max(1, remain_dist_est)
        return self.urgent_w * urgent_score + self.load_w * load_score + self.remain_w * remain_score

    def choose_yield_agv(
        self,
        agv_a,
        agv_b,
        time_step: int,
        remain_dist_a: int,
        remain_dist_b: int,
    ) -> Tuple[int, int]:
        """Return (high_priority_id, low_priority_id)."""
        pa = self.compute_priority(agv_a, time_step, remain_dist_a)
        pb = self.compute_priority(agv_b, time_step, remain_dist_b)
        if pa >= pb:
            return agv_a.id, agv_b.id
        return agv_b.id, agv_a.id

    def add_wait_dependency(self, waiter_id: int, holder_id: int):
        """Record wait edge waiter -> holder."""
        if waiter_id == holder_id:
            return
        self.wait_graph.setdefault(waiter_id, set()).add(holder_id)

    def clear_wait_dependency(self, waiter_id: int):
        """Clear outgoing wait dependencies for an AGV."""
        self.wait_graph.pop(waiter_id, None)

    def _find_cycle_dfs(
        self,
        node: int,
        visited: Set[int],
        stack: List[int],
        in_stack: Set[int],
    ) -> Optional[List[int]]:
        """DFS cycle detection in wait graph."""
        visited.add(node)
        stack.append(node)
        in_stack.add(node)

        for nxt in self.wait_graph.get(node, set()):
            if nxt not in visited:
                cycle = self._find_cycle_dfs(nxt, visited, stack, in_stack)
                if cycle:
                    return cycle
            elif nxt in in_stack:
                start_idx = stack.index(nxt)
                return stack[start_idx:].copy()

        stack.pop()
        in_stack.remove(node)
        return None

    def detect_deadlock_cycle(self) -> Optional[List[int]]:
        """Detect true deadlock cycle in wait graph."""
        visited: Set[int] = set()
        in_stack: Set[int] = set()
        for node in list(self.wait_graph.keys()):
            if node not in visited:
                cycle = self._find_cycle_dfs(node, visited, [], in_stack)
                if cycle:
                    return cycle
        return None

    def estimate_deadlock_risk(
        self,
        wait_count: int,
        repeat_conflict_count: int,
        repeated_resource_count: int,
        has_cycle: bool = False,
    ) -> float:
        """Estimate quasi-deadlock risk score."""
        base = (0.7 * wait_count) + (0.9 * repeat_conflict_count) + (0.6 * repeated_resource_count)
        if has_cycle:
            base += 3.0
        return base

    def pick_victim_for_deadlock(self, cycle_agv_ids: List[int], agv_map: Dict[int, object]) -> int:
        """Pick lowest-priority victim in deadlock cycle."""
        victim = cycle_agv_ids[0]
        victim_score = float("inf")
        for aid in cycle_agv_ids:
            agv = agv_map.get(aid)
            if agv is None:
                continue
            remain_est = 10
            if agv.tasks:
                last_task = agv.tasks[-1]
                remain_est = manhattan_dist(agv.start_pos, (last_task.x, last_task.y))
            score = self.compute_priority(agv, getattr(agv, "finish_time", 0), remain_est)
            if score < victim_score:
                victim_score = score
                victim = aid
        return victim

    def resolve_conflict(
        self,
        conflict_type: str,
        conflict_subtype: str,
        agv_a,
        agv_b,
        time_step: int,
        remain_dist_a: int,
        remain_dist_b: int,
        low_wait_count: int = 0,
        repeat_conflict_count: int = 0,
        repeated_resource_count: int = 0,
        has_cycle: bool = False,
        node: Optional[Node] = None,
        edge: Optional[Edge] = None,
    ) -> ConflictEvent:
        """Return wait/reroute/replan action based on subtype and risk."""
        high, low = self.choose_yield_agv(
            agv_a=agv_a,
            agv_b=agv_b,
            time_step=time_step,
            remain_dist_a=remain_dist_a,
            remain_dist_b=remain_dist_b,
        )

        risk_score = self.estimate_deadlock_risk(
            wait_count=low_wait_count,
            repeat_conflict_count=repeat_conflict_count,
            repeated_resource_count=repeated_resource_count,
            has_cycle=has_cycle,
        )

        action = "wait"
        if has_cycle or risk_score >= self.deadlock_risk_threshold or low_wait_count >= self.wait_threshold:
            action = "replan"
        elif conflict_subtype in {"edge_head_on", "node_service_block", "node_cross_merge"}:
            action = "reroute" if risk_score >= self.reroute_risk_threshold else "wait"
        elif conflict_subtype in {"node_turn_straight_mix", "node_shared_generic"}:
            action = "reroute" if repeated_resource_count >= 2 else "wait"
        elif conflict_subtype == "rear_follow":
            action = "reroute" if repeat_conflict_count >= 2 else "wait"

        detail = (
            f"action={action};subtype={conflict_subtype};"
            f"risk={risk_score:.2f};waits={low_wait_count};"
            f"repeat={repeat_conflict_count};resource_repeat={repeated_resource_count}"
        )
        return ConflictEvent(
            conflict_type=conflict_type,
            conflict_subtype=conflict_subtype,
            time_step=time_step,
            agv_high=high,
            agv_low=low,
            action=action,
            risk_score=risk_score,
            node=node,
            edge=edge,
            detail=detail,
        )
