# utils.py
import numpy as np
import random
from config import Config


def tent_map_generate(n, x0=0.4):
    """
    [核心创新点] Tent 混沌映射生成器
    :param n: 需要生成的序列长度 (通常等于任务数量)
    :param x0: 初始迭代值 (0 < x0 < 1)
    :return: 包含 n 个混沌数值的列表
    """
    sequence = []  # 初始化结果列表
    x = x0  # 设定初始值

    for _ in range(n):
        # Tent 映射公式实现
        if x < 0.5:
            x = 2 * x
        else:
            x = 2 * (1 - x)
        sequence.append(x)  # 将本次迭代结果存入列表

    return sequence


def generate_grid_map():
    """
    生成一个带随机障碍物的栅格地图
    :return: 二维 numpy 数组 (0:通道, 1:障碍物)
    """
    # 初始化全 0 矩阵
    grid = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)

    for x in range(Config.MAP_WIDTH):
        for y in range(Config.MAP_HEIGHT):
            # 保护机制：起点区域(最左列)和终点(右下角)不能生成障碍物
            if x == 0 or (x == Config.DEPOT_NODE[0] and y == Config.DEPOT_NODE[1]):
                continue

            # 根据设定的比例随机生成障碍物
            if random.random() < Config.OBSTACLE_RATIO:
                grid[x][y] = 1  # 标记为障碍物

    return grid


def manhattan_dist(start, end):
    """
    计算曼哈顿距离 (用于启发式估算)
    :param start: (x1, y1)
    :param end: (x2, y2)
    :return: |x1-x2| + |y1-y2|
    """
    return abs(start[0] - end[0]) + abs(start[1] - end[1])