# models.py

class Task:
    """
    任务实体类：代表仓库中的一个取货需求
    """
    def __init__(self, task_id, x, y, weight, deadline):
        self.id = task_id       # 任务唯一编号
        self.x = x              # 目标 X 坐标
        self.y = y              # 目标 Y 坐标
        self.weight = weight    # 货物重量
        self.deadline = deadline # 硬时间窗 (最晚完成时间)

    def __repr__(self):
        # 打印时的显示格式
        return f"Task(ID={self.id}, Pos=({self.x},{self.y}), W={self.weight}, DD={self.deadline})"

class AGV:
    """
    AGV 实体类：代表一辆具体的搬运机器人
    """
    def __init__(self, agv_id, start_pos):
        self.id = agv_id            # AGV 编号
        self.start_pos = start_pos  # 初始停泊位置
        self.tasks = []             # 分配给该车的任务列表
        self.path = []              # 规划好的完整路径 [(x,y,t), ...]
        self.load = 0               # 当前累计载重
        self.finish_time = 0        # 完成所有任务回到终点的时间

class Wolf:
    """
    狼实体类 (Wolf)：代表一个完整的调度方案 (Solution)
    """
    def __init__(self):
        self.agv_list = []      # 该方案中所有激活的 AGV 对象列表
        self.fitness = 0.0      # 适应度评分 (越小越好)
        self.vehicle_num = 0    # N: 使用车辆数
        self.total_dist = 0     # D: 总行驶距离
        self.time_penalty = 0   # T: 时间窗罚分