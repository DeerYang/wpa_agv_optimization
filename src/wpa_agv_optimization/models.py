"""
核心数据模型模块。

阅读建议：
1. 先看 Task（任务是什么）。
2. 再看 AGV（车辆如何承载任务与路径）。
3. 最后看 Wolf（一个完整调度方案如何被表示与评分）。
"""


class Task:
    """
    任务实体。

    参数：
    - task_id: 任务唯一编号。
    - x, y: 任务在栅格地图中的坐标。
    - weight: 任务重量（kg）。
    - deadline: 任务截止时间（秒）。
    """

    def __init__(self, task_id, x, y, weight, deadline):
        # 保存任务编号。
        self.id = task_id
        # 保存任务 X 坐标。
        self.x = x
        # 保存任务 Y 坐标。
        self.y = y
        # 保存任务重量。
        self.weight = weight
        # 保存任务截止时间。
        self.deadline = deadline

    def __repr__(self):
        """调试输出：便于打印任务列表时快速查看任务关键信息。"""
        return f"Task(ID={self.id}, Pos=({self.x},{self.y}), W={self.weight}, DD={self.deadline})"


class AGV:
    """
    AGV 实体。

    参数：
    - agv_id: 车辆编号。
    - start_pos: 起始泊位坐标。
    """

    def __init__(self, agv_id, start_pos):
        # 车辆编号。
        self.id = agv_id
        # 起始位置（固定泊位）。
        self.start_pos = start_pos
        # 分配给该车的任务序列（按执行顺序）。
        self.tasks = []
        # 该车完整时空路径，元素格式为 (x, y, t)。
        self.path = []
        # 当前总载重（kg）。
        self.load = 0
        # 执行完全部任务并完成服务时间后的结束时刻。
        self.finish_time = 0


class Wolf:
    """
    狼个体实体。

    含义：
    - 一只狼 = 一套完整的多 AGV 调度方案。
    - 该对象同时保存方案结构（agv_list）与评估结果（fitness/N/D/T）。
    """

    def __init__(self):
        # 方案中的 AGV 列表。
        self.agv_list = []
        # 综合适应度（越小越好）。
        self.fitness = 0.0
        # 使用车辆数 N。
        self.vehicle_num = 0
        # 总行驶距离 D。
        self.total_dist = 0
        # 时间窗总惩罚 T。
        self.time_penalty = 0
        # 冲突处理次数统计。
        self.conflict_count = 0
        # 死锁解锁次数统计。
        self.deadlock_count = 0
        # 准死锁风险触发次数统计。
        self.deadlock_risk_count = 0
        # 重规划触发次数统计。
        self.replan_count = 0
        # 局部改道触发次数统计。
        self.reroute_count = 0
        # 未完成客户任务数（所有 AGV 加总）。
        self.unfinished_count = 0
