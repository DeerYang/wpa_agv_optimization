"""
狼个体评估器（全流程统一评分核心）。

你可以把这个文件理解为：
1) 路径重建器：把任务分配方案变成时空路径。
2) 交通协调器调用方：在重建时接入冲突/死锁策略。
3) 指标计算器：输出 F/N/D/T 以及冲突统计。
"""

import random
from typing import Dict, List, Optional, Set, Tuple

# 全局配置参数来源。
from .config import Config
# 单段路径规划器（Tent-DFS）。
from .pathfinding import TentDFSPlanner
# 冲突与死锁策略模块。
from .traffic_manager import TrafficManager
# 通用工具：曼哈顿距离 + 混沌序列生成。
from .utils import manhattan_dist, tent_map_generate


# 空间节点别名，便于阅读类型注解。
Node = Tuple[int, int]
# 时空节点别名，格式为 (x, y, t)。
TimedNode = Tuple[int, int, int]


class WolfEvaluator:
    # 说明：
    # 1) 这个类是“评分中枢”，所有算子产生的新解都会在这里被重建与评分。
    # 2) 你阅读时如果只看一个文件，优先看本文件的 rebuild_wolf。
    # 3) rebuild_wolf 的主循环就是系统真实执行逻辑：规划 -> 冲突检测 -> 决策 -> 写表 -> 统计。
    """
    统一评估入口。

    上层（initializer、wpa_ops）会调用 rebuild_wolf：
    - 输入：只含任务分配顺序的 wolf。
    - 输出：填充路径与指标后的完整 wolf。
    """

    def __init__(self, grid_map):
        # grid_map：静态栅格地图，包含障碍信息；整个评估周期内不变。
        # 初始化路径规划器。
        self.planner = TentDFSPlanner(grid_map)
        # 初始化冲突与死锁协调器。
        self.traffic_manager = TrafficManager()

    @staticmethod
    def _agv_remain_dist_est(agv) -> int:
        # 该估计值只用于“冲突时优先级比较”，不是最终距离指标，因此允许粗估。
        """
        粗略估算 AGV 剩余路程（用于冲突优先级评分）。
        """
        # 无任务时返回最小正值，避免后续除零。
        if not agv.tasks:
            return 1
        # 取最后任务点做近似估计。
        last_task = agv.tasks[-1]
        return max(1, manhattan_dist(agv.start_pos, (last_task.x, last_task.y)))

    @staticmethod
    def _event_action(detail: str) -> str:
        # detail 是策略层给评估层的轻量文本协议。
        # 当前协议仅区分 wait 与 replan，后续可扩展为 slow_down / reroute 等动作。
        """
        从 conflict event 的 detail 文本里解析动作。
        """
        # 只要包含 replan 字样就当成重规划。
        if "replan" in detail:
            return "replan"
        # 其余情况统一按等待处理。
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
        # 该函数只负责“发现冲突并定位冲突对方”，不负责“怎么解决”。
        # 解决策略由 TrafficManager.resolve_conflict 决定，职责分离便于调参和替换策略。
        """
        对候选段路径做冲突判定。

        返回值：
        - 命中冲突：("node"/"edge"/"rear", 冲突时刻, 对方AGV_ID)
        - 无冲突：None
        """
        # ---------- 1) 节点冲突检测 ----------
        # 若候选路径触碰到已预约的时空点，则是节点冲突。
        node_hit = self.traffic_manager.detect_node_conflict(agv.id, segment_path, reservation_table)
        if node_hit is not None:
            # 取冲突时刻和冲突节点。
            t, node = node_hit
            # 从占用表反查该时空点的占用者。
            holder_id = reservation_owner.get((node[0], node[1], t))
            # 只有占用者有效且在映射中才返回冲突。
            if holder_id is not None and holder_id in agv_map:
                return "node", t, holder_id

        # ---------- 2) 相向边冲突检测 ----------
        # 检测 u->v 与 v->u 的同刻对冲。
        edge_hit = self.traffic_manager.detect_edge_conflict(segment_path, occupied_edges)
        if edge_hit is not None:
            # 取冲突时刻与本车边。
            t, edge = edge_hit
            # 反向边所有者即冲突对手。
            holder_id = edge_owner.get((edge[1], edge[0], t))
            if holder_id is not None and holder_id in agv_map:
                return "edge", t, holder_id

        # ---------- 3) 追尾风险检测 ----------
        # 用 t 与 t-1 的节点占用关系做简化判定。
        rear_hit = self.traffic_manager.detect_rear_conflict(segment_path, reservation_table)
        if rear_hit is not None:
            t, node = rear_hit
            # 追尾风险里，对手在 t-1 占用该点。
            holder_id = reservation_owner.get((node[0], node[1], t - 1))
            if holder_id is not None and holder_id in agv_map:
                return "rear", t, holder_id

        # 三类都未命中，则无冲突。
        return None

    def rebuild_wolf(self, wolf):
        # 阅读导航（逐句阅读建议）：
        # A. 先看资源表定义：reservation_table / reservation_owner / occupied_edges / edge_owner
        # B. 再看双层循环：for agv in ... + for target_pos in ...
        # C. 再看 while retries：这是冲突处理与重规划闭环
        # D. 最后看指标回写：F/N/D/T 及冲突统计如何落到 wolf 字段
        """
        重建并评估狼个体。

        整体流程：
        1) 初始化全局时空资源表和统计量。
        2) 按 AGV 顺序、按目标点顺序逐段规划路径。
        3) 每段规划后做冲突判定与动作决策（wait/replan）。
        4) 写入节点和边占用，更新时间与位置状态。
        5) 汇总 F/N/D/T 与冲突统计并写回 wolf。
        """
        # ===================== 全局资源状态 =====================
        # 节点预约表：记录所有已占用时空节点。
        reservation_table: Set[TimedNode] = set()
        # 节点所有者：记录某时空节点是谁占用的。
        reservation_owner: Dict[TimedNode, int] = {}
        # 边占用表：用于对向冲突检测。
        occupied_edges: Set[Tuple[Node, Node, int]] = set()
        # 边所有者表：记录边占用者，冲突时用来定位对手 AGV。
        edge_owner: Dict[Tuple[Node, Node, int], int] = {}
        # 每台车等待次数，用于达到阈值后触发重规划建议。
        wait_counts: Dict[int, int] = {}
        # AGV 映射表：方便按 id 快速取对象。
        agv_map: Dict[int, object] = {agv.id: agv for agv in wolf.agv_list}

        # ===================== 目标函数累计量 =====================
        # 系统总路程 D。
        total_dist = 0
        # 系统总时间窗惩罚 T。
        total_time_penalty = 0

        # ===================== 新增统计量 =====================
        # 冲突处理次数。
        conflict_count = 0
        # 死锁解锁次数。
        deadlock_count = 0
        # 重规划触发次数。
        replan_count = 0

        # ===================== 混沌序列准备 =====================
        # 随机生成混沌初值。
        x0 = random.random()
        # 生成固定长度混沌序列供路径规划器迭代消费。
        chaos_seq = tent_map_generate(n=5000, x0=x0)
        # 转为迭代器，避免一次性传递整个列表。
        chaos_iter = iter(chaos_seq)

        # ===================== 逐车处理 =====================
        for agv in wolf.agv_list:
            # 初始化该车等待计数。
            wait_counts.setdefault(agv.id, 0)
            # 当前空间位置从该车起点开始。
            curr_pos = agv.start_pos
            # 当前时间从 0 开始。
            curr_time = 0
            # 该车完整时空路径容器。
            full_path: List[TimedNode] = []

            # 构造目标链：先全部任务点，最后卸货点。
            targets = [(t.x, t.y) for t in agv.tasks]
            if agv.tasks:
                targets.append(Config.DEPOT_NODE)

            # 按目标链逐段规划。
            for target_pos in targets:
                # 当前段最多重试次数（防止无限循环）。
                max_retries = 8
                retries = 0
                # 段路径初始化为空，成功规划后赋值。
                segment_path: Optional[List[TimedNode]] = None

                # 段级重试循环。
                while retries <= max_retries:
                    # ---------- A. 尝试规划一段 ----------
                    segment_path = self.planner.plan(
                        curr_pos,
                        target_pos,
                        curr_time,
                        reservation_table,
                        chaos_iter,
                    )

                    # ---------- B. 规划失败处理 ----------
                    if segment_path is None:
                        # 记录一次重规划统计。
                        replan_count += 1
                        # 记录该车等待次数。
                        wait_counts[agv.id] += 1
                        # 当前时间后移 1 秒再试。
                        curr_time += 1
                        # 重试计数 +1。
                        retries += 1
                        # 继续下一次尝试。
                        continue

                    # ---------- C. 规划成功后做冲突判定 ----------
                    conflict = self._detect_conflict_event(
                        agv=agv,
                        segment_path=segment_path,
                        reservation_table=reservation_table,
                        reservation_owner=reservation_owner,
                        occupied_edges=occupied_edges,
                        edge_owner=edge_owner,
                        agv_map=agv_map,
                    )

                    # 若无冲突，接受本段，跳出重试循环。
                    if conflict is None:
                        break

                    # ---------- D. 冲突协调 ----------
                    # 解包冲突三元组。
                    conflict_type, time_step, holder_id = conflict
                    # 找到冲突对手对象。
                    holder_agv = agv_map[holder_id]
                    # 记录冲突统计。
                    conflict_count += 1

                    # 请求交通协调器给出处置建议。
                    event = self.traffic_manager.resolve_conflict(
                        conflict_type=conflict_type,
                        agv_a=agv,
                        agv_b=holder_agv,
                        time_step=time_step,
                        remain_dist_a=max(1, manhattan_dist(curr_pos, target_pos)),
                        remain_dist_b=self._agv_remain_dist_est(holder_agv),
                        low_wait_count=wait_counts.get(agv.id, 0),
                    )
                    # 解析建议动作。
                    action = self._event_action(event.detail)

                    # 当前实现是顺序规划，历史路径不可回滚，默认当前车让行。
                    self.traffic_manager.add_wait_dependency(
                        waiter_id=agv.id,
                        holder_id=holder_id,
                    )
                    # 当前车等待计数增加。
                    wait_counts[agv.id] = wait_counts.get(agv.id, 0) + 1

                    # ---------- E. 死锁检测 ----------
                    cycle = self.traffic_manager.detect_deadlock_cycle()
                    if cycle:
                        # 记录一次死锁解锁过程。
                        deadlock_count += 1
                        # 选牺牲方。
                        victim = self.traffic_manager.pick_victim_for_deadlock(cycle, agv_map)
                        # 清除牺牲方依赖边。
                        self.traffic_manager.clear_wait_dependency(victim)
                        # 若当前车是牺牲方，强制重规划动作。
                        if victim == agv.id:
                            action = "replan"

                    # ---------- F. 执行动作 ----------
                    if action == "replan":
                        # 记录重规划次数。
                        replan_count += 1
                        # 重规划动作让出更多时间窗。
                        curr_time += 2
                    else:
                        # 等待动作让出 1 秒。
                        curr_time += 1

                    # 重试计数 +1 后再次规划。
                    retries += 1

                # ===================== 段失败极端兜底 =====================
                if segment_path is None:
                    # 给该方案施加大惩罚，避免被误选为优解。
                    total_time_penalty += 10000
                    # 构造一个最小兜底节点，保证后续流程不崩。
                    segment_path = [(target_pos[0], target_pos[1], curr_time + 10)]

                # ===================== 段路径拼接 =====================
                if full_path:
                    # 后续段跳过首节点，避免与上一段尾节点重复。
                    full_path.extend(segment_path[1:])
                else:
                    # 第一段直接全量加入。
                    full_path.extend(segment_path)

                # ===================== 状态推进 =====================
                # 取段末节点。
                last_node = segment_path[-1]
                # 更新当前位置到段末坐标。
                curr_pos = (last_node[0], last_node[1])
                # 更新当前时间：段末时刻 + 服务时间。
                curr_time = last_node[2] + Config.SERVICE_TIME

                # ===================== 占用登记：节点 =====================
                for p in segment_path:
                    # 写入节点预约表。
                    reservation_table.add(p)
                    # 写入节点占用者。
                    reservation_owner[p] = agv.id

                # ===================== 占用登记：边 =====================
                for i in range(len(segment_path) - 1):
                    # 当前边起点。
                    u = (segment_path[i][0], segment_path[i][1])
                    # 当前边终点。
                    v = (segment_path[i + 1][0], segment_path[i + 1][1])
                    # 当前边时刻（到达 v 的时刻）。
                    t = segment_path[i + 1][2]
                    # 组合边键。
                    edge_key = (u, v, t)
                    # 登记边占用。
                    occupied_edges.add(edge_key)
                    # 登记边占用者。
                    edge_owner[edge_key] = agv.id

                # ===================== 服务时间占用登记 =====================
                for t_wait in range(1, Config.SERVICE_TIME + 1):
                    # 在段末节点追加服务占用时空点。
                    wait_node = (last_node[0], last_node[1], last_node[2] + t_wait)
                    reservation_table.add(wait_node)
                    reservation_owner[wait_node] = agv.id

                # 本段推进成功后，清除该车等待依赖并重置等待次数。
                self.traffic_manager.clear_wait_dependency(agv.id)
                wait_counts[agv.id] = 0

            # ===================== 单车结果回写 =====================
            # 写回完整路径。
            agv.path = full_path
            # 写回完成时刻。
            agv.finish_time = curr_time
            # 累加系统总路程。
            total_dist += len(full_path)

            # 若该车有任务，则计算其截止超时惩罚。
            if agv.tasks:
                last_deadline = agv.tasks[-1].deadline
                if curr_time > last_deadline:
                    total_time_penalty += (curr_time - last_deadline)

        # ===================== 方案级指标回写 =====================
        wolf.total_dist = total_dist
        wolf.time_penalty = total_time_penalty
        wolf.vehicle_num = len([agv for agv in wolf.agv_list if agv.tasks])
        wolf.fitness = (
            (Config.W1_DIST * total_dist)
            + (Config.W2_NUM * wolf.vehicle_num)
            + (Config.W3_TIME * total_time_penalty)
        )

        # 回写统计信息，便于最终输出和对比实验。
        wolf.conflict_count = conflict_count
        wolf.deadlock_count = deadlock_count
        wolf.replan_count = replan_count
        return wolf
