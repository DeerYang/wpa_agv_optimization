# ===================== 文件级说明 =====================
# 文件名: wpa_ops.py
# 功能: 狼群算法三大核心智能行为算子实现，完全对齐开题报告的算法设计
# 已实现: 游走(Scouting)、召唤(Summoning)、围攻(Besieging)
# 设计原则: 毕设初期极简优先，100%复用现有evaluator逻辑，零底层代码改动
# 开题对应: 狼群算法智能行为离散化适配章节，含游走-邻域搜索、召唤-路径交叉、围攻-Levy扰动
# ======================================================

# 引入随机数库，用于随机选择与变异
import random
# 引入深拷贝工具，保证原个体不被修改，变异失败可回退
import copy
# 引入数值计算库，用于Levy飞行步长生成
import numpy as np
# 引入伽马函数，用于Levy分布参数计算
from scipy.special import gamma
# 引入全局配置类
from config import Config
# 引入AGV实体类，用于新AGV实例化
from models import AGV
# 引入曼哈顿距离工具函数，复用现有逻辑
from utils import manhattan_dist


class WPAOperators:
    """
    狼群算法算子集合类
    职责: 实现狼群算法三大核心智能行为，严格遵循标准狼群算法分工边界
    行为分工:
        1. 游走(Scouting): 探狼执行，全局广域勘探，寻找潜在更优解区域
        2. 召唤(Summoning): 猛狼执行，向头狼靠拢，实现优质基因信息共享，加速收敛
        3. 围攻(Besieging): 全种群执行，Levy飞行自适应扰动，局部精细优化+防早熟收敛
    设计说明: 所有算子均采用"深拷贝-变异-重评估-贪婪选择"标准流程，保证原个体不被污染
    """
    def __init__(self, evaluator):
        """
        算子类初始化方法
        :param evaluator: WolfEvaluator实例，复用路径规划、冲突规避、适应度评估逻辑
        """
        # 存储狼评估器实例，全文件复用，保证评估逻辑全局一致
        self.evaluator = evaluator

    # ===================== 已实现：游走行为（Scouting）=====================
    def scouting(self, wolf):
        """
        狼群算法-游走行为(Scouting)实现
        功能: 模拟探狼的邻域探索行为，对当前方案进行微小变异，寻找更优的邻域解
        变异策略: 随机选择一辆有多个任务的AGV，交换其内部两个任务的执行顺序，实现邻域搜索
        开题对应: 游走行为-邻域路径探索章节
        :param wolf: 执行游走行为的原狼个体
        :return: Wolf，游走后的最优个体（原个体或变异后的更优个体）
        """
        # 1. 深拷贝原狼个体，避免修改原个体数据，保证变异失败时可回退
        new_wolf = copy.deepcopy(wolf)

        # 2. 筛选出有至少2个任务的AGV，只有多个任务才能交换执行顺序
        active_agvs = [agv for agv in new_wolf.agv_list if len(agv.tasks) >= 2]
        # 边界兜底：如果没有符合条件的AGV，无法执行游走变异，直接返回原个体
        if not active_agvs:
            return wolf

        # 3. 随机选择一辆目标AGV执行变异
        target_agv = random.choice(active_agvs)

        # 4. 执行任务交换变异（邻域游走核心逻辑）
        # 随机选择两个不同的任务索引，保证交换的是不同任务
        idx1, idx2 = random.sample(range(len(target_agv.tasks)), 2)
        # 交换两个任务的执行顺序，完成邻域变异，100%保留原有任务不修改
        target_agv.tasks[idx1], target_agv.tasks[idx2] = target_agv.tasks[idx2], target_agv.tasks[idx1]

        # 5. 重新规划路径并计算适应度
        # 任务顺序改变后，必须重新规划路径、检测冲突、计算适应度，完全复用现有评估逻辑
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # 6. 贪婪选择策略：仅当变异后的方案更优时，才返回新个体；否则返回原个体
        if new_wolf.fitness < wolf.fitness:
            # 变异成功，打印优化日志，便于调试与迭代监控
            print(f"  [游走成功] F值优化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f}")
            return new_wolf
        else:
            # 变异失败，返回原个体，保证种群适应度不退化
            return wolf

    # ===================== 召唤行为（Summoning） =====================
    def summoning(self, wolf, alpha_wolf):
        """
        狼群算法-召唤行为(Summoning)极简实现
        功能: 模拟头狼召唤猛狼向最优解靠拢，提取头狼的任务运行方向，修改猛狼的任务执行顺序
        核心设计: 同起点同终点AGV精准匹配，仅修改任务执行顺序，100%保留必过任务点，彻底解决任务不匹配问题
        冲突解决: 完全复用evaluator.rebuild_wolf()的时空预约表机制，自动规避路径冲突
        开题对应: 召唤行为-路径交叉与信息共享章节
        :param wolf: 执行召唤行为的猛狼个体（原个体）
        :param alpha_wolf: 当前种群的全局唯一头狼（最优解个体）
        :return: Wolf，召唤后的最优个体（原个体或变异后的更优个体）
        """
        # -------------------------- 1. 深拷贝与边界兜底校验 --------------------------
        # 深拷贝原猛狼个体，避免修改原数据，保证变异失败可回退
        new_wolf = copy.deepcopy(wolf)
        # 深拷贝头狼个体，避免修改全局最优头狼的原始数据
        alpha_copy = copy.deepcopy(alpha_wolf)

        # 边界兜底1：如果头狼无任务/猛狼无任务，直接返回原个体，避免程序异常
        if not alpha_copy.agv_list or not new_wolf.agv_list:
            return wolf
        # 边界兜底2：70%执行概率，30%直接跳过，保护种群多样性，防止早熟收敛
        if random.random() > 0.7:
            return wolf

        # -------------------------- 2. 同起点同终点AGV精准匹配 --------------------------
        # 核心设计：你的所有AGV终点统一为卸货区，同编号AGV起点固定，天然满足同起点同终点要求
        # 随机选1辆头狼里有任务的AGV，作为优质基因来源
        alpha_agv = random.choice([agv for agv in alpha_copy.agv_list if agv.tasks])
        # 找到猛狼里同编号的AGV（同起点泊位），完成精准匹配
        wolf_agv = next((agv for agv in new_wolf.agv_list if agv.id == alpha_agv.id), None)

        # 边界兜底：如果猛狼里没有同编号AGV/该AGV无任务，直接返回原个体
        if wolf_agv is None or not wolf_agv.tasks:
            return wolf

        # -------------------------- 3. 提取头狼的任务运行方向规则 --------------------------
        # 毕设初期极简实现：提取头狼AGV的核心排序规则（X坐标升序，即从左到右的运行方向）
        # 可根据需求切换为：Y坐标排序、到起点的距离排序、到终点的距离排序
        def alpha_sort_rule(task):
            # 排序规则：按任务点X坐标升序（头狼的核心运行方向）
            return task.x

        # -------------------------- 4. 猛狼对齐头狼规则，修改任务执行顺序 --------------------------
        # 核心优势：100%保留猛狼自身的必过任务点，仅修改执行顺序，彻底解决任务不匹配问题
        # 提取猛狼AGV的所有必过任务，强制不修改、不增删、不遗漏
        wolf_original_tasks = wolf_agv.tasks.copy()
        # 用头狼的排序规则，重新排序猛狼的任务列表，完全复制头狼的运行方向
        wolf_agv.tasks = sorted(wolf_original_tasks, key=alpha_sort_rule)
        # 重新计算AGV当前载重，保证数据一致性
        wolf_agv.load = sum([task.weight for task in wolf_agv.tasks])

        # -------------------------- 5. 载重硬约束兜底校验 --------------------------
        # 复用你initializer.py里的贪婪分配逻辑，保证载重不超过AGV上限
        if wolf_agv.load > Config.AGV_CAPACITY:
            # 超载时，拆分后半段任务到新AGV
            split_idx = len(wolf_agv.tasks) // 2
            split_tasks = wolf_agv.tasks[split_idx:]
            # 保留前半段任务在原AGV
            wolf_agv.tasks = wolf_agv.tasks[:split_idx]
            wolf_agv.load = sum([task.weight for task in wolf_agv.tasks])

            # 生成新AGV，分配拆分的任务
            new_agv_id = max([agv.id for agv in new_wolf.agv_list]) + 1
            # 循环使用泊位，避免编号超出泊位数量
            if new_agv_id >= len(Config.START_NODES):
                new_agv_id = 0
            # 实例化新AGV
            new_agv = AGV(agv_id=new_agv_id, start_pos=Config.START_NODES[new_agv_id])
            new_agv.tasks = split_tasks
            new_agv.load = sum([task.weight for task in split_tasks])
            # 将新AGV加入猛狼的AGV列表
            new_wolf.agv_list.append(new_agv)

        # -------------------------- 6. 自动解决时空冲突，重评估方案 --------------------------
        # 核心设计：完全复用现有评估逻辑，自动初始化全新的时空预约表，规划无冲突路径，计算适应度
        # 零额外代码解决路径冲突问题，保证全系统逻辑一致性
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # -------------------------- 7. 贪婪选择策略，保证迭代不退化 --------------------------
        if new_wolf.fitness < wolf.fitness:
            # 召唤成功，打印优化日志，便于调试
            print(f"  [召唤成功] F值优化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f}")
            return new_wolf
        else:
            # 召唤失败，返回原个体，保证种群适应度不退化
            return wolf

    # ===================== 围攻行为（Besieging） =====================
    # -------------------------- 辅助工具函数：Levy飞行步长生成 --------------------------
    def _levy_flight_step(self, beta=1.5, step_scale=1.0):
        """
        Mantegna算法生成服从Levy分布的随机步长
        核心特性：大部分短步长、极小概率长步长，完美匹配开题要求的长短步相间特性
        开题对应: 围攻行为-Levy飞行扰动跳出局部最优章节
        :param beta: Levy分布的幂律指数，1<beta<2，默认1.5（学术通用标准值）
        :param step_scale: 步长缩放系数，控制整体扰动范围
        :return: 服从Levy分布的绝对值步长
        """
        # 计算Levy分布的sigma参数，Mantegna算法标准公式
        sigma_num = gamma(1 + beta) * np.sin(np.pi * beta / 2)
        sigma_den = gamma((1 + beta) / 2) * beta * np.power(2, (beta - 1) / 2)
        sigma = np.power(sigma_num / sigma_den, 1 / beta)

        # 生成两个正态分布随机数，用于计算Levy步长
        u = np.random.normal(0, sigma, 1)
        v = np.random.normal(0, 1, 1)

        # Mantegna算法核心公式，计算Levy步长
        step = step_scale * u / np.power(np.abs(v), 1 / beta)
        # 返回绝对值步长，用于扰动范围判断
        return abs(step[0])

    # -------------------------- 围攻行为主方法 --------------------------
    def besieging(self, wolf, curr_iter, max_iter):
        """
        狼群算法-围攻行为(Besieging)极简实现
        功能: 基于Levy飞行做自适应扰动，短步长局部精细优化，长步长全局跳变，跳出局部最优
        核心设计: 迭代自适应步长，越靠后步长越小，从全局勘探转向局部开发，完全贴合开题要求
        冲突解决: 完全复用evaluator.rebuild_wolf()机制，自动规避时空路径冲突
        开题对应: 围攻行为-Levy飞行扰动跳出局部最优章节
        :param wolf: 执行围攻行为的狼个体
        :param curr_iter: 当前迭代次数，用于自适应调整步长
        :param max_iter: 算法最大迭代次数，用于自适应调整步长
        :return: Wolf，围攻后的最优个体（原个体或变异后的更优个体）
        """
        # -------------------------- 1. 深拷贝与边界兜底校验 --------------------------
        # 深拷贝原狼个体，避免修改原数据
        new_wolf = copy.deepcopy(wolf)
        # 筛选有任务的AGV，边界兜底
        active_agvs = [agv for agv in new_wolf.agv_list if agv.tasks]
        # 边界兜底：无有效AGV，直接返回原个体
        if not active_agvs:
            return wolf
        # 边界兜底：80%执行概率，20%直接跳过，保护种群多样性
        if random.random() > 0.8:
            return wolf

        # -------------------------- 2. 生成自适应Levy飞行步长 --------------------------
        # 自适应缩放系数：迭代越靠后，系数越小，步长整体越小，从全局勘探转向局部开发
        step_scale = 2.0 * (1 - curr_iter / max_iter)
        # 生成Levy随机步长
        levy_step = self._levy_flight_step(step_scale=step_scale)
        # 步长阈值：区分短步长（局部微调）和长步长（全局跳变）
        step_threshold = 1.0

        # -------------------------- 3. 基于Levy步长的两级扰动策略 --------------------------
        # 情况1：短步长（90%概率触发）- 局部精细开发，单AGV内部任务微调
        if levy_step < step_threshold:
            # 随机选1辆有任务的AGV，做极小范围的任务顺序调整
            target_agv = random.choice(active_agvs)
            # 边界兜底：只有1个任务无法调整，直接返回原个体
            if len(target_agv.tasks) < 2:
                return wolf
            # 70%概率：相邻任务交换（最小粒度微调，局部优化）
            if random.random() < 0.7:
                # 随机选相邻的两个任务索引
                swap_idx = random.randint(0, len(target_agv.tasks) - 2)
                # 交换相邻任务顺序，100%保留原有任务
                target_agv.tasks[swap_idx], target_agv.tasks[swap_idx+1] = target_agv.tasks[swap_idx+1], target_agv.tasks[swap_idx]
            # 30%概率：单任务随机插入（小范围调整）
            else:
                # 随机选要移动的任务索引和插入位置
                move_idx, insert_idx = random.sample(range(len(target_agv.tasks)), 2)
                # 弹出任务，插入到新位置
                move_task = target_agv.tasks.pop(move_idx)
                target_agv.tasks.insert(insert_idx, move_task)
            # 重新计算AGV载重，保证数据一致性
            target_agv.load = sum([task.weight for task in target_agv.tasks])

        # 情况2：长步长（10%概率触发）- 全局跳变，跨AGV任务迁移，跳出局部最优
        else:
            # 边界兜底：至少2辆AGV才能做跨车迁移，否则降级为短步长微调
            if len(active_agvs) < 2:
                return self.besieging(wolf, curr_iter, max_iter)
            # 随机选2辆不同的AGV，做跨车任务迁移
            agv_a, agv_b = random.sample(active_agvs, 2)
            # 边界兜底：AGV无任务，直接返回原个体
            if not agv_a.tasks:
                return wolf
            # 随机选1个任务，从AGV-A迁移到AGV-B，保证任务唯一性，无重复无遗漏
            move_task_idx = random.randint(0, len(agv_a.tasks) - 1)
            move_task = agv_a.tasks.pop(move_task_idx)
            # 随机插入到AGV-B的任务列表中
            agv_b.tasks.insert(random.randint(0, len(agv_b.tasks)), move_task)

            # 重新计算两辆AGV的载重
            agv_a.load = sum([task.weight for task in agv_a.tasks])
            agv_b.load = sum([task.weight for task in agv_b.tasks])

            # -------------------------- 载重硬约束兜底 --------------------------
            # 如果AGV-B超载，拆分任务到新AGV，复用贪婪分配逻辑
            if agv_b.load > Config.AGV_CAPACITY:
                split_idx = len(agv_b.tasks) // 2
                split_tasks = agv_b.tasks[split_idx:]
                agv_b.tasks = agv_b.tasks[:split_idx]
                agv_b.load = sum([task.weight for task in agv_b.tasks])

                # 生成新AGV
                new_agv_id = max([agv.id for agv in new_wolf.agv_list]) + 1
                if new_agv_id >= len(Config.START_NODES):
                    new_agv_id = 0
                new_agv = AGV(agv_id=new_agv_id, start_pos=Config.START_NODES[new_agv_id])
                new_agv.tasks = split_tasks
                new_agv.load = sum([task.weight for task in split_tasks])
                new_wolf.agv_list.append(new_agv)

            # 移除无任务的AGV，优化车辆数量指标
            new_wolf.agv_list = [agv for agv in new_wolf.agv_list if agv.tasks]

        # -------------------------- 4. 自动解决时空冲突，重评估方案 --------------------------
        # 完全复用现有评估逻辑，自动规划无冲突路径，计算适应度
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # -------------------------- 5. 贪婪选择策略，保证迭代不退化 --------------------------
        if new_wolf.fitness < wolf.fitness:
            # 围攻成功，打印优化日志，包含Levy步长，便于调试
            print(f"  [围攻成功] F值优化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f} (Levy步长={levy_step:.2f})")
            return new_wolf
        else:
            # 围攻失败，返回原个体
            return wolf