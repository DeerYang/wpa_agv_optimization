"""
种群初始化模块。

职责：
- 只负责生成初始任务分配方案。
- 路径规划与适应度计算统一交给 evaluator，保证全流程评估口径一致。
"""

import random

from .config import Config
from .evaluator import WolfEvaluator
from .models import AGV, Wolf
from .utils import manhattan_dist, tent_map_generate


class PopulationInitializer:
    """初始种群生成器。"""

    def __init__(self, grid_map, task_list):
        # 保存地图。
        self.grid_map = grid_map
        # 保存任务列表。
        self.task_list = task_list
        # 初始化统一评估器。
        self.evaluator = WolfEvaluator(grid_map)

    def generate_population(self):
        """按 Config.POP_SIZE 生成初始种群。"""
        population = []
        print(f"--- 正在使用 Tent-DFS (混沌导向深度搜索) 初始化 {Config.POP_SIZE} 只狼 ---")
        for i in range(Config.POP_SIZE):
            wolf = self._create_one_wolf()
            population.append(wolf)
            print(f"  > 生成第 {i + 1} 只狼: 耗用车辆 N={wolf.vehicle_num}, 适应度 F={wolf.fitness:.2f}")
        return population

    def _create_one_wolf(self):
        """
        生成单个狼个体。

        步骤：
        1) 用 Tent 序列打散任务顺序。
        2) 用贪婪规则把任务分配到 AGV。
        3) 调 evaluator 重建路径并计算评分。
        """
        # 生成本轮任务排序的混沌序列。
        x0_task = random.uniform(0.1, 0.9)
        chaos_seq_task = tent_map_generate(len(self.task_list), x0=x0_task)
        zipped = zip(self.task_list, chaos_seq_task)
        sorted_tasks = [t for t, c in sorted(zipped, key=lambda item: item[1])]

        # 初始化 AGV 分配过程状态。
        agv_list = []
        curr_agv_id = 0
        current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
        current_pos = current_agv.start_pos
        current_time = 0

        # 逐任务分配。
        for task in sorted_tasks:
            dist = manhattan_dist(current_pos, (task.x, task.y))
            arrival_time = current_time + (dist / Config.AGV_SPEED)

            # 若超载或超时，则切换到下一辆车。
            if (current_agv.load + task.weight > Config.AGV_CAPACITY) or (arrival_time > task.deadline):
                if current_agv.tasks:
                    agv_list.append(current_agv)
                curr_agv_id += 1
                if curr_agv_id >= len(Config.START_NODES):
                    curr_agv_id = 0
                current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
                current_pos = current_agv.start_pos
                current_time = 0

            # 分配当前任务。
            current_agv.tasks.append(task)
            current_agv.load += task.weight
            current_pos = (task.x, task.y)
            # 注意：这里保留原逻辑的时间更新方式，不改变行为。
            current_time += (manhattan_dist(current_pos, (task.x, task.y)) + Config.SERVICE_TIME)

        # 收尾：最后一辆有任务的车加入列表。
        if current_agv.tasks:
            agv_list.append(current_agv)

        # 封装为 wolf 并统一评估。
        wolf = Wolf()
        wolf.agv_list = agv_list
        wolf = self.evaluator.rebuild_wolf(wolf)
        return wolf

