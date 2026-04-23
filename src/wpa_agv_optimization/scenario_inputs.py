"""固定场景输入库。"""

from .config import Config


def _finalize_obstacles(obstacles):
    obstacles = {(x, y) for (x, y) in obstacles if x != 0 and (x, y) != Config.DEPOT_NODE}
    return sorted(obstacles)


def _add_vertical_band(obstacles, xs, y_ranges):
    for x in xs:
        for y_start, y_end in y_ranges:
            for y in range(y_start, y_end + 1):
                obstacles.add((x, y))


def _add_horizontal_band(obstacles, ys, x_ranges):
    for y in ys:
        for x_start, x_end in x_ranges:
            for x in range(x_start, x_end + 1):
                obstacles.add((x, y))


def _open_island_obstacles():
    """小规模场景：多个分散拣选岛，通道开阔，绕行代价低。"""
    obstacles = set()
    _add_vertical_band(obstacles, (4, 5), ((3, 7),))
    _add_vertical_band(obstacles, (7, 8), ((16, 19),))
    _add_vertical_band(obstacles, (12, 13), ((6, 11),))
    _add_vertical_band(obstacles, (15, 16), ((20, 23),))
    _add_vertical_band(obstacles, (20, 21), ((4, 8),))
    _add_vertical_band(obstacles, (23, 24), ((14, 18),))
    _add_vertical_band(obstacles, (25, 26), ((22, 26),))
    return _finalize_obstacles(obstacles)


def _transfer_merge_obstacles():
    """中规模场景：左右货架区通过错位转运带相连，汇流明显。"""
    obstacles = set()
    _add_vertical_band(obstacles, (3, 4), ((2, 10),))
    _add_vertical_band(obstacles, (5, 6), ((14, 23),))
    _add_vertical_band(obstacles, (9, 10), ((4, 18),))
    _add_vertical_band(obstacles, (13, 14), ((2, 7), (10, 25)))
    _add_vertical_band(obstacles, (18, 19), ((5, 14), (17, 24)))
    _add_vertical_band(obstacles, (22, 23), ((3, 11), (15, 21)))
    _add_vertical_band(obstacles, (26, 27), ((12, 27),))
    _add_horizontal_band(obstacles, (12,), ((6, 8),))
    _add_horizontal_band(obstacles, (16,), ((14, 17),))
    _add_horizontal_band(obstacles, (20,), ((23, 25),))
    return _finalize_obstacles(obstacles)


def _deep_warehouse_obstacles():
    """大规模场景：深仓排架交错分布，窄通道多，回流压力强。"""
    obstacles = set()
    _add_vertical_band(obstacles, (2, 3), ((1, 6), (9, 27)))
    _add_vertical_band(obstacles, (6, 7), ((3, 14), (17, 26)))
    _add_vertical_band(obstacles, (10, 11), ((1, 8), (11, 21), (24, 27)))
    _add_vertical_band(obstacles, (14, 15), ((4, 10), (13, 27)))
    _add_vertical_band(obstacles, (18, 19), ((2, 7), (9, 17), (20, 26)))
    _add_vertical_band(obstacles, (22, 23), ((1, 12), (15, 24)))
    _add_vertical_band(obstacles, (26, 27), ((3, 9), (11, 27)))
    _add_vertical_band(obstacles, (5,), ((22, 24),))
    _add_vertical_band(obstacles, (12,), ((18, 20),))
    _add_vertical_band(obstacles, (17,), ((5, 6), (23, 24)))
    _add_vertical_band(obstacles, (24,), ((13, 14),))
    return _finalize_obstacles(obstacles)


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

    return _finalize_obstacles(obstacles)


SCENARIO_LIBRARY = [
    {
        "name": "场景1-岛式拣选小规模场景",
        "description": "30×30 开阔岛式布局，小批量任务分散在多个拣选岛周边，绕行空间充足。",
        "obstacles": _open_island_obstacles(),
        "tasks": [
            {"x": 3, "y": 4, "weight": 18, "deadline": 42},
            {"x": 6, "y": 6, "weight": 22, "deadline": 56},
            {"x": 6, "y": 17, "weight": 20, "deadline": 70},
            {"x": 9, "y": 18, "weight": 24, "deadline": 84},
            {"x": 11, "y": 8, "weight": 19, "deadline": 66},
            {"x": 14, "y": 10, "weight": 23, "deadline": 78},
            {"x": 14, "y": 21, "weight": 21, "deadline": 96},
            {"x": 17, "y": 22, "weight": 25, "deadline": 112},
            {"x": 19, "y": 6, "weight": 20, "deadline": 88},
            {"x": 22, "y": 16, "weight": 26, "deadline": 118},
            {"x": 24, "y": 24, "weight": 22, "deadline": 132},
        ],
    },
    {
        "name": "场景2-转运汇流中规模场景",
        "description": "30×30 转运汇流布局，左右货架区通过错位连通带衔接，中段会车与汇流持续出现。",
        "obstacles": _transfer_merge_obstacles(),
        "tasks": [
            {"x": 2, "y": 3, "weight": 18, "deadline": 22},
            {"x": 5, "y": 5, "weight": 24, "deadline": 30},
            {"x": 2, "y": 9, "weight": 20, "deadline": 36},
            {"x": 7, "y": 16, "weight": 26, "deadline": 48},
            {"x": 7, "y": 22, "weight": 28, "deadline": 60},
            {"x": 8, "y": 6, "weight": 19, "deadline": 34},
            {"x": 11, "y": 10, "weight": 22, "deadline": 42},
            {"x": 8, "y": 17, "weight": 23, "deadline": 54},
            {"x": 12, "y": 23, "weight": 27, "deadline": 70},
            {"x": 15, "y": 4, "weight": 21, "deadline": 38},
            {"x": 15, "y": 12, "weight": 24, "deadline": 50},
            {"x": 15, "y": 20, "weight": 26, "deadline": 66},
            {"x": 17, "y": 8, "weight": 20, "deadline": 46},
            {"x": 20, "y": 18, "weight": 25, "deadline": 72},
            {"x": 21, "y": 6, "weight": 22, "deadline": 58},
            {"x": 24, "y": 17, "weight": 27, "deadline": 84},
            {"x": 25, "y": 24, "weight": 24, "deadline": 96},
            {"x": 28, "y": 18, "weight": 29, "deadline": 108},
        ],
    },
    {
        "name": "场景3-深仓交错大规模场景",
        "description": "30×30 深仓交错布局，多层窄巷道与深货位叠加，回流、冲突与时间窗压力同时增大。",
        "obstacles": _deep_warehouse_obstacles(),
        "tasks": [
            {"x": 1, "y": 2, "weight": 20, "deadline": 18},
            {"x": 4, "y": 5, "weight": 28, "deadline": 24},
            {"x": 1, "y": 10, "weight": 18, "deadline": 34},
            {"x": 4, "y": 18, "weight": 24, "deadline": 44},
            {"x": 4, "y": 25, "weight": 26, "deadline": 56},
            {"x": 5, "y": 4, "weight": 22, "deadline": 30},
            {"x": 8, "y": 6, "weight": 21, "deadline": 38},
            {"x": 8, "y": 12, "weight": 23, "deadline": 48},
            {"x": 5, "y": 20, "weight": 25, "deadline": 60},
            {"x": 8, "y": 24, "weight": 27, "deadline": 72},
            {"x": 9, "y": 3, "weight": 19, "deadline": 34},
            {"x": 12, "y": 7, "weight": 24, "deadline": 44},
            {"x": 12, "y": 16, "weight": 22, "deadline": 56},
            {"x": 13, "y": 24, "weight": 28, "deadline": 70},
            {"x": 16, "y": 5, "weight": 20, "deadline": 40},
            {"x": 16, "y": 14, "weight": 26, "deadline": 54},
            {"x": 17, "y": 21, "weight": 30, "deadline": 68},
            {"x": 20, "y": 4, "weight": 21, "deadline": 46},
            {"x": 20, "y": 10, "weight": 24, "deadline": 58},
            {"x": 21, "y": 17, "weight": 27, "deadline": 72},
            {"x": 20, "y": 22, "weight": 29, "deadline": 86},
            {"x": 24, "y": 6, "weight": 23, "deadline": 62},
            {"x": 25, "y": 13, "weight": 25, "deadline": 76},
            {"x": 24, "y": 19, "weight": 28, "deadline": 90},
            {"x": 28, "y": 8, "weight": 24, "deadline": 82},
            {"x": 28, "y": 20, "weight": 29, "deadline": 104},
            {"x": 25, "y": 26, "weight": 27, "deadline": 116},
        ],
    },
    {
        "name": "场景4-极端时间窗补充场景",
        "description": "补充实验场景：重点放大时间窗压力，用于验证算法时序鲁棒性。",
        "obstacles": _corridor_obstacles(),
        "tasks": [
            {"x": 4, "y": 2, "weight": 18, "deadline": 4},
            {"x": 4, "y": 9, "weight": 17, "deadline": 12},
            {"x": 4, "y": 3, "weight": 24, "deadline": 10},
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
        "description": "补充实验场景：重点放大瓶颈通道冲突密度，用于验证算法协调鲁棒性。",
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
            {"x": 17, "y": 8, "weight": 21, "deadline": 118},
        ],
    },
]
