# ===================== 文件级说明 =====================
# 文件名: scenario_inputs.py
# 功能: 固定基准场景输入库，用于不同算法实现之间的可复现实验对比
# 设计原则: 场景数据与算法逻辑解耦，统一从此文件读取输入，避免随机输入导致实验不可比
# ======================================================

from config import Config


def _base_obstacles():
    """构建基础障碍物布局（走廊+货架）"""
    obstacles = set()

    for y in range(1, Config.MAP_HEIGHT - 1):
        if y not in (3, 9, 15):
            obstacles.add((5, y))
        if y not in (6, 12):
            obstacles.add((10, y))
        if y not in (4, 10, 16):
            obstacles.add((14, y))

    for x in range(2, Config.MAP_WIDTH - 2):
        if x not in (5, 10, 14):
            obstacles.add((x, 7))
            obstacles.add((x, 13))

    # 保护出发列和卸货点
    obstacles = {
        (x, y)
        for (x, y) in obstacles
        if x != 0 and (x, y) != Config.DEPOT_NODE
    }
    return sorted(obstacles)


SCENARIO_LIBRARY = [
    {
        "name": "场景1-中等任务密度",
        "description": "10个任务，时间窗较宽，用于算法功能回归。",
        "obstacles": _base_obstacles(),
        "tasks": [
            {"x": 2, "y": 2, "weight": 18, "deadline": 140},
            {"x": 3, "y": 11, "weight": 25, "deadline": 180},
            {"x": 4, "y": 17, "weight": 20, "deadline": 210},
            {"x": 6, "y": 3, "weight": 16, "deadline": 120},
            {"x": 7, "y": 15, "weight": 28, "deadline": 230},
            {"x": 9, "y": 5, "weight": 14, "deadline": 160},
            {"x": 11, "y": 9, "weight": 32, "deadline": 240},
            {"x": 12, "y": 16, "weight": 22, "deadline": 260},
            {"x": 15, "y": 6, "weight": 26, "deadline": 200},
            {"x": 17, "y": 14, "weight": 30, "deadline": 280},
        ],
    },
    {
        "name": "场景2-标准对比场景",
        "description": "15个任务，时间窗中等，建议作为主要算法对比场景。",
        "obstacles": _base_obstacles(),
        "tasks": [
            {"x": 2, "y": 4, "weight": 18, "deadline": 110},
            {"x": 2, "y": 16, "weight": 24, "deadline": 170},
            {"x": 3, "y": 9, "weight": 15, "deadline": 130},
            {"x": 4, "y": 2, "weight": 20, "deadline": 100},
            {"x": 4, "y": 18, "weight": 25, "deadline": 190},
            {"x": 6, "y": 10, "weight": 12, "deadline": 150},
            {"x": 7, "y": 4, "weight": 30, "deadline": 160},
            {"x": 8, "y": 17, "weight": 21, "deadline": 220},
            {"x": 9, "y": 11, "weight": 28, "deadline": 210},
            {"x": 11, "y": 3, "weight": 14, "deadline": 140},
            {"x": 11, "y": 15, "weight": 27, "deadline": 240},
            {"x": 12, "y": 8, "weight": 16, "deadline": 170},
            {"x": 15, "y": 5, "weight": 33, "deadline": 250},
            {"x": 16, "y": 12, "weight": 19, "deadline": 230},
            {"x": 17, "y": 17, "weight": 26, "deadline": 280},
        ],
    },
    {
        "name": "场景3-高负载压力场景",
        "description": "20个任务，时间窗更紧，用于验证算法鲁棒性。",
        "obstacles": _base_obstacles(),
        "tasks": [
            {"x": 1, "y": 5, "weight": 14, "deadline": 90},
            {"x": 1, "y": 14, "weight": 18, "deadline": 120},
            {"x": 2, "y": 10, "weight": 20, "deadline": 110},
            {"x": 3, "y": 3, "weight": 16, "deadline": 100},
            {"x": 3, "y": 18, "weight": 22, "deadline": 150},
            {"x": 4, "y": 12, "weight": 24, "deadline": 140},
            {"x": 6, "y": 2, "weight": 19, "deadline": 130},
            {"x": 6, "y": 16, "weight": 27, "deadline": 170},
            {"x": 7, "y": 9, "weight": 15, "deadline": 115},
            {"x": 8, "y": 5, "weight": 29, "deadline": 160},
            {"x": 8, "y": 18, "weight": 17, "deadline": 180},
            {"x": 9, "y": 14, "weight": 21, "deadline": 175},
            {"x": 11, "y": 6, "weight": 23, "deadline": 150},
            {"x": 11, "y": 17, "weight": 18, "deadline": 200},
            {"x": 12, "y": 11, "weight": 31, "deadline": 210},
            {"x": 13, "y": 3, "weight": 26, "deadline": 170},
            {"x": 15, "y": 8, "weight": 20, "deadline": 220},
            {"x": 16, "y": 4, "weight": 25, "deadline": 230},
            {"x": 17, "y": 10, "weight": 22, "deadline": 240},
            {"x": 18, "y": 16, "weight": 28, "deadline": 260},
        ],
    },
]

