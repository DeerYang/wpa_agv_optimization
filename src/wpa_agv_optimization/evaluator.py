"""
狼个体评估器。

作用：
1. 将任务分配方案重建为可执行的时空路径。
2. 在重建阶段接入冲突分型、准死锁风险评估和解除动作。
3. 汇总 F/N/D/T 和冲突统计，作为 WPA 的真实评价函数。
"""

import hashlib
from typing import Dict, List, Optional, Set, Tuple

from .config import Config
from .pathfinding import TentDFSPlanner
from .traffic_manager import TrafficManager
from .utils import manhattan_dist, tent_map_iter


Node = Tuple[int, int]
TimedNode = Tuple[int, int, int]
TimedEdge = Tuple[Node, Node, int]


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
    def _task_signature(agv) -> Tuple[int, ...]:
        """Build a stable signature for one AGV task sequence."""
        return tuple(task.id for task in agv.tasks)

    @staticmethod
    def _derive_chaos_x0(wolf) -> float:
        """
        从 wolf 的任务分配结构派生确定性 Tent 混沌起点。

        同一结构的 wolf 永远得到同一个 x0，消除评估顺序对 tie-break 路径的影响。
        SHA1 保证跨进程/跨机器稳定（Python 内置 hash 不稳定），落在 (0.1, 0.9) 区间
        避开 Tent 映射的 0/0.5/1 退化点附近。
        """
        parts = []
        for agv in wolf.agv_list:
            parts.append(f"{agv.start_pos[0]},{agv.start_pos[1]}:")
            parts.append(",".join(str(task.id) for task in agv.tasks))
            parts.append(";")
        digest = hashlib.sha1("".join(parts).encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big")
        return 0.1 + (value / float(1 << 64)) * 0.8

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

    @staticmethod
    def _reserve_wait_window(
        agv_id: int,
        pos: Node,
        start_time: int,
        end_time: int,
        reservation_table: Set[TimedNode],
        reservation_owner: Dict[TimedNode, int],
        agv_reserved_nodes: Optional[Set[TimedNode]] = None,
    ) -> Tuple[int, Optional[Dict[str, object]]]:
        """
        把冲突重试阶段产生的原地等待写入时空占用表。

        如果等待区间中途撞上了别的车辆已经占用的时空节点，
        就在冲突发生前停下并把冲突详情返回给调用方，
        防止等待窗口把已有占位静默覆盖掉。
        """
        if end_time <= start_time:
            return start_time, None

        x, y = pos
        actual_end_time = start_time
        for wait_time in range(start_time + 1, end_time + 1):
            wait_node = (x, y, wait_time)
            holder_id = reservation_owner.get(wait_node)
            if holder_id is not None and holder_id != agv_id:
                return actual_end_time, {
                    "kind": "node",
                    "time": wait_time,
                    "holder_id": holder_id,
                    "node": (x, y),
                    "edge": None,
                }

            reservation_table.add(wait_node)
            reservation_owner[wait_node] = agv_id
            if agv_reserved_nodes is not None:
                agv_reserved_nodes.add(wait_node)
            actual_end_time = wait_time

        return actual_end_time, None

    @staticmethod
    def _copy_cached_agv_state(target_agv, base_agv) -> None:
        """Copy reusable cached planner state from one AGV to another."""
        target_agv.load = base_agv.load
        target_agv.path = list(base_agv.path)
        target_agv.finish_time = base_agv.finish_time
        target_agv._task_signature = tuple(getattr(base_agv, "_task_signature", ()))
        target_agv._reserved_nodes = set(getattr(base_agv, "_reserved_nodes", set()))
        target_agv._reserved_edges = set(getattr(base_agv, "_reserved_edges", set()))
        target_agv._cached_metrics = dict(getattr(base_agv, "_cached_metrics", {}))

    def _first_changed_agv_index(self, base_wolf, candidate_agvs) -> int:
        """Find the first AGV index whose task signature differs from the base wolf."""
        if base_wolf is None or not getattr(base_wolf, "_cache_ready", False):
            return 0

        shared = min(len(base_wolf.agv_list), len(candidate_agvs))
        for idx in range(shared):
            base_agv = base_wolf.agv_list[idx]
            candidate_agv = candidate_agvs[idx]
            if base_agv.start_pos != candidate_agv.start_pos:
                return idx
            if getattr(base_agv, "_task_signature", None) != self._task_signature(candidate_agv):
                return idx

        return shared if len(base_wolf.agv_list) == len(candidate_agvs) else shared

    def _build_initial_state(self, wolf, base_wolf=None):
        """Seed one rebuild state, optionally reusing an unchanged AGV prefix."""
        state = {
            "reservation_table": set(),
            "reservation_owner": {},
            "occupied_edges": set(),
            "edge_owner": {},
            "wait_counts": {},
            "agv_map": {agv.id: agv for agv in wolf.agv_list},
            "total_dist": 0,
            "total_time_penalty": 0,
            "conflict_count": 0,
            "deadlock_count": 0,
            "deadlock_risk_count": 0,
            "replan_count": 0,
            "reroute_count": 0,
            "total_unfinished": 0,
            "pair_repeat_counts": {},
            "resource_repeat_counts": {},
            "start_idx": 0,
        }

        if base_wolf is None or not getattr(base_wolf, "_cache_ready", False):
            return state

        start_idx = self._first_changed_agv_index(base_wolf, wolf.agv_list)
        state["start_idx"] = start_idx

        for idx in range(start_idx):
            target_agv = wolf.agv_list[idx]
            base_agv = base_wolf.agv_list[idx]
            self._copy_cached_agv_state(target_agv, base_agv)

            for node in target_agv._reserved_nodes:
                state["reservation_table"].add(node)
                state["reservation_owner"][node] = target_agv.id

            for edge in target_agv._reserved_edges:
                state["occupied_edges"].add(edge)
                state["edge_owner"][edge] = target_agv.id

            cached_metrics = target_agv._cached_metrics
            state["total_dist"] += int(cached_metrics.get("dist", 0))
            state["total_time_penalty"] += float(cached_metrics.get("time_penalty", 0))
            state["conflict_count"] += int(cached_metrics.get("conflict_count", 0))
            state["deadlock_count"] += int(cached_metrics.get("deadlock_count", 0))
            state["deadlock_risk_count"] += int(cached_metrics.get("deadlock_risk_count", 0))
            state["replan_count"] += int(cached_metrics.get("replan_count", 0))
            state["reroute_count"] += int(cached_metrics.get("reroute_count", 0))
            state["total_unfinished"] += int(cached_metrics.get("unfinished_count", 0))

        return state

    def _detect_conflict_event(
        self,
        agv,
        segment_path: List[TimedNode],
        reservation_table: Set[TimedNode],
        reservation_owner: Dict[TimedNode, int],
        occupied_edges: Set[TimedEdge],
        edge_owner: Dict[TimedEdge, int],
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

    def _detect_service_window_conflict(
        self,
        agv,
        last_node: TimedNode,
        reservation_table: Set[TimedNode],
        reservation_owner: Dict[TimedNode, int],
        agv_map: Dict[int, object],
    ) -> Optional[Dict[str, object]]:
        """
        检查到达目标点后的服务占点是否与已有时空占用冲突。

        之前这里是直接把 SERVICE_TIME 对应的等待节点写入 reservation_table，
        如果别的车辆更早被重建并已经占用了这些时刻，就会把真实冲突静默覆盖掉。
        """
        x, y, arrive_time = last_node
        for extra_wait in range(1, Config.SERVICE_TIME + 1):
            time_step = arrive_time + extra_wait
            wait_node = (x, y, time_step)
            if wait_node in reservation_table:
                holder_id = reservation_owner.get(wait_node)
                if holder_id is not None and holder_id in agv_map and holder_id != agv.id:
                    return {
                        "kind": "node",
                        "time": time_step,
                        "holder_id": holder_id,
                        "node": (x, y),
                        "edge": None,
                    }
        return None

    def rebuild_wolf(self, wolf, base_wolf=None):
        """重建并评估狼个体。"""
        state = self._build_initial_state(wolf, base_wolf=base_wolf)
        reservation_table: Set[TimedNode] = state["reservation_table"]
        reservation_owner: Dict[TimedNode, int] = state["reservation_owner"]
        occupied_edges: Set[TimedEdge] = state["occupied_edges"]
        edge_owner: Dict[TimedEdge, int] = state["edge_owner"]
        wait_counts: Dict[int, int] = state["wait_counts"]
        agv_map: Dict[int, object] = state["agv_map"]
        total_dist = state["total_dist"]
        total_time_penalty = state["total_time_penalty"]
        conflict_count = state["conflict_count"]
        deadlock_count = state["deadlock_count"]
        deadlock_risk_count = state["deadlock_risk_count"]
        replan_count = state["replan_count"]
        reroute_count = state["reroute_count"]
        total_unfinished = state["total_unfinished"]
        pair_repeat_counts = state["pair_repeat_counts"]
        resource_repeat_counts = state["resource_repeat_counts"]
        start_idx = state["start_idx"]

        x0 = self._derive_chaos_x0(wolf)
        chaos_iter = tent_map_iter(x0=x0)

        for agv in wolf.agv_list[start_idx:]:
            wait_counts.setdefault(agv.id, 0)
            curr_pos = agv.start_pos
            curr_time = 0
            full_path: List[TimedNode] = []
            agv_reserved_nodes: Set[TimedNode] = set()
            agv_reserved_edges: Set[TimedEdge] = set()

            agv_conflict_count = 0
            agv_deadlock_count = 0
            agv_deadlock_risk_count = 0
            agv_replan_count = 0
            agv_reroute_count = 0
            agv_time_penalty = 0
            agv_unfinished_count = 0
            agv_aborted = False

            targets = list(agv.tasks)
            if agv.tasks:
                targets.append(None)

            for target_idx, target in enumerate(targets):
                target_pos = Config.DEPOT_NODE if target is None else (target.x, target.y)
                max_retries = 8
                retries = 0
                segment_path: Optional[List[TimedNode]] = None
                temporary_blocks: Set[TimedNode] = set()

                while retries <= max_retries:
                    plan_start_time = curr_time
                    segment_path = self.planner.plan(
                        curr_pos,
                        target_pos,
                        curr_time,
                        reservation_table,
                        chaos_iter,
                        extra_blocks=temporary_blocks,
                    )

                    if segment_path is None:
                        agv_replan_count += 1
                        wait_counts[agv.id] += 1
                        curr_time += 1
                        curr_time, wait_conflict = self._reserve_wait_window(
                            agv_id=agv.id,
                            pos=curr_pos,
                            start_time=plan_start_time,
                            end_time=curr_time,
                            reservation_table=reservation_table,
                            reservation_owner=reservation_owner,
                            agv_reserved_nodes=agv_reserved_nodes,
                        )
                        if wait_conflict is not None:
                            temporary_blocks |= self._temporary_blocks_for_conflict(wait_conflict)
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
                        service_conflict = self._detect_service_window_conflict(
                            agv=agv,
                            last_node=segment_path[-1],
                            reservation_table=reservation_table,
                            reservation_owner=reservation_owner,
                            agv_map=agv_map,
                        )
                        if service_conflict is None:
                            break
                        conflict = service_conflict

                    holder_id = int(conflict["holder_id"])
                    holder_agv = agv_map[holder_id]
                    agv_conflict_count += 1

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
                        agv_deadlock_count += 1
                        victim = self.traffic_manager.pick_victim_for_deadlock(cycle, agv_map)
                        self.traffic_manager.clear_wait_dependency(victim)
                        if victim == agv.id:
                            action = "replan"
                    elif event.risk_score >= self.traffic_manager.deadlock_risk_threshold:
                        agv_deadlock_risk_count += 1

                    if action == "reroute":
                        agv_reroute_count += 1
                        temporary_blocks |= self._temporary_blocks_for_conflict(conflict)
                        curr_time += 1
                    elif action == "replan":
                        agv_replan_count += 1
                        temporary_blocks |= self._temporary_blocks_for_conflict(conflict)
                        curr_time += 2
                    else:
                        curr_time += 1

                    curr_time, wait_conflict = self._reserve_wait_window(
                        agv_id=agv.id,
                        pos=curr_pos,
                        start_time=plan_start_time,
                        end_time=curr_time,
                        reservation_table=reservation_table,
                        reservation_owner=reservation_owner,
                        agv_reserved_nodes=agv_reserved_nodes,
                    )
                    if wait_conflict is not None:
                        temporary_blocks |= self._temporary_blocks_for_conflict(wait_conflict)

                    retries += 1

                if segment_path is None:
                    # 规划彻底失败：AGV 停机，避免瞬移污染时空占用表
                    if target is not None:
                        # 当前失败的客户任务及其后所有客户任务都算未完成（depot 不算）
                        remaining = targets[target_idx:]
                        agv_unfinished_count = sum(1 for item in remaining if item is not None)
                    agv_aborted = True
                    break

                if full_path:
                    full_path.extend(segment_path[1:])
                else:
                    full_path.extend(segment_path)

                last_node = segment_path[-1]
                curr_pos = (last_node[0], last_node[1])
                curr_time = last_node[2] + Config.SERVICE_TIME
                if target is not None:
                    agv_time_penalty += max(0, curr_time - target.deadline)

                for point in segment_path:
                    reservation_table.add(point)
                    reservation_owner[point] = agv.id
                    agv_reserved_nodes.add(point)

                for idx in range(len(segment_path) - 1):
                    u = (segment_path[idx][0], segment_path[idx][1])
                    v = (segment_path[idx + 1][0], segment_path[idx + 1][1])
                    time_step = segment_path[idx + 1][2]
                    edge_key = (u, v, time_step)
                    occupied_edges.add(edge_key)
                    edge_owner[edge_key] = agv.id
                    agv_reserved_edges.add(edge_key)

                for extra_wait in range(1, Config.SERVICE_TIME + 1):
                    wait_node = (last_node[0], last_node[1], last_node[2] + extra_wait)
                    reservation_table.add(wait_node)
                    reservation_owner[wait_node] = agv.id
                    agv_reserved_nodes.add(wait_node)

                self.traffic_manager.clear_wait_dependency(agv.id)
                wait_counts[agv.id] = 0

            if agv_aborted:
                # 停机后同样要清理 wait graph，避免残留依赖影响后续 AGV 的死锁检测
                self.traffic_manager.clear_wait_dependency(agv.id)
                wait_counts[agv.id] = 0

            agv.path = full_path
            agv.finish_time = curr_time
            agv._task_signature = self._task_signature(agv)
            agv._reserved_nodes = agv_reserved_nodes
            agv._reserved_edges = agv_reserved_edges
            agv._cached_metrics = {
                "dist": len(full_path),
                "time_penalty": agv_time_penalty,
                "conflict_count": agv_conflict_count,
                "deadlock_count": agv_deadlock_count,
                "deadlock_risk_count": agv_deadlock_risk_count,
                "replan_count": agv_replan_count,
                "reroute_count": agv_reroute_count,
                "unfinished_count": agv_unfinished_count,
            }

            total_dist += len(full_path)
            total_time_penalty += agv_time_penalty
            conflict_count += agv_conflict_count
            deadlock_count += agv_deadlock_count
            deadlock_risk_count += agv_deadlock_risk_count
            replan_count += agv_replan_count
            reroute_count += agv_reroute_count
            total_unfinished += agv_unfinished_count

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
            + (Config.W7_UNFINISHED * total_unfinished)
        )

        wolf.conflict_count = conflict_count
        wolf.deadlock_count = deadlock_count
        wolf.deadlock_risk_count = deadlock_risk_count
        wolf.replan_count = replan_count
        wolf.reroute_count = reroute_count
        wolf.unfinished_count = total_unfinished
        wolf._cache_ready = True
        return wolf

