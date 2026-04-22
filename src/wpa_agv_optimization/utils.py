"""
通用工具函数模块。

本模块只放“无状态纯函数”，便于复用与测试。
"""

import numpy as np
import random

from .config import Config


def tent_map_generate(n, x0=0.4):
    """
    生成长度为 n 的 Tent 混沌序列。

    参数：
    - n: 序列长度。
    - x0: 初始值（建议在 (0,1) 内）。

    返回：
    - list[float]，每个值在 [0,1] 范围附近。
    """
    # 创建结果容器。
    sequence = []
    # 初始化迭代值。
    x = x0
    # 循环生成 n 个混沌值。
    for _ in range(n):
        # Tent 映射的分段定义：x<0.5 时做线性放大。
        if x < 0.5:
            x = 2 * x
        # Tent 映射的另一段：x>=0.5 时做对称折返。
        else:
            x = 2 * (1 - x)
        # 记录本轮值。
        sequence.append(x)
    # 返回完整序列。
    return sequence



def generate_grid_map():
    """
    生成随机障碍地图。

    规则：
    - 0 表示可通行。
    - 1 表示障碍物。
    - 起始列与卸货点不放障碍。
    """
    # 先生成全 0 矩阵。
    grid = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
    # 遍历所有格子。
    for x in range(Config.MAP_WIDTH):
        for y in range(Config.MAP_HEIGHT):
            # 保护起始列和卸货点。
            if x == 0 or (x == Config.DEPOT_NODE[0] and y == Config.DEPOT_NODE[1]):
                continue
            # 按障碍比例随机置 1。
            if random.random() < Config.OBSTACLE_RATIO:
                grid[x][y] = 1
    # 返回地图。
    return grid


def manhattan_dist(start, end):
    """
    计算曼哈顿距离（四连通网格常用距离）。

    参数：
    - start: (x1, y1)
    - end: (x2, y2)
    """
    return abs(start[0] - end[0]) + abs(start[1] - end[1])


_NEIGHBOR_OFFSETS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def is_valid_pick_location(pos, obstacles):
    """任务合法落点：自身非障碍，且至少一个 4-邻居是障碍（货架）。"""
    if pos in obstacles:
        return False
    x, y = pos
    for dx, dy in _NEIGHBOR_OFFSETS:
        if (x + dx, y + dy) in obstacles:
            return True
    return False


def nearest_pick_location(pos, obstacles, grid_shape, max_radius=None):
    """返回离 pos 最近的合法 pick location；pos 本身合法则直接返回。

    BFS 扫描 Chebyshev 距离由小到大的候选格，用于把孤岛任务挪到最近货架邻接格。
    """
    width, height = grid_shape
    if max_radius is None:
        max_radius = max(width, height)

    if is_valid_pick_location(pos, obstacles):
        return pos

    x0, y0 = pos
    for radius in range(1, max_radius + 1):
        best = None
        best_manhattan = None
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                nx, ny = x0 + dx, y0 + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                cand = (nx, ny)
                if not is_valid_pick_location(cand, obstacles):
                    continue
                md = abs(dx) + abs(dy)
                if best is None or md < best_manhattan or (md == best_manhattan and cand < best):
                    best = cand
                    best_manhattan = md
        if best is not None:
            return best
    return None

