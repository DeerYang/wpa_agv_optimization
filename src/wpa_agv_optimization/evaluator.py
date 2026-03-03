import random
from typing import Dict, List, Optional, Set, Tuple

from .config import Config
from .pathfinding import TentDFSPlanner
from .traffic_manager import TrafficManager
from .utils import manhattan_dist, tent_map_generate


Node = Tuple[int, int]
TimedNode = Tuple[int, int, int]


class WolfEvaluator:
    """
    狼个体评估器:
    1) 根据任务分配重建每台 AGV 的时空路径
    2) 处理冲突与死锁
    3) 计算 F/N/D/T
    """

    def __init__(self, grid_map):
        self.planner = TentDFSPlanner(grid_map)
        self.traffic_manager = TrafficManager()

    @staticmethod
    def _agv_remain_dist_est(agv) -> int:
        if not agv.tasks:
            return 1
        last_task = agv.tasks[-1]
        return max(1, manhattan_dist(agv.start_pos, (last_task.x, last_task.y)))

    @staticmethod
    def _event_action(detail: str) -> str:
        # detail 形如: "low_agv_action=wait" / "low_agv_action=replan"
        if "replan" in detail:
            return "replan"
        return "wait"

    def _detect_conflict_event(
        self,
        agv,
        segment_path: List[TimedNode],
        reservation_table: Set[TimedNode],
        reservation_owner: Dict[TimedNode, int],
        occupied_edges: Set[Tuple[Node, Node, int]],
        edge_owner: Dict[Tuple[Node, Node, int], int],
        agv_map: Dict[int, object],
    ):
        # 节点冲突
        node_hit = self.traffic_manager.detect_node_conflict(agv.id, segment_path, reservation_table)
        if node_hit is not None:
            t, node = node_hit
            holder_id = reservation_owner.get((node[0], node[1], t))
            if holder_id is not None and holder_id in agv_map:
                return "node", t, holder_id

        # 相向边冲突
        edge_hit = self.traffic_manager.detect_edge_conflict(segment_path, occupied_edges)
        if edge_hit is not None:
            t, edge = edge_hit
            holder_id = edge_owner.get((edge[1], edge[0], t))
            if holder_id is not None and holder_id in agv_map:
                return "edge", t, holder_id

        # 追尾风险
        rear_hit = self.traffic_manager.detect_rear_conflict(segment_path, reservation_table)
        if rear_hit is not None:
            t, node = rear_hit
            holder_id = reservation_owner.get((node[0], node[1], t - 1))
            if holder_id is not None and holder_id in agv_map:
                return "rear", t, holder_id

        return None

    def rebuild_wolf(self, wolf):
        # 资源/状态
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
        replan_count = 0

        x0 = random.random()
        chaos_seq = tent_map_generate(n=5000, x0=x0)
        chaos_iter = iter(chaos_seq)

        for agv in wolf.agv_list:
            wait_counts.setdefault(agv.id, 0)
            curr_pos = agv.start_pos
            curr_time = 0
            full_path: List[TimedNode] = []

            targets = [(t.x, t.y) for t in agv.tasks]
            if agv.tasks:
                targets.append(Config.DEPOT_NODE)

            for target_pos in targets:
                # 单段路径最多尝试多次（等待/重规划）
                max_retries = 8
                retries = 0
                segment_path: Optional[List[TimedNode]] = None

                while retries <= max_retries:
                    segment_path = self.planner.plan(
                        curr_pos, target_pos, curr_time, reservation_table, chaos_iter
                    )

                    if segment_path is None:
                        # 当前时刻不可达：先等待再重试
                        retries += 1
                        replan_count += 1
                        wait_counts[agv.id] += 1
                        curr_time += 1
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

                    conflict_type, time_step, holder_id = conflict
                    holder_agv = agv_map[holder_id]
                    conflict_count += 1

                    event = self.traffic_manager.resolve_conflict(
                        conflict_type=conflict_type,
                        agv_a=agv,
                        agv_b=holder_agv,
                        time_step=time_step,
                        remain_dist_a=max(1, manhattan_dist(curr_pos, target_pos)),
                        remain_dist_b=self._agv_remain_dist_est(holder_agv),
                        low_wait_count=wait_counts.get(agv.id, 0),
                    )
                    action = self._event_action(event.detail)

                    # 规划顺序已固定，历史路径不可回写修改，因此当前 AGV 让行/重规划
                    self.traffic_manager.add_wait_dependency(waiter_id=agv.id, holder_id=holder_id)
                    wait_counts[agv.id] = wait_counts.get(agv.id, 0) + 1

                    cycle = self.traffic_manager.detect_deadlock_cycle()
                    if cycle:
                        deadlock_count += 1
                        victim = self.traffic_manager.pick_victim_for_deadlock(cycle, agv_map)
                        self.traffic_manager.clear_wait_dependency(victim)
                        if victim == agv.id:
                            action = "replan"

                    if action == "replan":
                        replan_count += 1
                        curr_time += 2
                    else:
                        curr_time += 1

                    retries += 1

                # 极端兜底
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

                # 登记节点占用
                for p in segment_path:
                    reservation_table.add(p)
                    reservation_owner[p] = agv.id

                # 登记边占用（用于相向冲突检测）
                for i in range(len(segment_path) - 1):
                    u = (segment_path[i][0], segment_path[i][1])
                    v = (segment_path[i + 1][0], segment_path[i + 1][1])
                    t = segment_path[i + 1][2]
                    edge_key = (u, v, t)
                    occupied_edges.add(edge_key)
                    edge_owner[edge_key] = agv.id

                # 装卸服务时间占用（占用当前末节点）
                for t_wait in range(1, Config.SERVICE_TIME + 1):
                    wait_node = (last_node[0], last_node[1], last_node[2] + t_wait)
                    reservation_table.add(wait_node)
                    reservation_owner[wait_node] = agv.id

                # 当前段成功推进，清理等待依赖
                self.traffic_manager.clear_wait_dependency(agv.id)
                wait_counts[agv.id] = 0

            agv.path = full_path
            agv.finish_time = curr_time
            total_dist += len(full_path)

            if agv.tasks:
                last_deadline = agv.tasks[-1].deadline
                if curr_time > last_deadline:
                    total_time_penalty += (curr_time - last_deadline)

        wolf.total_dist = total_dist
        wolf.time_penalty = total_time_penalty
        wolf.vehicle_num = len([agv for agv in wolf.agv_list if agv.tasks])
        wolf.fitness = (
            (Config.W1_DIST * total_dist)
            + (Config.W2_NUM * wolf.vehicle_num)
            + (Config.W3_TIME * total_time_penalty)
        )

        wolf.conflict_count = conflict_count
        wolf.deadlock_count = deadlock_count
        wolf.replan_count = replan_count
        return wolf

