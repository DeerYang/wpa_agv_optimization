# ===================== 文件级说明 =====================
# 文件名: utils.py
# 功能: 系统通用工具函数集合，无业务耦合，纯功能函数，可复用性强
# 设计原则: 单一职责、无状态、纯函数设计，输入确定则输出确定，便于单元测试与复用
# 包含功能: Tent混沌映射生成、栅格地图生成、曼哈顿距离计算
# ======================================================

# 引入数值计算库，用于栅格地图矩阵生成
import numpy as np
# 引入随机数库，用于障碍物随机生成
import random
# 引入全局配置类，保证参数全局一致性
from config import Config


def tent_map_generate(n, x0=0.4):
    """
    Tent混沌映射序列生成器（核心创新点）
    功能: 基于Tent映射生成混沌序列，利用混沌序列的遍历性、随机性、规律性，提升算法全局搜索能力
    理论支撑: 对应开题报告中Tent混沌映射初始化、狼群算法改进策略，解决传统算法易陷入局部最优的问题
    数学公式:
        x_{k+1} = 2*x_k,           x_k < 0.5
        x_{k+1} = 2*(1 - x_k),     x_k >= 0.5
    :param n: 需要生成的混沌序列长度，通常等于任务数量或迭代步数
    :param x0: 混沌迭代初始值，范围(0,1)，初始值不同会生成完全不同的混沌序列，默认0.4
    :return: list，包含n个0~1之间的混沌数值的列表
    """
    # 初始化空列表，用于存储生成的混沌序列
    sequence = []
    # 设定混沌迭代初始值，启动迭代过程
    x = x0
    # 循环迭代n次，生成n个混沌数值
    for _ in range(n):
        # Tent映射核心公式计算，分段函数实现
        if x < 0.5:
            # 当x小于0.5时，执行2倍放大
            x = 2 * x
        else:
            # 当x大于等于0.5时，执行对称折叠
            x = 2 * (1 - x)
        # 将本次迭代生成的混沌值存入结果列表
        sequence.append(x)
    # 返回生成完成的混沌序列
    return sequence


def generate_grid_map():
    """
    带随机障碍物的栅格地图生成器
    功能: 基于全局配置生成仓储环境二维栅格地图，0代表可通行通道，1代表静态障碍物
    约束说明: 自动保护AGV出发区、卸货终点不生成障碍物，保证基础通行能力
    对应理论: 开题报告中栅格法仓储环境建模章节
    :return: numpy二维数组，shape为[MAP_WIDTH, MAP_HEIGHT]，元素为0(通道)或1(障碍物)
    """
    # 初始化全0二维矩阵，所有栅格默认可通行
    grid = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)
    # 遍历地图X轴所有栅格
    for x in range(Config.MAP_WIDTH):
        # 遍历地图Y轴所有栅格
        for y in range(Config.MAP_HEIGHT):
            # 保护机制：AGV出发区(最左列x=0)和卸货终点(右下角)禁止生成障碍物
            if x == 0 or (x == Config.DEPOT_NODE[0] and y == Config.DEPOT_NODE[1]):
                # 跳过本次循环，保持栅格为0(可通行)
                continue
            # 基于障碍物比例，随机生成静态障碍物
            if random.random() < Config.OBSTACLE_RATIO:
                # 将当前栅格标记为1(障碍物，不可通行)
                grid[x][y] = 1
    # 返回生成完成的栅格地图
    return grid


def manhattan_dist(start, end):
    """
    曼哈顿距离计算函数
    功能: 计算栅格地图中两个点之间的曼哈顿距离，用于路径规划的启发式估算、任务排序
    计算公式: 曼哈顿距离 = |x1 - x2| + |y1 - y2|，对应栅格地图中四方向移动的最少步数
    :param start: 起点坐标，元组格式(x1, y1)
    :param end: 终点坐标，元组格式(x2, y2)
    :return: int，两个点之间的曼哈顿距离，单位：栅格数
    """
    # 按曼哈顿距离公式计算并返回结果
    return abs(start[0] - end[0]) + abs(start[1] - end[1])