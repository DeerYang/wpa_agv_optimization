# initializer.py
import random
from config import Config
from models import Wolf, AGV
from utils import tent_map_generate, manhattan_dist
from evaluator import WolfEvaluator  # 【新增】引入评估器，复用逻辑


class PopulationInitializer:
    """
    种群初始化器类 (重构版)
    功能：只负责 "任务分配 (Allocation)" 策略，
         具体的 "路径规划 (Routing)" 和 "评分 (Scoring)" 委托给 Evaluator 处理。
    """

    def __init__(self, grid_map, task_list):
        self.grid_map = grid_map
        self.task_list = task_list
        # 【修改】不再直接实例化 Planner，而是实例化 Evaluator
        self.evaluator = WolfEvaluator(grid_map)

    def generate_population(self):
        population = []
        print(f"--- 正在使用 Tent-DFS (混沌导向深度搜索) 初始化 {Config.POP_SIZE} 只狼 ---")

        for i in range(Config.POP_SIZE):
            wolf = self._create_one_wolf()
            population.append(wolf)
            print(f"  > 生成第 {i + 1} 只狼: 耗用车辆 N={wolf.vehicle_num}, 适应度 F={wolf.fitness:.2f}")

        return population

    def _create_one_wolf(self):
        """
        创建单个个体
        """
        # ==========================================
        # Step 1: 基于 Tent 混沌映射的任务排序 (保持不变)
        # ==========================================
        x0_task = random.uniform(0.1, 0.9)
        chaos_seq_task = tent_map_generate(len(self.task_list), x0=x0_task)
        zipped = zip(self.task_list, chaos_seq_task)
        sorted_tasks = [t for t, c in sorted(zipped, key=lambda item: item[1])]

        # ==========================================
        # Step 2: 贪婪插入法分配任务 (保持不变)
        # ==========================================
        agv_list = []
        curr_agv_id = 0

        current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
        current_pos = current_agv.start_pos
        current_time = 0

        for task in sorted_tasks:
            # 简单估算
            dist = manhattan_dist(current_pos, (task.x, task.y))
            arrival_time = current_time + (dist / Config.AGV_SPEED)

            # 约束检查
            if (current_agv.load + task.weight > Config.AGV_CAPACITY) or \
                    (arrival_time > task.deadline):

                if current_agv.tasks:
                    agv_list.append(current_agv)

                curr_agv_id += 1
                if curr_agv_id >= len(Config.START_NODES): curr_agv_id = 0

                current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
                current_pos = current_agv.start_pos
                current_time = 0

            current_agv.tasks.append(task)
            current_agv.load += task.weight
            current_pos = (task.x, task.y)
            current_time += (manhattan_dist(current_pos, (task.x, task.y)) + Config.SERVICE_TIME)

        if current_agv.tasks:
            agv_list.append(current_agv)

        # ==========================================
        # Step 3 & 4: 委托给 Evaluator 处理 (核心修改)
        # ==========================================
        # 此时 wolf 只有 agv_list (含任务)，但 path 为空，fitness 为 0
        wolf = Wolf()
        wolf.agv_list = agv_list

        # 调用评估器：它会自动做 Tent-DFS 寻路、冲突处理、计算 N/D/T 和 Fitness
        # 这就是"代码复用"的魅力
        wolf = self.evaluator.rebuild_wolf(wolf)

        return wolf