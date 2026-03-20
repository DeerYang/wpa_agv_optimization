"""全局配置模块。"""


class Config:
    """Project-wide static configuration."""

    # ===================== 地图与环境参数 =====================
    MAP_WIDTH = 20
    MAP_HEIGHT = 20
    OBSTACLE_RATIO = 0.1

    # ===================== AGV 物理参数 =====================
    AGV_CAPACITY = 100
    AGV_SPEED = 1
    SERVICE_TIME = 2

    # ===================== 业务节点参数 =====================
    START_NODES = [(0, y) for y in range(MAP_HEIGHT)]
    DEPOT_NODE = (MAP_WIDTH - 1, MAP_HEIGHT - 1)

    # ===================== 狼群算法参数 =====================
    POP_SIZE = 10

    # ===================== 目标函数权重 =====================
    # 新的目标函数同时考虑：
    # D: 总行驶距离
    # N: 启用车辆数
    # T: 时间窗惩罚
    # C: 冲突处理次数
    # R: 重规划次数
    # Q: 准死锁风险触发次数
    W1_DIST = 1.0
    W2_NUM = 150.0
    W3_TIME = 10.0
    W4_CONFLICT = 4.0
    W5_REPLAN = 10.0
    W6_RISK = 3.0
