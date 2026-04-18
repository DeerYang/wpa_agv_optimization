"""全局配置模块。"""

from dataclasses import dataclass


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
    # U: 未完成客户任务数
    W1_DIST = 1.0
    W2_NUM = 150.0
    W3_TIME = 10.0
    W4_CONFLICT = 4.0
    W5_REPLAN = 10.0
    W6_RISK = 3.0
    W7_UNFINISHED = 500.0


@dataclass
class ImprovedOperatorConfig:
    """
    Improved 算子的概率 gate 超参数。

    集中 summoning / besieging 里原本硬编码的激活概率与阈值，便于论文里做
    消融实验（把任一概率置为 1.0 即关闭 gate，保持算子每代必跑）。
    默认值等价于重构前的硬编码行为。
    """

    # summoning: 按当前狼与头狼的 fitness gap 切换激活概率
    summoning_gap_threshold: float = 120.0
    summoning_prob_close: float = 0.45  # gap < threshold 时的激活概率
    summoning_prob_far: float = 0.7     # gap >= threshold 时的激活概率

    # besieging: 按迭代阶段切换激活概率，早期阶段 = curr_iter < max_iter // divisor
    besieging_early_phase_divisor: int = 3
    besieging_prob_early: float = 0.35
    besieging_prob_late: float = 0.6
