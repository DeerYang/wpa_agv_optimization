# ===================== 文件级说明 =====================
# 文件名: traffic_manager.py
# 功能: 多AGV冲突与死锁管理模块（集中式协调）
# 核心能力:
#   1) 冲突检测：节点冲突、相向冲突、追击冲突
#   2) 动态优先级：根据任务紧迫度/负载/剩余路程评分
#   3) 死锁检测：等待依赖图环检测
#   4) 解锁建议：选择低优先级AGV执行回退/让行
# 设计定位: 当前版本提供“可接入评估器”的策略内核，不与具体路径搜索强耦合
# ======================================================

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .config import Config
from .utils import manhattan_dist


Node = Tuple[int, int]
Edge = Tuple[Node, Node]


@dataclass
class ConflictEvent:
    """
    冲突事件模型
    conflict_type:
      - node: 同时刻同节点占用冲突
      - edge: 相向边交换冲突（u->v 与 v->u）
      - rear: 追击冲突（后车逼近前车）
    """

    conflict_type: str
    time_step: int
    agv_high: int
    agv_low: int
    node: Optional[Node] = None
    edge: Optional[Edge] = None
    detail: str = ""


class TrafficManager:
    """
    集中式冲突与死锁协调器
    """

    def __init__(
        self,
        urgent_w: float = 0.5,
        load_w: float = 0.3,
        remain_w: float = 0.2,
        wait_threshold: int = 3,
    ):
        # 优先级评分权重
        self.urgent_w = urgent_w
        self.load_w = load_w
        self.remain_w = remain_w
        # 低优先级AGV累计等待超过阈值后应考虑局部重规划
        self.wait_threshold = wait_threshold
        # 等待依赖图：A等待B -> wait_graph[A]={B,...}
        self.wait_graph: Dict[int, Set[int]] = {}

    # ===================== 冲突检测 =====================
    @staticmethod
    def _build_reservation_maps(reservation_table: Set[Tuple[int, int, int]]):
        """
        将reservation_table转换为更易查询的数据结构
        """
        time_to_nodes: Dict[int, Set[Node]] = {}
        for x, y, t in reservation_table:
            time_to_nodes.setdefault(t, set()).add((x, y))
        return time_to_nodes

    def detect_node_conflict(
        self,
        agv_id: int,
        segment_path: List[Tuple[int, int, int]],
        reservation_table: Set[Tuple[int, int, int]],
    ) -> Optional[Tuple[int, Node]]:
        """
        检测节点冲突：候选路径上的(x,y,t)是否已被占用
        """
        if not segment_path:
            return None
        for x, y, t in segment_path:
            if (x, y, t) in reservation_table:
                return t, (x, y)
        return None

    def detect_edge_conflict(
        self,
        segment_path: List[Tuple[int, int, int]],
        occupied_edges: Set[Tuple[Node, Node, int]],
    ) -> Optional[Tuple[int, Edge]]:
        """
        检测相向冲突：候选边(u->v,t)的反向边(v->u,t)是否已被占用
        """
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
        segment_path: List[Tuple[int, int, int]],
        reservation_table: Set[Tuple[int, int, int]],
    ) -> Optional[Tuple[int, Node]]:
        """
        检测追击冲突（简化）:
          若候选路径在t+1进入的节点在t时已被占用，视作潜在追击风险
        """
        if len(segment_path) < 2:
            return None
        for i in range(1, len(segment_path)):
            x, y, t = segment_path[i]
            if (x, y, t - 1) in reservation_table:
                return t, (x, y)
        return None

    # ===================== 优先级评分 =====================
    def compute_priority(
        self,
        agv,
        current_time: int,
        remain_dist_est: int,
    ) -> float:
        """
        动态优先级评分（值越大优先级越高）
        因子:
          1) 时间窗紧迫度
          2) 负载占比
          3) 剩余路径短优先（释放资源快）
        """
        # 时间窗紧迫度（基于最后任务截止时间）
        if agv.tasks:
            last_deadline = agv.tasks[-1].deadline
            slack = max(1, last_deadline - current_time)
            urgent_score = 1.0 / slack
        else:
            urgent_score = 0.0

        load_score = agv.load / max(1, Config.AGV_CAPACITY)

        # 剩余路程越短分越高（归一化为0~1近似）
        remain_score = 1.0 / max(1, remain_dist_est)

        return (
            self.urgent_w * urgent_score
            + self.load_w * load_score
            + self.remain_w * remain_score
        )

    def choose_yield_agv(
        self,
        agv_a,
        agv_b,
        time_step: int,
        remain_dist_a: int,
        remain_dist_b: int,
    ) -> Tuple[int, int]:
        """
        冲突时选择让行车:
          返回(high_priority_agv_id, low_priority_agv_id)
        """
        pa = self.compute_priority(agv_a, time_step, remain_dist_a)
        pb = self.compute_priority(agv_b, time_step, remain_dist_b)

        if pa >= pb:
            return agv_a.id, agv_b.id
        return agv_b.id, agv_a.id

    # ===================== 等待依赖图与死锁 =====================
    def add_wait_dependency(self, waiter_id: int, holder_id: int):
        """
        记录等待关系 waiter -> holder
        """
        if waiter_id == holder_id:
            return
        self.wait_graph.setdefault(waiter_id, set()).add(holder_id)

    def clear_wait_dependency(self, waiter_id: int):
        """
        清除某AGV的等待依赖（恢复通行后调用）
        """
        if waiter_id in self.wait_graph:
            self.wait_graph.pop(waiter_id, None)

    def _find_cycle_dfs(
        self,
        node: int,
        visited: Set[int],
        stack: List[int],
        in_stack: Set[int],
    ) -> Optional[List[int]]:
        visited.add(node)
        stack.append(node)
        in_stack.add(node)

        for nxt in self.wait_graph.get(node, set()):
            if nxt not in visited:
                cyc = self._find_cycle_dfs(nxt, visited, stack, in_stack)
                if cyc:
                    return cyc
            elif nxt in in_stack:
                # 回边：提取环
                idx = stack.index(nxt)
                return stack[idx:].copy()

        stack.pop()
        in_stack.remove(node)
        return None

    def detect_deadlock_cycle(self) -> Optional[List[int]]:
        """
        检测等待依赖图中的环（死锁）
        """
        visited: Set[int] = set()
        in_stack: Set[int] = set()
        for node in list(self.wait_graph.keys()):
            if node not in visited:
                cyc = self._find_cycle_dfs(node, visited, [], in_stack)
                if cyc:
                    return cyc
        return None

    def pick_victim_for_deadlock(self, cycle_agv_ids: List[int], agv_map: Dict[int, object]) -> int:
        """
        从死锁环中选“牺牲车”（优先级最低者）执行回退/让行
        """
        victim = cycle_agv_ids[0]
        victim_score = float("inf")

        for aid in cycle_agv_ids:
            agv = agv_map.get(aid)
            if agv is None:
                continue
            # 低优先级（紧迫低、载重低、剩余远）更适合当牺牲车
            remain_est = 10
            if agv.tasks:
                last_task = agv.tasks[-1]
                remain_est = manhattan_dist(agv.start_pos, (last_task.x, last_task.y))
            score = self.compute_priority(agv, getattr(agv, "finish_time", 0), remain_est)
            if score < victim_score:
                victim_score = score
                victim = aid
        return victim

    # ===================== 高层决策接口 =====================
    def resolve_conflict(
        self,
        conflict_type: str,
        agv_a,
        agv_b,
        time_step: int,
        remain_dist_a: int,
        remain_dist_b: int,
        low_wait_count: int = 0,
    ) -> ConflictEvent:
        """
        高层冲突决策:
          1) 先按优先级决定让行方
          2) 低优先级默认等待
          3) 等待超过阈值，建议触发局部重规划
        """
        high, low = self.choose_yield_agv(
            agv_a=agv_a,
            agv_b=agv_b,
            time_step=time_step,
            remain_dist_a=remain_dist_a,
            remain_dist_b=remain_dist_b,
        )

        action = "wait"
        if low_wait_count >= self.wait_threshold:
            action = "replan"

        detail = f"low_agv_action={action}"
        return ConflictEvent(
            conflict_type=conflict_type,
            time_step=time_step,
            agv_high=high,
            agv_low=low,
            detail=detail,
        )
