"""固定场景输入库。"""

from .config import Config


def _corridor_obstacles():
    """构造多走廊瓶颈地图。"""
    obstacles = set()

    for y in range(1, Config.MAP_HEIGHT - 1):
        if y not in (4, 10, 15):
            obstacles.add((5, y))
        if y not in (6, 12):
            obstacles.add((10, y))
        if y not in (5, 9, 16):
            obstacles.add((14, y))

    for x in range(2, Config.MAP_WIDTH - 2):
        if x not in (5, 10, 14):
            obstacles.add((x, 7))
            obstacles.add((x, 13))

    obstacles = {(x, y) for (x, y) in obstacles if x != 0 and (x, y) != Config.DEPOT_NODE}
    return sorted(obstacles)


SCENARIO_LIBRARY = [
    {
        "name": "场景1-综合小规模场景",
        "description": "小规模综合压力场景，同时包含临界载重、紧时间窗与瓶颈通道冲突。",
        "obstacles": _corridor_obstacles(),
        "tasks": [
            {"x": 2, "y": 2, "weight": 33, "deadline": 4},
            {"x": 2, "y": 15, "weight": 28, "deadline": 60},
            {"x": 4, "y": 6, "weight": 27, "deadline": 42},
            {"x": 4, "y": 12, "weight": 24, "deadline": 70},
            {"x": 6, "y": 4, "weight": 31, "deadline": 11},
            {"x": 7, "y": 16, "weight": 34, "deadline": 36},
            {"x": 9, "y": 10, "weight": 29, "deadline": 30},
            {"x": 11, "y": 8, "weight": 26, "deadline": 100},
            {"x": 13, "y": 12, "weight": 25, "deadline": 120},
            {"x": 16, "y": 15, "weight": 28, "deadline": 45},
        ],
    },
    {
        "name": "场景2-综合中规模场景",
        "description": "中规模综合压力场景，载重、时间窗和通道冲突同时增强。",
        "obstacles": _corridor_obstacles(),
        "tasks": [
            {"x": 2, "y": 2, "weight": 21, "deadline": 5},
            {"x": 2, "y": 16, "weight": 24, "deadline": 20},
            {"x": 3, "y": 10, "weight": 18, "deadline": 16},
            {"x": 4, "y": 4, "weight": 27, "deadline": 20},
            {"x": 4, "y": 18, "weight": 23, "deadline": 30},
            {"x": 5, "y": 10, "weight": 16, "deadline": 36},
            {"x": 6, "y": 6, "weight": 26, "deadline": 45},
            {"x": 6, "y": 12, "weight": 24, "deadline": 32},
            {"x": 8, "y": 6, "weight": 19, "deadline": 54},
            {"x": 9, "y": 10, "weight": 28, "deadline": 50},
            {"x": 10, "y": 12, "weight": 22, "deadline": 84},
            {"x": 11, "y": 8, "weight": 17, "deadline": 78},
            {"x": 13, "y": 6, "weight": 25, "deadline": 28},
            {"x": 15, "y": 12, "weight": 21, "deadline": 105},
            {"x": 17, "y": 16, "weight": 24, "deadline": 125},
        ],
    },
    {
        "name": "场景3-综合大规模场景",
        "description": "大规模综合压力场景，在高负载下进一步提升时间窗与瓶颈冲突密度。",
        "obstacles": _corridor_obstacles(),
        "tasks": [
            {"x": 2, "y": 2, "weight": 22, "deadline": 8},
            {"x": 2, "y": 16, "weight": 26, "deadline": 32},
            {"x": 3, "y": 10, "weight": 18, "deadline": 14},
            {"x": 4, "y": 4, "weight": 29, "deadline": 22},
            {"x": 4, "y": 6, "weight": 24, "deadline": 34},
            {"x": 4, "y": 12, "weight": 23, "deadline": 38},
            {"x": 5, "y": 10, "weight": 17, "deadline": 30},
            {"x": 6, "y": 6, "weight": 28, "deadline": 40},
            {"x": 6, "y": 12, "weight": 26, "deadline": 40},
            {"x": 8, "y": 6, "weight": 21, "deadline": 50},
            {"x": 8, "y": 14, "weight": 19, "deadline": 45},
            {"x": 9, "y": 10, "weight": 30, "deadline": 30},
            {"x": 10, "y": 12, "weight": 24, "deadline": 34},
            {"x": 11, "y": 8, "weight": 18, "deadline": 55},
            {"x": 11, "y": 14, "weight": 20, "deadline": 70},
            {"x": 13, "y": 6, "weight": 27, "deadline": 82},
            {"x": 13, "y": 12, "weight": 25, "deadline": 40},
            {"x": 15, "y": 8, "weight": 26, "deadline": 104},
            {"x": 15, "y": 14, "weight": 22, "deadline": 118},
            {"x": 17, "y": 9, "weight": 25, "deadline": 122},
        ],
    },
    {
        "name": "场景4-极端时间窗补充场景",
        "description": "补充实验场景：重点放大时间窗压力，用于验证算法时序鲁棒性。",
        "obstacles": _corridor_obstacles(),
        "tasks": [
            {"x": 2, "y": 2, "weight": 18, "deadline": 4},
            {"x": 3, "y": 10, "weight": 17, "deadline": 12},
            {"x": 4, "y": 4, "weight": 24, "deadline": 10},
            {"x": 4, "y": 18, "weight": 20, "deadline": 22},
            {"x": 5, "y": 10, "weight": 16, "deadline": 18},
            {"x": 6, "y": 6, "weight": 25, "deadline": 24},
            {"x": 6, "y": 12, "weight": 23, "deadline": 26},
            {"x": 8, "y": 6, "weight": 19, "deadline": 32},
            {"x": 9, "y": 10, "weight": 27, "deadline": 28},
            {"x": 11, "y": 8, "weight": 17, "deadline": 36},
            {"x": 13, "y": 6, "weight": 22, "deadline": 40},
            {"x": 15, "y": 12, "weight": 20, "deadline": 50},
        ],
    },
    {
        "name": "场景5-极端冲突补充场景",
        "description": "补充实验场景：重点放大时间窗压力，用于验证算法时序鲁棒性。????",
        "obstacles": _corridor_obstacles(),
        "tasks": [
            {"x": 4, "y": 6, "weight": 18, "deadline": 60},
            {"x": 4, "y": 12, "weight": 18, "deadline": 62},
            {"x": 5, "y": 10, "weight": 16, "deadline": 58},
            {"x": 6, "y": 6, "weight": 22, "deadline": 70},
            {"x": 6, "y": 12, "weight": 22, "deadline": 72},
            {"x": 8, "y": 6, "weight": 20, "deadline": 78},
            {"x": 8, "y": 14, "weight": 19, "deadline": 82},
            {"x": 9, "y": 10, "weight": 24, "deadline": 74},
            {"x": 10, "y": 12, "weight": 21, "deadline": 88},
            {"x": 11, "y": 8, "weight": 17, "deadline": 90},
            {"x": 11, "y": 14, "weight": 17, "deadline": 94},
            {"x": 13, "y": 6, "weight": 22, "deadline": 96},
            {"x": 13, "y": 12, "weight": 22, "deadline": 98},
            {"x": 15, "y": 8, "weight": 23, "deadline": 108},
            {"x": 15, "y": 14, "weight": 20, "deadline": 112},
            {"x": 17, "y": 9, "weight": 21, "deadline": 118},
        ],
    },
]
