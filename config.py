# config.py

class Config:
    """
    全局配置类，用于管理所有静态参数
    """
    # --- 地图与仿真环境设置 ---
    MAP_WIDTH = 20  # 栅格地图宽度 (X轴)
    MAP_HEIGHT = 20  # 栅格地图高度 (Y轴)
    OBSTACLE_RATIO = 0.1  # 随机障碍物生成的比例 (10%是墙)

    # --- AGV 物理属性 ---
    AGV_CAPACITY = 100  # 单车最大载重量 (kg)
    AGV_SPEED = 1  # AGV 行驶速度 (1格/秒)
    SERVICE_TIME = 2  # 到达任务点后的装卸货耗时 (秒)

    # --- 逻辑设置 ---
    # 定义 AGV 的停泊/出发区：在地图最左侧的一列 (0, 0) 到 (0, 19)
    START_NODES = [(0, y) for y in range(MAP_HEIGHT)]
    # 定义 统一卸货区 (终点)：设在地图右下角
    DEPOT_NODE = (MAP_WIDTH - 1, MAP_HEIGHT - 1)

    # --- 算法参数 ---
    POP_SIZE = 10  # 种群规模 (初始化生成多少只狼/方案)

    # --- 目标函数权重 (用于计算 F 值) ---
    W1_DIST = 1.0  # 距离权重 (单位: 格)
    W2_NUM = 100.0  # 车辆数量权重 (设大一点，优先减少用车)
    W3_TIME = 5.0  # 时间窗惩罚权重 (单位: 秒)