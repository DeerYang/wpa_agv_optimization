# ===================== 文件级说明 =====================
# 文件名: initializer.py
# 功能: 狼群算法种群初始化模块，负责生成初始可行解种群
# 设计原则: 职责分离，仅负责任务分配策略，路径规划与评估完全委托给Evaluator，实现代码复用
# 核心策略: Tent混沌映射任务排序、贪婪插入法任务分配，保证初始种群的多样性与可行性
# 理论支撑: 对应开题报告中狼群初始化与路径编码、Tent混沌映射改进策略
# ======================================================

# 引入随机数库，用于混沌序列初始值生成
import random
# 引入全局配置类
from config import Config
# 引入狼实体类、AGV实体类
from models import Wolf, AGV
# 引入工具函数：Tent混沌映射生成、曼哈顿距离计算
from utils import tent_map_generate, manhattan_dist
# 引入狼评估器，复用路径规划与评估逻辑
from evaluator import WolfEvaluator


class PopulationInitializer:
    """
    种群初始化器（重构版）
    职责: 生成狼群算法的初始种群，每个个体为一套可行的多AGV调度方案
    设计思路: 拆分"任务分配"与"路径规划"两个环节，本类仅负责任务分配策略，路径规划与评估完全委托给Evaluator
    核心优势: 代码高度复用，初始化逻辑与后续迭代的评估逻辑完全一致，保证算法一致性
    """
    def __init__(self, grid_map, task_list):
        """
        初始化器构造方法
        :param grid_map: 全局静态栅格地图
        :param task_list: 全局待执行的取货任务列表，每个元素为Task实体对象
        """
        # 存储全局栅格地图
        self.grid_map = grid_map
        # 存储全局待分配任务列表
        self.task_list = task_list
        # 实例化狼评估器，用于后续方案的路径规划与适应度计算
        self.evaluator = WolfEvaluator(grid_map)

    def generate_population(self):
        """
        生成完整初始种群的入口方法
        功能: 按配置的种群规模，生成指定数量的狼个体，组成初始种群
        :return: list，包含POP_SIZE个狼个体的种群列表
        """
        # 初始化种群空列表
        population = []
        # 打印初始化日志，便于监控进度
        print(f"--- 正在使用 Tent-DFS (混沌导向深度搜索) 初始化 {Config.POP_SIZE} 只狼 ---")
        # 循环生成POP_SIZE个狼个体
        for i in range(Config.POP_SIZE):
            # 调用内部方法，生成单个狼个体
            wolf = self._create_one_wolf()
            # 将生成的狼个体加入种群
            population.append(wolf)
            # 打印单只狼的生成结果，便于调试与监控
            print(f"  > 生成第 {i + 1} 只狼: 耗用车辆 N={wolf.vehicle_num}, 适应度 F={wolf.fitness:.2f}")
        # 返回生成完成的初始种群
        return population

    def _create_one_wolf(self):
        """
        内部方法：创建单个狼个体（单个可行调度方案）
        执行流程: 混沌映射任务排序 -> 贪婪插入法任务分配 -> 委托评估器完成路径规划与适应度计算
        :return: Wolf，完整的、评估完成的狼个体
        """
        # ================ Step1: 基于Tent混沌映射的任务排序 ================
        # 设计目的: 利用混沌序列的遍历性，让每个狼个体的任务排序不同，保证初始种群的多样性
        # 生成0.1~0.9之间的随机初始值，避免混沌序列收敛到0或1
        x0_task = random.uniform(0.1, 0.9)
        # 生成与任务数量等长的混沌序列
        chaos_seq_task = tent_map_generate(len(self.task_list), x0=x0_task)
        # 将任务与混沌值一一配对
        zipped = zip(self.task_list, chaos_seq_task)
        # 按混沌值从小到大对任务进行排序，得到随机且遍历性强的任务执行顺序
        sorted_tasks = [t for t, c in sorted(zipped, key=lambda item: item[1])]

        # ================ Step2: 贪婪插入法任务分配 ================
        # 设计目的: 按排序后的任务顺序，为AGV分配任务，满足载重与时间窗硬约束
        # 初始化AGV列表，存储分配了任务的AGV对象
        agv_list = []
        # 初始化当前AGV编号，从0开始
        curr_agv_id = 0
        # 实例化当前操作的AGV对象，分配对应的初始泊位
        current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
        # 初始化当前AGV的当前位置为初始泊位
        current_pos = current_agv.start_pos
        # 初始化当前AGV的当前时间为0
        current_time = 0

        # 遍历排序后的所有任务，逐一分配
        for task in sorted_tasks:
            # 估算当前AGV从当前位置到任务点的曼哈顿距离
            dist = manhattan_dist(current_pos, (task.x, task.y))
            # 估算AGV到达任务点的时间
            arrival_time = current_time + (dist / Config.AGV_SPEED)

            # ---------------- 硬约束校验 ----------------
            # 校验1: 加入该任务后，AGV载重是否超过最大容量
            # 校验2: 到达任务点的时间是否超过任务的截止时间
            if (current_agv.load + task.weight > Config.AGV_CAPACITY) or \
                    (arrival_time > task.deadline):
                # 约束不满足，无法将该任务分配给当前AGV
                # 如果当前AGV已有任务，将其加入AGV列表
                if current_agv.tasks:
                    agv_list.append(current_agv)
                # 生成新的AGV编号，循环使用泊位
                curr_agv_id += 1
                # 如果编号超过泊位数量，重置为0，循环使用
                if curr_agv_id >= len(Config.START_NODES):
                    curr_agv_id = 0
                # 实例化新的AGV对象
                current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
                # 重置当前位置为新AGV的初始泊位
                current_pos = current_agv.start_pos
                # 重置当前时间为0
                current_time = 0

            # ---------------- 任务分配 ----------------
            # 将该任务加入当前AGV的任务列表
            current_agv.tasks.append(task)
            # 累加当前AGV的载重
            current_agv.load += task.weight
            # 更新当前位置为任务点坐标
            current_pos = (task.x, task.y)
            # 更新当前时间：行驶时间 + 装卸货时间
            current_time += (manhattan_dist(current_pos, (task.x, task.y)) + Config.SERVICE_TIME)

        # 循环结束后，将最后一辆有任务的AGV加入列表
        if current_agv.tasks:
            agv_list.append(current_agv)

        # ================ Step3&4: 委托评估器完成重构与评估 ================
        # 实例化狼个体
        wolf = Wolf()
        # 将分配好任务的AGV列表赋值给狼个体
        wolf.agv_list = agv_list
        # 调用评估器，完成路径规划、冲突检测、适应度计算
        wolf = self.evaluator.rebuild_wolf(wolf)

        # 返回生成完成的狼个体
        return wolf