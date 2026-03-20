import random

from .config import Config
from .evaluator import WolfEvaluator
from .models import AGV, Wolf
from .utils import manhattan_dist, tent_map_generate


class PopulationInitializer:
    """Initial population builder."""

    def __init__(self, grid_map, task_list):
        self.grid_map = grid_map
        self.task_list = task_list
        self.evaluator = WolfEvaluator(grid_map)

    def generate_population(self):
        """Generate the initial wolf population."""
        population = []
        print(f"--- 正在使用 Tent-DFS 初始化 {Config.POP_SIZE} 只狼 ---")
        for i in range(Config.POP_SIZE):
            wolf = self._create_one_wolf()
            population.append(wolf)
            print(f"  > 生成第 {i + 1} 只狼: 使用车辆 N={wolf.vehicle_num}, 适应度 F={wolf.fitness:.2f}")
        return population

    def _open_next_agv(self, curr_agv_id):
        """Open the next AGV slot used by greedy initialization."""
        curr_agv_id += 1
        if curr_agv_id >= len(Config.START_NODES):
            curr_agv_id = 0
        return curr_agv_id, AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])

    def _create_one_wolf(self):
        """Create one initial wolf by Tent order plus greedy assignment."""
        x0_task = random.uniform(0.1, 0.9)
        chaos_seq_task = tent_map_generate(len(self.task_list), x0=x0_task)
        sorted_tasks = [task for task, _ in sorted(zip(self.task_list, chaos_seq_task), key=lambda item: item[1])]

        agv_list = []
        curr_agv_id = 0
        current_agv = AGV(agv_id=curr_agv_id, start_pos=Config.START_NODES[curr_agv_id])
        current_pos = current_agv.start_pos
        current_time = 0.0

        for task in sorted_tasks:
            task_pos = (task.x, task.y)
            travel_dist = manhattan_dist(current_pos, task_pos)
            arrival_time = current_time + (travel_dist / Config.AGV_SPEED)

            if (current_agv.load + task.weight > Config.AGV_CAPACITY) or (arrival_time > task.deadline):
                if current_agv.tasks:
                    agv_list.append(current_agv)
                curr_agv_id, current_agv = self._open_next_agv(curr_agv_id)
                current_pos = current_agv.start_pos
                current_time = 0.0
                travel_dist = manhattan_dist(current_pos, task_pos)
                arrival_time = current_time + (travel_dist / Config.AGV_SPEED)

            current_agv.tasks.append(task)
            current_agv.load += task.weight
            current_time = arrival_time + Config.SERVICE_TIME
            current_pos = task_pos

        if current_agv.tasks:
            agv_list.append(current_agv)

        wolf = Wolf()
        wolf.agv_list = agv_list
        return self.evaluator.rebuild_wolf(wolf)
