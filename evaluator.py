# evaluator.py
from config import Config
from models import Wolf
from pathfinding import TentDFSPlanner
from utils import tent_map_generate, manhattan_dist
import random


class WolfEvaluator:
    """
    狼群评估器：负责"重构"一只狼
    即：给定任务分配方案，重新规划所有路径，并计算 F 值
    """

    def __init__(self, grid_map):
        self.planner = TentDFSPlanner(grid_map)

    def rebuild_wolf(self, wolf):
        """
        核心函数：传入一只只分配了任务(Tasks)但路径未定的狼，
        为其规划路径、检测冲突、计算适应度。
        """
        reservation_table = set()
        total_dist = 0
        total_time_penalty = 0

        # 为了游走的多样性，每次重构都生成新的 Tent 序列
        x0 = random.random()
        chaos_seq = tent_map_generate(n=5000, x0=x0)
        chaos_iter = iter(chaos_seq)

        # 依次为每辆 AGV 规划路径 (顺序规划策略)
        for agv in wolf.agv_list:
            curr_pos = agv.start_pos
            curr_time = 0
            full_path = []

            # 构建目标链：任务点 -> 卸货区
            targets = [(t.x, t.y) for t in agv.tasks]
            if agv.tasks:  # 只有有任务的车才需要去卸货区
                targets.append(Config.DEPOT_NODE)

            for target_pos in targets:
                # 调用 Tent-DFS 寻路
                segment_path = self.planner.plan(curr_pos, target_pos, curr_time, reservation_table, chaos_iter)

                if segment_path is None:
                    # 兜底机制：如果堵死，给重罚并瞬移
                    total_time_penalty += 10000
                    # 虚拟路径
                    segment_path = [(target_pos[0], target_pos[1], curr_time + 10)]

                    # 拼接路径
                if full_path:
                    full_path.extend(segment_path[1:])
                else:
                    full_path.extend(segment_path)

                last_node = segment_path[-1]
                curr_pos = (last_node[0], last_node[1])
                curr_time = last_node[2] + Config.SERVICE_TIME

                # 登记占用
                for p in segment_path:
                    reservation_table.add(p)
                for t_wait in range(1, Config.SERVICE_TIME + 1):
                    reservation_table.add((p[0], p[1], p[2] + t_wait))

            # 更新 AGV 数据
            agv.path = full_path
            agv.finish_time = curr_time
            total_dist += len(full_path)

            # 软时间窗罚分
            last_deadline = agv.tasks[-1].deadline if agv.tasks else 0
            if curr_time > last_deadline:
                total_time_penalty += (curr_time - last_deadline)

        # 更新狼的属性
        wolf.total_dist = total_dist
        wolf.time_penalty = total_time_penalty
        wolf.vehicle_num = len([agv for agv in wolf.agv_list if agv.tasks])  # 只统计干活的车

        # 计算 F 值
        wolf.fitness = (Config.W1_DIST * total_dist) + \
                       (Config.W2_NUM * wolf.vehicle_num) + \
                       (Config.W3_TIME * total_time_penalty)
        return wolf