"""
WPA 算子模块（游走/召唤/围攻）。

阅读建议：
1) 先看 scouting：最简单的邻域扰动。
2) 再看 summoning：当前版本提升最大的算子。
3) 最后看 besieging：Levy 步长驱动的混合搜索。
"""

import copy
import random

import numpy as np
from scipy.special import gamma

# 全局参数。
from .config import Config
# AGV 数据结构（解码时会创建新 AGV）。
from .models import AGV
# 估算代价时需要曼哈顿距离。
from .utils import manhattan_dist


class WPAOperators:
    """WPA 三算子集合。"""

    def __init__(self, evaluator):
        # evaluator 负责“把任务序列变成可行路径并打分”；
        # 本类负责“如何扰动任务序列以产生候选新解”。
        # evaluator 负责重建路径与评分，算子只负责“怎么变”。
        self.evaluator = evaluator

    def _flatten_tasks(self, wolf):
        # 把多车任务展开为全局线性序列，便于执行交叉、迁移、插入等序列算子。
        """
        将多 AGV 任务队列展平为全局序列。
        """
        # 初始化空序列。
        seq = []
        # 按 AGV 顺序拼接每台车的任务。
        for agv in wolf.agv_list:
            seq.extend(agv.tasks)
        # 返回展平结果。
        return seq

    def _decode_sequence_to_agvs(self, task_seq):
        # 基础解码：按容量阈值切分，不做复杂代价优化。
        """
        基础解码器：仅按载重约束切分任务序列。

        该函数是“简单版解码”，当前主要保留作参考与兜底。
        """
        # 空序列直接返回空 AGV 列表。
        if not task_seq:
            return []

        # 解码结果容器。
        agv_list = []
        # 当前 AGV 编号从 0 开始。
        agv_id = 0
        # 创建当前 AGV。
        curr_agv = AGV(agv_id=agv_id, start_pos=Config.START_NODES[agv_id])
        # 当前 AGV 已分配载重。
        curr_load = 0

        # 逐任务扫描并分配。
        for task in task_seq:
            # 若单任务超过最大载重，无法解码。
            if task.weight > Config.AGV_CAPACITY:
                return None

            # 若继续放入会超载，则收尾当前 AGV 并新开一台。
            if curr_load + task.weight > Config.AGV_CAPACITY:
                if curr_agv.tasks:
                    curr_agv.load = curr_load
                    agv_list.append(curr_agv)
                agv_id += 1
                if agv_id >= len(Config.START_NODES):
                    return None
                curr_agv = AGV(agv_id=agv_id, start_pos=Config.START_NODES[agv_id])
                curr_load = 0

            # 放入当前任务。
            curr_agv.tasks.append(task)
            # 更新载重。
            curr_load += task.weight

        # 循环结束后收尾最后一台 AGV。
        if curr_agv.tasks:
            curr_agv.load = curr_load
            agv_list.append(curr_agv)

        # 返回解码结果。
        return agv_list

    def _estimate_route_cost(self, tasks, start_pos):
        # 该代价函数只用于“算子内部快速比较插入位置优劣”，
        # 最终真实优劣仍以 evaluator.rebuild_wolf 的全流程评分为准。
        """
        估算单车执行任务序列的代价。

        代价组成：
        - 总距离
        - 超时惩罚（乘以 W3_TIME）
        """
        # 无任务代价为 0。
        if not tasks:
            return 0.0

        # 当前坐标初始化为起点。
        curr = start_pos
        # 当前时间初始化为 0。
        curr_time = 0
        # 距离累计。
        dist = 0
        # 超时累计。
        tardy = 0

        # 按任务顺序估算执行成本。
        for task in tasks:
            # 计算去往任务点的距离。
            step = manhattan_dist(curr, (task.x, task.y))
            dist += step
            # 时间推进：路程时间 + 服务时间。
            curr_time += step + Config.SERVICE_TIME
            # 累计该任务超时量。
            tardy += max(0, curr_time - task.deadline)
            # 更新当前位置。
            curr = (task.x, task.y)

        # 加上最后回卸货点的距离。
        dist += manhattan_dist(curr, Config.DEPOT_NODE)
        # 返回总代价。
        return dist + (Config.W3_TIME * tardy)

    def _decode_sequence_to_agvs_cost_based(self, task_seq):
        # 成本导向解码（当前召唤算子核心）：
        # - 对每个任务尝试所有可行插入位；
        # - 以最小增量代价策略决定插入点；
        # - 若插不进任何现有车辆，再尝试开新车。
        """
        增量代价最小插入解码器（召唤算子主力解码器）。

        处理策略：
        - 对每个任务，尝试插入每台可行 AGV 的每个位置。
        - 选取代价增量最小的插入方案。
        - 若都不可行，再尝试新开 AGV。
        """
        # 空序列返回空结果。
        if not task_seq:
            return []

        # 已创建 AGV 列表。
        agv_list = []
        # 下一个可用 AGV 编号。
        next_id = 0
        # 最大可用 AGV 数量由起始泊位数决定。
        max_agv = len(Config.START_NODES)

        # 逐任务做增量插入。
        for task in task_seq:
            # 单任务超载直接失败。
            if task.weight > Config.AGV_CAPACITY:
                return None

            # 记录当前最优方案（insert/new）。
            best_plan = None

            # ---------- 方案A：插入现有 AGV ----------
            for agv_idx, agv in enumerate(agv_list):
                # 当前车容量不够，跳过。
                if agv.load + task.weight > Config.AGV_CAPACITY:
                    continue
                # 计算插入前基准代价。
                base_cost = self._estimate_route_cost(agv.tasks, agv.start_pos)
                # 遍历所有可插入位置（含头尾）。
                for pos in range(len(agv.tasks) + 1):
                    # 构造插入后的任务序列。
                    new_tasks = agv.tasks[:pos] + [task] + agv.tasks[pos:]
                    # 计算插入后代价。
                    new_cost = self._estimate_route_cost(new_tasks, agv.start_pos)
                    # 计算增量。
                    delta = new_cost - base_cost
                    # 更新最优方案。
                    if (best_plan is None) or (delta < best_plan["delta"]):
                        best_plan = {
                            "mode": "insert",
                            "agv_idx": agv_idx,
                            "pos": pos,
                            "delta": delta,
                        }

            # ---------- 方案B：新开 AGV ----------
            if next_id < max_agv:
                # 新车起点。
                new_start = Config.START_NODES[next_id]
                # 新车只执行该任务的代价。
                new_cost = self._estimate_route_cost([task], new_start)
                # 给开新车加轻微偏置，鼓励优先复用已有车辆。
                open_bias = Config.W2_NUM * 0.05
                open_delta = new_cost + open_bias
                # 与当前最优比较。
                if (best_plan is None) or (open_delta < best_plan["delta"]):
                    best_plan = {"mode": "new", "delta": open_delta}

            # 两种方案都不可行则失败。
            if best_plan is None:
                return None

            # 应用最优方案。
            if best_plan["mode"] == "insert":
                target = agv_list[best_plan["agv_idx"]]
                target.tasks.insert(best_plan["pos"], task)
                target.load += task.weight
            else:
                new_agv = AGV(agv_id=next_id, start_pos=Config.START_NODES[next_id])
                new_agv.tasks = [task]
                new_agv.load = task.weight
                agv_list.append(new_agv)
                next_id += 1

        # 返回增量解码结果。
        return agv_list

    def scouting(self, wolf):
        # 游走：轻量局部扰动，探索邻域解，扰动幅度小、风险低。
        """
        游走算子：随机选一台任务数>=2的车，交换两个任务顺序。
        """
        # 深拷贝，避免原个体被污染。
        new_wolf = copy.deepcopy(wolf)
        # 只挑可交换任务顺序的 AGV。
        active_agvs = [agv for agv in new_wolf.agv_list if len(agv.tasks) >= 2]
        # 若没有可操作 AGV，返回原个体。
        if not active_agvs:
            return wolf

        # 随机选目标车。
        target_agv = random.choice(active_agvs)
        # 随机抽两个任务索引。
        idx1, idx2 = random.sample(range(len(target_agv.tasks)), 2)
        # 执行交换。
        target_agv.tasks[idx1], target_agv.tasks[idx2] = target_agv.tasks[idx2], target_agv.tasks[idx1]

        # 重建并重评估。
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # 贪婪接受：只有更优才保留新个体。
        if new_wolf.fitness < wolf.fitness:
            print(f"  [游走成功] F值优化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f}")
            return new_wolf
        return wolf

    def summoning(self, wolf, alpha_wolf):
        # 召唤：利用头狼结构信息（片段继承）指导个体向更优结构靠近。
        # 当前版本采用 OX 片段继承 + 成本导向解码，是召唤算子的主提升点。
        """
        召唤算子（当前增强版）。

        核心流程：
        1) 以 OX 思想继承头狼片段。
        2) 用猛狼顺序补全剩余任务。
        3) 用增量代价解码器还原为多 AGV 方案。
        4) 重评估后仅在更优时接受。
        """
        # 深拷贝父代个体。
        new_wolf = copy.deepcopy(wolf)
        alpha_copy = copy.deepcopy(alpha_wolf)

        # 基础边界检查。
        if not alpha_copy.agv_list or not new_wolf.agv_list:
            return wolf
        # 召唤不是每次都触发，保留一定随机探索空间。
        if random.random() > 0.6:
            return wolf

        # 拉平任务序列。
        alpha_tasks = self._flatten_tasks(alpha_copy)
        wolf_tasks = self._flatten_tasks(new_wolf)
        if len(alpha_tasks) < 2 or len(wolf_tasks) < 2:
            return wolf

        # 以猛狼任务集合为基准，构造 ID 映射。
        wolf_task_map = {t.id: t for t in wolf_tasks}
        wolf_ids = [t.id for t in wolf_tasks]
        alpha_ids = [t.id for t in alpha_tasks if t.id in wolf_task_map]

        # 若任务集合不一致则不执行召唤。
        if len(alpha_ids) != len(wolf_ids):
            return wolf

        # ---------- OX 片段继承 ----------
        n = len(wolf_ids)
        seg_len_min = 2
        seg_len_max = min(4, n)
        if seg_len_max < seg_len_min:
            return wolf

        # 随机片段长度。
        seg_len = random.randint(seg_len_min, seg_len_max)
        # 头狼片段起点。
        alpha_start = random.randint(0, n - seg_len)
        # 截取头狼片段。
        alpha_segment = alpha_ids[alpha_start: alpha_start + seg_len]
        # 子序列插入起点。
        child_start = random.randint(0, n - seg_len)

        # 子代 ID 序列初始化为 None。
        child_ids = [None] * n
        # 放入头狼片段。
        child_ids[child_start: child_start + seg_len] = alpha_segment

        # 其余位置按猛狼原顺序补齐。
        fill_candidates = [tid for tid in wolf_ids if tid not in alpha_segment]
        fill_idx = 0
        for i in range(n):
            if child_ids[i] is None:
                child_ids[i] = fill_candidates[fill_idx]
                fill_idx += 1

        # ---------- 解码与评估 ----------
        # 把 ID 序列还原为 Task 序列。
        child_task_seq = [wolf_task_map[tid] for tid in child_ids]
        # 用增量代价解码器解码。
        decoded_agvs = self._decode_sequence_to_agvs_cost_based(child_task_seq)
        if decoded_agvs is None:
            return wolf
        # 写回新个体 AGV 列表。
        new_wolf.agv_list = decoded_agvs
        # 重建路径并评估。
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # 严格改进才接受。
        if new_wolf.fitness < wolf.fitness:
            print(
                f"  [召唤成功-增强] F值变化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f} "
                f"(片段长度={seg_len})"
            )
            return new_wolf
        return wolf

    def _levy_flight_step(self, beta=1.5, step_scale=1.0):
        # Levy 步长用于生成“多数小步、少数大步”的搜索行为分布。
        """
        生成 Levy 步长（Mantegna 方法）。
        """
        # 计算 sigma 分子项。
        sigma_num = gamma(1 + beta) * np.sin(np.pi * beta / 2)
        # 计算 sigma 分母项。
        sigma_den = gamma((1 + beta) / 2) * beta * np.power(2, (beta - 1) / 2)
        # 计算 sigma。
        sigma = np.power(sigma_num / sigma_den, 1 / beta)
        # 采样 u。
        u = np.random.normal(0, sigma, 1)
        # 采样 v。
        v = np.random.normal(0, 1, 1)
        # 计算 step。
        step = step_scale * u / np.power(np.abs(v), 1 / beta)
        # 取绝对值做无方向步长。
        return abs(step[0])

    def besieging(self, wolf, curr_iter, max_iter):
        # 围攻：由 Levy 步长驱动“局部微调/全局跳变”二分策略。
        # - 小步长：更偏 exploitation（精修当前可行解）
        # - 大步长：更偏 exploration（跨车迁移任务）
        """
        围攻算子：Levy 步长决定“局部微调”还是“全局迁移”。
        """
        # 深拷贝个体。
        new_wolf = copy.deepcopy(wolf)
        # 仅保留有任务的 AGV。
        active_agvs = [agv for agv in new_wolf.agv_list if agv.tasks]
        if not active_agvs:
            return wolf
        # 围攻触发概率控制，避免过强扰动。
        if random.random() > 0.8:
            return wolf

        # 迭代后期减小步长，逐渐从探索转向开发。
        step_scale = 2.0 * (1 - curr_iter / max_iter)
        levy_step = self._levy_flight_step(step_scale=step_scale)
        step_threshold = 1.0

        # ---------- 短步长：局部微调 ----------
        if levy_step < step_threshold:
            target_agv = random.choice(active_agvs)
            if len(target_agv.tasks) < 2:
                return wolf
            # 大概率做相邻交换，小概率做单任务插入。
            if random.random() < 0.7:
                swap_idx = random.randint(0, len(target_agv.tasks) - 2)
                target_agv.tasks[swap_idx], target_agv.tasks[swap_idx + 1] = (
                    target_agv.tasks[swap_idx + 1],
                    target_agv.tasks[swap_idx],
                )
            else:
                move_idx, insert_idx = random.sample(range(len(target_agv.tasks)), 2)
                move_task = target_agv.tasks.pop(move_idx)
                target_agv.tasks.insert(insert_idx, move_task)
            # 维护载重一致性。
            target_agv.load = sum([task.weight for task in target_agv.tasks])

        # ---------- 长步长：全局跳变 ----------
        else:
            # 需要至少两台车才可跨车迁移。
            if len(active_agvs) < 2:
                # 若不足两台，降级为再尝试一次围攻（原逻辑保留）。
                return self.besieging(wolf, curr_iter, max_iter)

            # 随机选两台车做迁移。
            agv_a, agv_b = random.sample(active_agvs, 2)
            if not agv_a.tasks:
                return wolf

            # 从 A 弹出一个任务，插入到 B 任意位置。
            move_task_idx = random.randint(0, len(agv_a.tasks) - 1)
            move_task = agv_a.tasks.pop(move_task_idx)
            agv_b.tasks.insert(random.randint(0, len(agv_b.tasks)), move_task)

            # 更新两车载重。
            agv_a.load = sum([task.weight for task in agv_a.tasks])
            agv_b.load = sum([task.weight for task in agv_b.tasks])

            # 若 B 超载，做简单拆分并新建一台车承接后半段任务。
            if agv_b.load > Config.AGV_CAPACITY:
                split_idx = len(agv_b.tasks) // 2
                split_tasks = agv_b.tasks[split_idx:]
                agv_b.tasks = agv_b.tasks[:split_idx]
                agv_b.load = sum([task.weight for task in agv_b.tasks])

                new_agv_id = max([agv.id for agv in new_wolf.agv_list]) + 1
                if new_agv_id >= len(Config.START_NODES):
                    new_agv_id = 0
                new_agv = AGV(agv_id=new_agv_id, start_pos=Config.START_NODES[new_agv_id])
                new_agv.tasks = split_tasks
                new_agv.load = sum([task.weight for task in split_tasks])
                new_wolf.agv_list.append(new_agv)

            # 清理空任务车辆。
            new_wolf.agv_list = [agv for agv in new_wolf.agv_list if agv.tasks]

        # 重建与重评估。
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # 贪婪接受。
        if new_wolf.fitness < wolf.fitness:
            print(f"  [围攻成功] F值优化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f} (Levy步长={levy_step:.2f})")
            return new_wolf
        return wolf
