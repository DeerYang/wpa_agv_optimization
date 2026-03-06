"""
交通冲突与死锁协调模块（策略层）。

阅读目的：
- 你在阅读 evaluator 时，会看到它把“检测到冲突之后怎么办”委托给这里。
- 这个文件不做路径搜索，只做“判定、评分、决策、解锁建议”。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# 读取全局参数（如 AGV 容量）。
from .config import Config
# 复用曼哈顿距离工具函数，用于估算剩余路程。
from .utils import manhattan_dist


# 二维网格节点类型：(x, y)。
Node = Tuple[int, int]
# 边类型：((x1,y1),(x2,y2))。
Edge = Tuple[Node, Node]


@dataclass
class ConflictEvent:
    """
    冲突事件对象。

    用途：
    - 统一封装冲突处理结果，供上层（evaluator）读取。
    """

    # 冲突类型：node / edge / rear。
    conflict_type: str
    # 冲突发生时刻。
    time_step: int
    # 高优先级 AGV（先行）。
    agv_high: int
    # 低优先级 AGV（让行）。
    agv_low: int
    # 若是节点冲突，可填冲突节点。
    node: Optional[Node] = None
    # 若是边冲突，可填冲突边。
    edge: Optional[Edge] = None
    # 附加动作信息，如 "low_agv_action=wait/replan"。
    detail: str = ""


class TrafficManager:
    # 角色定位：
    # - 本模块是“策略层”，负责冲突识别后的优先级判定和动作建议；
    # - 本模块不直接修改路径，不直接操作 reservation_table 的写入；
    # - 真正执行动作（等待、重规划）在 evaluator 中完成。
    """
    集中式冲突与死锁协调器。

    核心能力：
    1) 冲突检测：节点冲突、对向边冲突、追尾风险。
    2) 动态优先级评分：决定谁让行。
    3) 等待依赖图与死锁环检测。
    4) 冲突处置建议：wait 或 replan。
    """

    def __init__(
        self,
        urgent_w: float = 0.5,
        load_w: float = 0.3,
        remain_w: float = 0.2,
        wait_threshold: int = 3,
    ):
        # urgent_w/load_w/remain_w：优先级打分权重。
        # wait_threshold：低优先级车辆连续等待次数阈值，超过后建议 replan。
        # 时间紧迫度权重（deadline 越近越优先）。
        self.urgent_w = urgent_w
        # 负载权重（载重越高越优先）。
        self.load_w = load_w
        # 剩余路程权重（剩余越短越优先）。
        self.remain_w = remain_w
        # 低优先级车辆连续等待阈值，超过阈值后建议重规划。
        self.wait_threshold = wait_threshold
        # 等待依赖图：A 等 B 记作 A -> B。
        self.wait_graph: Dict[int, Set[int]] = {}

    @staticmethod
    def _build_reservation_maps(reservation_table: Set[Tuple[int, int, int]]):
        # 工具函数：把三元组集合按时间分桶，便于分析同一时刻占用。
        """
        将 reservation_table 按时间拆分。

        例如：
        - 输入是 {(x,y,t), ...}
        - 输出是 {t: {(x,y), ...}, ...}

        当前主流程暂未直接使用该函数，但保留便于后续扩展。
        """
        # 初始化按时间分组的字典。
        time_to_nodes: Dict[int, Set[Node]] = {}
        # 遍历每个时空占用点。
        for x, y, t in reservation_table:
            # 若该时刻不存在集合则先创建，再加入节点。
            time_to_nodes.setdefault(t, set()).add((x, y))
        # 返回分组结果。
        return time_to_nodes

    def detect_node_conflict(
        self,
        agv_id: int,
        segment_path: List[Tuple[int, int, int]],
        reservation_table: Set[Tuple[int, int, int]],
    ) -> Optional[Tuple[int, Node]]:
        # 节点冲突定义：候选路径中的任意 (x,y,t) 已被其他车辆占用。
        """
        检测节点冲突：候选路径是否命中已预约的 (x,y,t)。

        返回：
        - 命中时返回 (t, (x,y))
        - 否则返回 None
        """
        # 空路径无需检测，直接无冲突。
        if not segment_path:
            return None
        # 逐节点检查是否已被占用。
        for x, y, t in segment_path:
            if (x, y, t) in reservation_table:
                return t, (x, y)
        # 全部通过则无冲突。
        return None

    def detect_edge_conflict(
        self,
        segment_path: List[Tuple[int, int, int]],
        occupied_edges: Set[Tuple[Node, Node, int]],
    ) -> Optional[Tuple[int, Edge]]:
        # 边冲突定义：本车计划在 t 走 u->v，而已有车辆在同一 t 走 v->u（对向穿越）。
        """
        检测对向边冲突：
        - 若本车计划在 t 走 u->v，
        - 且已有车辆在同一 t 走 v->u，
        - 则判定为对向冲突。
        """
        # 单点路径没有“边”，无需检测。
        if len(segment_path) < 2:
            return None
        # 遍历相邻节点对，构造每条边。
        for i in range(len(segment_path) - 1):
            # 当前边起点。
            u = (segment_path[i][0], segment_path[i][1])
            # 当前边终点。
            v = (segment_path[i + 1][0], segment_path[i + 1][1])
            # 边发生时刻取到达终点时刻。
            t = segment_path[i + 1][2]
            # 若反向边在同刻已被占用，则冲突。
            if (v, u, t) in occupied_edges:
                return t, (u, v)
        # 未发现冲突。
        return None

    def detect_rear_conflict(
        self,
        segment_path: List[Tuple[int, int, int]],
        reservation_table: Set[Tuple[int, int, int]],
    ) -> Optional[Tuple[int, Node]]:
        # 追尾风险定义（保守规则）：本车在 t 进入节点，而该节点在 t-1 被占用。
        """
        检测简化追尾风险。

        规则：
        - 若本车在 t 时刻进入节点 (x,y)，
        - 且该节点在 t-1 时刻刚被占用，
        - 则认为有追尾风险（用于保守避让）。
        """
        # 至少要有“下一步进入”才谈追尾。
        if len(segment_path) < 2:
            return None
        # 从第二个节点开始检查（第一个是当前点）。
        for i in range(1, len(segment_path)):
            x, y, t = segment_path[i]
            if (x, y, t - 1) in reservation_table:
                return t, (x, y)
        # 未发现追尾风险。
        return None

    def compute_priority(self, agv, current_time: int, remain_dist_est: int) -> float:
        # 优先级值越高，越应被“保行”；优先级值越低，越应“让行”。
        # 三个分量均已归一化为同量纲近似值，再按权重线性组合。
        """
        计算 AGV 动态优先级分数（越大优先级越高）。

        评分由三项加权：
        - urgent_score：时间紧迫度
        - load_score：载重占比
        - remain_score：剩余路程反比
        """
        # 若车辆有任务，则按最后任务截止时间估算紧迫度。
        if agv.tasks:
            # 取该车最后任务的 deadline 作为总体时限近似。
            last_deadline = agv.tasks[-1].deadline
            # slack 至少为 1，避免除零。
            slack = max(1, last_deadline - current_time)
            # slack 越小，紧迫度越高。
            urgent_score = 1.0 / slack
        else:
            # 无任务车辆紧迫度为 0。
            urgent_score = 0.0

        # 载重占比：当前载重 / 最大载重。
        load_score = agv.load / max(1, Config.AGV_CAPACITY)
        # 剩余路程得分：距离越短，得分越高。
        remain_score = 1.0 / max(1, remain_dist_est)

        # 三项加权求和得到总优先级。
        return self.urgent_w * urgent_score + self.load_w * load_score + self.remain_w * remain_score

    def choose_yield_agv(
        self,
        agv_a,
        agv_b,
        time_step: int,
        remain_dist_a: int,
        remain_dist_b: int,
    ) -> Tuple[int, int]:
        # 返回 (高优先级, 低优先级)，由上层据此生成 wait/replan 动作。
        """
        比较两车优先级，返回 (高优先级车ID, 低优先级车ID)。
        """
        # 计算 A 车优先级。
        pa = self.compute_priority(agv_a, time_step, remain_dist_a)
        # 计算 B 车优先级。
        pb = self.compute_priority(agv_b, time_step, remain_dist_b)
        # A 分数高于或等于 B，则 A 先行。
        if pa >= pb:
            return agv_a.id, agv_b.id
        # 否则 B 先行。
        return agv_b.id, agv_a.id

    def add_wait_dependency(self, waiter_id: int, holder_id: int):
        # 等待依赖边 waiter -> holder：表示 waiter 被 holder 阻塞。
        """
        记录等待依赖：waiter -> holder。
        """
        # 自己等自己无意义，直接忽略。
        if waiter_id == holder_id:
            return
        # 在图中加入一条依赖边。
        self.wait_graph.setdefault(waiter_id, set()).add(holder_id)

    def clear_wait_dependency(self, waiter_id: int):
        # 清除某车作为“等待方”的所有出边；常在该车推进成功后调用。
        """
        清除某辆车作为“等待方”的所有依赖边。
        """
        # 若该车存在等待边，则删除该节点出边。
        if waiter_id in self.wait_graph:
            self.wait_graph.pop(waiter_id, None)

    def _find_cycle_dfs(
        self,
        node: int,
        visited: Set[int],
        stack: List[int],
        in_stack: Set[int],
    ) -> Optional[List[int]]:
        # 标准 DFS 找环：使用 in_stack 识别回边；发现回边即切栈得到一个环。
        """
        DFS 寻环子程序。

        发现回边时，按当前递归栈切出一个环并返回。
        """
        # 标记已访问。
        visited.add(node)
        # 压入当前递归栈。
        stack.append(node)
        # 标记在栈中。
        in_stack.add(node)

        # 遍历该节点所有后继。
        for nxt in self.wait_graph.get(node, set()):
            # 若后继未访问，继续深搜。
            if nxt not in visited:
                cyc = self._find_cycle_dfs(nxt, visited, stack, in_stack)
                if cyc:
                    return cyc
            # 若后继已在递归栈中，说明发现回边，存在环。
            elif nxt in in_stack:
                # 截取从回边起点到栈顶的一段，即一个环。
                idx = stack.index(nxt)
                return stack[idx:].copy()

        # 回溯前弹栈并取消“在栈中”标记。
        stack.pop()
        in_stack.remove(node)
        # 当前分支无环。
        return None

    def detect_deadlock_cycle(self) -> Optional[List[int]]:
        # 死锁判据：等待依赖图中出现有向环。
        """
        检测等待依赖图中是否存在死锁环。
        """
        # 全局访问集合。
        visited: Set[int] = set()
        # 递归栈集合。
        in_stack: Set[int] = set()
        # 从每个尚未访问节点启动 DFS。
        for node in list(self.wait_graph.keys()):
            if node not in visited:
                cyc = self._find_cycle_dfs(node, visited, [], in_stack)
                if cyc:
                    return cyc
        # 没有环则返回 None。
        return None

    def pick_victim_for_deadlock(self, cycle_agv_ids: List[int], agv_map: Dict[int, object]) -> int:
        # 选牺牲方策略：在环上选优先级最低者执行回退/重规划，最小化全局扰动。
        """
        在死锁环中选择牺牲方（优先级最低）作为回退/重规划对象。
        """
        # 默认先取环上的第一个，后续用更低分替换。
        victim = cycle_agv_ids[0]
        # 记录当前最低优先级分值（越小越低）。
        victim_score = float("inf")

        # 遍历环上每台车做打分比较。
        for aid in cycle_agv_ids:
            agv = agv_map.get(aid)
            # 若映射中无该车，跳过。
            if agv is None:
                continue
            # 默认剩余路程估计值。
            remain_est = 10
            # 若有任务，按起点到最后任务点做一个近似估计。
            if agv.tasks:
                last_task = agv.tasks[-1]
                remain_est = manhattan_dist(agv.start_pos, (last_task.x, last_task.y))
            # 用当前车 finish_time 作为 current_time 近似，计算优先级。
            score = self.compute_priority(agv, getattr(agv, "finish_time", 0), remain_est)
            # 分数更低，更新牺牲方。
            if score < victim_score:
                victim_score = score
                victim = aid
        # 返回牺牲方 ID。
        return victim

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
        # 决策接口只输出“建议动作”，不直接改路径。
        # 当前版本规则：
        # 1) 先按优先级决定谁让行；
        # 2) 低优先级默认 wait；
        # 3) 若低优先级等待次数超阈值，则建议 replan。
        """
        冲突高层决策接口。

        决策流程：
        1) 先按优先级决定让行方。
        2) 默认低优先级车辆等待。
        3) 若低优先级车辆等待次数超阈值，建议重规划。
        """
        # 先得到高优先级与低优先级车辆。
        high, low = self.choose_yield_agv(
            agv_a=agv_a,
            agv_b=agv_b,
            time_step=time_step,
            remain_dist_a=remain_dist_a,
            remain_dist_b=remain_dist_b,
        )

        # 默认动作是等待。
        action = "wait"
        # 超阈值则升级为重规划，避免长期饥饿。
        if low_wait_count >= self.wait_threshold:
            action = "replan"

        # 把动作写入 detail 供上层解析。
        detail = f"low_agv_action={action}"
        # 返回封装好的冲突事件对象。
        return ConflictEvent(
            conflict_type=conflict_type,
            time_step=time_step,
            agv_high=high,
            agv_low=low,
            detail=detail,
        )
