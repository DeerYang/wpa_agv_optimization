# ===================== 文件级说明 =====================
# 文件名: evaluator.py
# 功能: 狼群算法个体评估核心模块，负责调度方案的路径重构、冲突检测、适应度计算
# 设计模式: 单一职责原则，仅负责方案评估与重构，不负责方案生成，实现逻辑解耦与代码复用
# 核心能力: 多AGV顺序路径规划、时空冲突规避、多目标适应度计算、极端场景兜底机制
# 理论支撑: 对应开题报告中多目标优化函数、时空资源预约表、冲突检测机制
# ======================================================

# 引入全局配置类
from .config import Config
# 引入狼实体类
from .models import Wolf
# 引入Tent-DFS路径规划器
from .pathfinding import TentDFSPlanner
# 引入工具函数：栅格地图生成、曼哈顿距离计算
from .utils import tent_map_generate, manhattan_dist
# 引入随机数库，用于混沌序列初始值生成
import random


class WolfEvaluator:
    """
    狼群个体评估器
    职责: 给定仅完成任务分配的狼个体，为其规划无冲突路径、检测冲突、计算多目标适应度值，完成狼个体的完整重构
    设计说明: 全系统核心复用模块，初始化、游走、召唤、围攻等所有算子均调用该模块完成方案评估，保证评估逻辑全局一致
    """
    def __init__(self, grid_map):
        """
        评估器初始化方法
        :param grid_map: 全局静态栅格地图，用于初始化路径规划器
        """
        # 初始化Tent-DFS路径规划器，用于后续AGV路径规划
        self.planner = TentDFSPlanner(grid_map)

    def rebuild_wolf(self, wolf):
        """
        核心方法：狼个体重构与评估
        功能: 输入仅分配了任务的狼个体，完成全流程路径规划、冲突登记、指标计算、适应度评分
        执行流程: 初始化预约表 -> 生成混沌序列 -> 逐车规划路径 -> 登记资源占用 -> 计算全局指标 -> 计算适应度
        :param wolf: 待重构的狼个体，仅需包含agv_list与分配好的tasks，其他属性会被重写
        :return: Wolf，重构完成的狼个体，包含完整路径、所有评估指标、最终适应度
        """
        # ================ 初始化核心数据结构 ================
        # 全局时空资源预约表，set集合，存储所有AGV已占用的(x,y,t)时空节点，用于冲突检测与避障
        reservation_table = set()
        # 系统总行驶距离计数器，累加所有AGV的路径长度，对应优化目标D
        total_dist = 0
        # 系统总时间窗惩罚计数器，累加所有超时任务的惩罚时长，对应优化目标T
        total_time_penalty = 0

        # ================ 生成Tent混沌序列 ================
        # 每次重构都生成新的混沌序列，保证路径规划的多样性，避免每次规划路径完全一致
        # 生成0~1之间的随机初始值，保证混沌序列的随机性
        x0 = random.random()
        # 生成长度5000的混沌序列，满足单台AGV路径规划的迭代需求
        chaos_seq = tent_map_generate(n=5000, x0=x0)
        # 转换为迭代器，便于路径规划器逐次获取混沌值
        chaos_iter = iter(chaos_seq)

        # ================ 逐车顺序路径规划（核心逻辑） ================
        # 采用顺序规划策略，按AGV列表顺序依次规划，后规划的车辆避让先规划的车辆，保证无冲突
        for agv in wolf.agv_list:
            # 初始化AGV当前位置为初始停泊位置
            curr_pos = agv.start_pos
            # 初始化AGV当前时间为0，从0时刻开始执行任务
            curr_time = 0
            # 初始化AGV完整时空路径列表
            full_path = []

            # 构建AGV的目标点执行链：先按顺序执行所有取货任务，最后到达统一卸货区
            # 提取所有任务的坐标，作为路径规划的中间目标点
            targets = [(t.x, t.y) for t in agv.tasks]
            # 只有分配了任务的AGV，才需要在最后前往卸货区完成交付
            if agv.tasks:
                targets.append(Config.DEPOT_NODE)

            # 遍历目标点链，逐段规划路径
            for target_pos in targets:
                # 调用Tent-DFS规划器，规划当前位置到目标点的无冲突路径
                # 传入参数：起点、终点、出发时间、全局预约表、混沌序列迭代器
                segment_path = self.planner.plan(curr_pos, target_pos, curr_time, reservation_table, chaos_iter)

                # ---------------- 极端场景兜底机制 ----------------
                # 如果规划器返回None，说明当前路径被完全堵死，无可行路径
                if segment_path is None:
                    # 施加巨额惩罚，让该方案在种群竞争中被淘汰
                    total_time_penalty += 10000
                    # 生成虚拟瞬移路径，保证程序不崩溃，仅用于兜底
                    segment_path = [(target_pos[0], target_pos[1], curr_time + 10)]

                # ---------------- 路径拼接 ----------------
                # 如果不是第一段路径，跳过起点（与上一段路径的终点重复），避免路径重复
                if full_path:
                    full_path.extend(segment_path[1:])
                # 如果是第一段路径，直接完整拼接
                else:
                    full_path.extend(segment_path)

                # ---------------- 状态更新 ----------------
                # 获取本段路径的最后一个节点，作为下一段路径的起点
                last_node = segment_path[-1]
                # 更新当前位置为本段路径的终点坐标
                curr_pos = (last_node[0], last_node[1])
                # 更新当前时间：到达终点的时间 + 装卸货耗时，装卸货期间AGV停留在当前节点
                curr_time = last_node[2] + Config.SERVICE_TIME

                # ---------------- 时空资源预约登记 ----------------
                # 将本段路径的所有时空节点登记到全局预约表，后续AGV需避让这些节点
                for p in segment_path:
                    reservation_table.add(p)
                # 登记装卸货期间的节点占用：装卸货的SERVICE_TIME秒内，AGV持续占用当前节点
                for t_wait in range(1, Config.SERVICE_TIME + 1):
                    reservation_table.add((p[0], p[1], p[2] + t_wait))

            # ================ 单台AGV数据更新 ================
            # 将规划完成的完整路径赋值给AGV对象
            agv.path = full_path
            # 将完成所有任务的最终时间赋值给AGV对象
            agv.finish_time = curr_time
            # 累加该AGV的路径长度到系统总行驶距离
            total_dist += len(full_path)

            # ================ 时间窗惩罚计算 ================
            # 只有分配了任务的AGV才需要计算时间窗惩罚
            if agv.tasks:
                # 获取该AGV最后一个任务的截止时间，作为整体时间窗约束
                last_deadline = agv.tasks[-1].deadline
                # 如果完成时间超过截止时间，计算超时时长并累加到总惩罚
                if curr_time > last_deadline:
                    total_time_penalty += (curr_time - last_deadline)

        # ================ 狼个体全局属性更新 ================
        # 赋值系统总行驶距离
        wolf.total_dist = total_dist
        # 赋值系统总时间窗惩罚
        wolf.time_penalty = total_time_penalty
        # 统计实际使用的AGV数量：仅统计有任务分配的车辆，对应优化目标N
        wolf.vehicle_num = len([agv for agv in wolf.agv_list if agv.tasks])

        # ================ 多目标适应度计算 ================
        # 严格按照开题报告中的加权目标函数计算：F = w1·D + w2·N + w3·T
        # 适应度值越小，代表调度方案越优
        wolf.fitness = (Config.W1_DIST * total_dist) + \
                       (Config.W2_NUM * wolf.vehicle_num) + \
                       (Config.W3_TIME * total_time_penalty)

        # 返回重构完成、评估完毕的狼个体
        return wolf
