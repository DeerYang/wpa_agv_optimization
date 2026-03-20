"""
狼个体评估器。

作用：
1. 将任务分配方案重建为可执行的时空路径。
2. 在重建阶段接入冲突分型、准死锁风险评估和解除动作。
3. 汇总 F/N/D/T 和冲突统计，作为 WPA 的真实评价函数。
"""

import random
from typing import Dict, List, Optional, Set, Tuple

from .config import Config
from .pathfinding import TentDFSPlanner
from .traffic_manager import TrafficManager
from .utils import manhattan_dist, tent_map_iter


Node = Tuple[int, int]
TimedNode = Tuple[int, int, int]


class WolfEvaluator:
    """统一评估入口。"""

    def __init__(self, grid_map):
        self.grid_map = grid_map
        self.planner = TentDFSPlanner(grid_map)
        self.traffic_manager = TrafficManager()

    @staticmethod
    def _agv_remain_dist_est(agv) -> int:
        """粗略估计车辆剩余路程，用于优先级比较。"""
        if not agv.tasks:
            return 1
        last_task = agv.tasks[-1]
        return max(1, manhattan_dist(agv.start_pos, (last_task.x, last_task.y)))

    @staticmethod
    def _resource_key(conflict: Dict[str, object]) -> str:
        """把冲突位置转成可计数的资源签名。"""
        if conflict["kind"] == "edge":
            return f"edge:{conflict['edge']}@{conflict['time']}"
        return f"node:{conflict['node']}@{conflict['time']}"

    @staticmethod
    def _temporary_blocks_for_conflict(conflict: Dict[str, object]) -> Set[TimedNode]:
        """
        为局部改道动作生成临时时空禁忌。

        目的不是永久封锁，而是避免同一轮重试又撞回同一个瓶颈位置。
        """
        blocks: Set[TimedNode] = set()
        time_step = int(conflict["time"])

        if conflict["kind"] == "edge":
            u, v = conflict["edge"]
            for extra_t in range(time_step, time_step + 3):
                blocks.add((u[0], u[1], extra_t))
                blocks.add((v[0], v[1], extra_t))
        else:
            x, y = conflict["node"]
            for extra_t in range(time_step, time_step + 3):
                blocks.add((x, y, extra_t))
        return blocks

    def _detect_conflict_event(
        self,
        agv,
        segment_path: List[TimedNode],
        reservation_table: Set[TimedNode],
        reservation_owner: Dict[TimedNode, int],
        occupied_edges: Set[Tuple[Node, Node, int]],
        edge_owner: Dict[Tuple[Node, Node, int], int],
        agv_map: Dict[int, object],
    ) -> Optional[Dict[str, object]]:
        """对候选段路径做冲突检测，并返回冲突详情。"""
        node_hit = self.traffic_manager.detect_node_conflict(agv.id, segment_path, reservation_table)
        if node_hit is not None:
            time_step, node = node_hit
            holder_id = reservation_owner.get((node[0], node[1], time_step))
            if holder_id is not None and holder_id in agv_map:
                return {
                    "kind": "node",
                    "time": time_step,
                    "holder_id": holder_id,
                    "node": node,
                    "edge": None,
                }

        edge_hit = self.traffic_manager.detect_edge_conflict(segment_path, occupied_edges)
        if edge_hit is not None:
            time_step, edge = edge_hit
            holder_id = edge_owner.get((edge[1], edge[0], time_step))
            if holder_id is not None and holder_id in agv_map:
                return {
                    "kind": "edge",
                    "time": time_step,
                    "holder_id": holder_id,
                    "node": None,
                    "edge": edge,
                }

        rear_hit = self.traffic_manager.detect_rear_conflict(segment_path, reservation_table)
        if rear_hit is not None:
            time_step, node = rear_hit
            holder_id = reservation_owner.get((node[0], node[1], time_step - 1))
            if holder_id is not None and holder_id in agv_map:
                return {
                    "kind": "rear",
                    "time": time_step,
                    "holder_id": holder_id,
                    "node": node,
                    "edge": None,
                }

        return None

    def rebuild_wolf(self, wolf):
        """重建并评估狼个体。"""
        reservation_table: Set[TimedNode] = set()
        reservation_owner: Dict[TimedNode, int] = {}
        occupied_edges: Set[Tuple[Node, Node, int]] = set()
        edge_owner: Dict[Tuple[Node, Node, int], int] = {}
        wait_counts: Dict[int, int] = {}
        agv_map: Dict[int, object] = {agv.id: agv for agv in wolf.agv_list}

        total_dist = 0
        total_time_penalty = 0

        conflict_count = 0
        deadlock_count = 0
        deadlock_risk_count = 0
        replan_count = 0
        reroute_count = 0

        pair_repeat_counts: Dict[Tuple[int, int, str], int] = {}
        resource_repeat_counts: Dict[str, int] = {}

        x0 = random.random()
        chaos_iter = tent_map_iter(x0=x0)

        for agv in wolf.agv_list:
            wait_counts.setdefault(agv.id, 0)
            curr_pos = agv.start_pos
            curr_time = 0
            full_path: List[TimedNode] = []

            targets = list(agv.tasks)
            if agv.tasks:
                targets.append(None)

            for target in targets:
                target_pos = Config.DEPOT_NODE if target is None else (target.x, target.y)
                max_retries = 8
                retries = 0
                segment_path: Optional[List[TimedNode]] = None
                temporary_blocks: Set[TimedNode] = set()

                while retries <= max_retries:
                    segment_path = self.planner.plan(
                        curr_pos,
                        target_pos,
                        curr_time,
                        reservation_table,
                        chaos_iter,
                        extra_blocks=temporary_blocks,
                    )

                    if segment_path is None:
                        replan_count += 1
                        wait_counts[agv.id] += 1
                        curr_time += 1
                        retries += 1
                        continue

                    conflict = self._detect_conflict_event(
                        agv=agv,
                        segment_path=segment_path,
                        reservation_table=reservation_table,
                        reservation_owner=reservation_owner,
                        occupied_edges=occupied_edges,
                        edge_owner=edge_owner,
                        agv_map=agv_map,
                    )
                    if conflict is None:
                        break

                    holder_id = int(conflict["holder_id"])
                    holder_agv = agv_map[holder_id]
                    conflict_count += 1

                    pair_key = (agv.id, holder_id, str(conflict["kind"]))
                    pair_repeat_counts[pair_key] = pair_repeat_counts.get(pair_key, 0) + 1

                    resource_key = self._resource_key(conflict)
                    resource_repeat_counts[resource_key] = resource_repeat_counts.get(resource_key, 0) + 1

                    self.traffic_manager.add_wait_dependency(agv.id, holder_id)
                    wait_counts[agv.id] = wait_counts.get(agv.id, 0) + 1

                    cycle = self.traffic_manager.detect_deadlock_cycle()
                    conflict_subtype = self.traffic_manager.classify_conflict(
                        conflict_type=str(conflict["kind"]),
                        time_step=int(conflict["time"]),
                        agv_current=agv,
                        agv_holder=holder_agv,
                        segment_path=segment_path,
                        node=conflict.get("node"),
                        edge=conflict.get("edge"),
                    )
                    event = self.traffic_manager.resolve_conflict(
                        conflict_type=str(conflict["kind"]),
                        conflict_subtype=conflict_subtype,
                        agv_a=agv,
                        agv_b=holder_agv,
                        time_step=int(conflict["time"]),
                        remain_dist_a=max(1, manhattan_dist(curr_pos, target_pos)),
                        remain_dist_b=self._agv_remain_dist_est(holder_agv),
                        low_wait_count=wait_counts.get(agv.id, 0),
                        repeat_conflict_count=pair_repeat_counts[pair_key],
                        repeated_resource_count=resource_repeat_counts[resource_key],
                        has_cycle=cycle is not None,
                        node=conflict.get("node"),
                        edge=conflict.get("edge"),
                    )

                    action = event.action
                    if cycle:
                        deadlock_count += 1
                        victim = self.traffic_manager.pick_victim_for_deadlock(cycle, agv_map)
                        self.traffic_manager.clear_wait_dependency(victim)
                        if victim == agv.id:
                            action = "replan"
                    elif event.risk_score >= self.traffic_manager.deadlock_risk_threshold:
                        deadlock_risk_count += 1

                    if action == "reroute":
                        reroute_count += 1
                        temporary_blocks |= self._temporary_blocks_for_conflict(conflict)
                        curr_time += 1
                    elif action == "replan":
                        replan_count += 1
                        temporary_blocks |= self._temporary_blocks_for_conflict(conflict)
                        curr_time += 2
                    else:
                        curr_time += 1

                    retries += 1

                if segment_path is None:
                    total_time_penalty += 10000
                    segment_path = [(target_pos[0], target_pos[1], curr_time + 10)]

                if full_path:
                    full_path.extend(segment_path[1:])
                else:
                    full_path.extend(segment_path)

                last_node = segment_path[-1]
                curr_pos = (last_node[0], last_node[1])
                curr_time = last_node[2] + Config.SERVICE_TIME
                if target is not None:
                    total_time_penalty += max(0, curr_time - target.deadline)

                for point in segment_path:
                    reservation_table.add(point)
                    reservation_owner[point] = agv.id

                for idx in range(len(segment_path) - 1):
                    u = (segment_path[idx][0], segment_path[idx][1])
                    v = (segment_path[idx + 1][0], segment_path[idx + 1][1])
                    time_step = segment_path[idx + 1][2]
                    edge_key = (u, v, time_step)
                    occupied_edges.add(edge_key)
                    edge_owner[edge_key] = agv.id

                for extra_wait in range(1, Config.SERVICE_TIME + 1):
                    wait_node = (last_node[0], last_node[1], last_node[2] + extra_wait)
                    reservation_table.add(wait_node)
                    reservation_owner[wait_node] = agv.id

                self.traffic_manager.clear_wait_dependency(agv.id)
                wait_counts[agv.id] = 0

            agv.path = full_path
            agv.finish_time = curr_time
            total_dist += len(full_path)

        wolf.total_dist = total_dist
        wolf.time_penalty = total_time_penalty
        wolf.vehicle_num = len([agv for agv in wolf.agv_list if agv.tasks])
        wolf.fitness = (
            (Config.W1_DIST * total_dist)
            + (Config.W2_NUM * wolf.vehicle_num)
            + (Config.W3_TIME * total_time_penalty)
            + (Config.W4_CONFLICT * conflict_count)
            + (Config.W5_REPLAN * replan_count)
            + (Config.W6_RISK * deadlock_risk_count)
        )

        wolf.conflict_count = conflict_count
        wolf.deadlock_count = deadlock_count
        wolf.deadlock_risk_count = deadlock_risk_count
        wolf.replan_count = replan_count
        wolf.reroute_count = reroute_count
        return wolf
