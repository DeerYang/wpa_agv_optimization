# ===================== 文件级说明 =====================
# 文件名: pathfinding.py
# 功能: 多AGV时空无冲突路径规划核心模块，实现Tent混沌导向的深度优先搜索(Tent-DFS)
# 核心能力: 静态障碍物避障、动态多车时空冲突避障、完备性路径搜索、混沌引导跳出局部最优
# 理论支撑: 对应开题报告中时空资源表冲突检测、路径规划算法设计、混沌映射改进策略
# 设计原则: 单例规划器设计，一次初始化可重复执行路径规划，无状态污染
# ======================================================

# 引入随机数库，用于混沌序列兜底与随机探索
import random
# 引入全局配置类
from config import Config


class TentDFSPlanner:
    """
    Tent混沌导向的深度优先搜索(Tent-DFS)路径规划器
    设计目的: 为单台AGV规划从起点到终点的时空无冲突路径，解决传统DFS固定搜索顺序易陷入死胡同的问题
    核心特性:
        1. 完备性: 只要物理路径连通且未被完全封死，可通过回溯机制找到可行路径
        2. 混沌决策: 利用Tent混沌序列动态调整邻居搜索优先级，平衡贪婪寻优与随机探索
        3. 时空避障: 基于时空预约表，同时规避静态障碍物与其他AGV的动态路径占用
        4. 边界保护: 内置最大迭代步数保护，避免极端场景下程序卡死
    """
    def __init__(self, grid_map):
        """
        规划器初始化方法
        :param grid_map: 全局静态栅格地图，二维数组，0=可通行，1=静态障碍物
        """
        # 存储全局静态栅格地图，用于后续静态障碍物检查
        self.grid = grid_map
        # 从全局配置读取地图宽度，用于边界合法性检查
        self.width = Config.MAP_WIDTH
        # 从全局配置读取地图高度，用于边界合法性检查
        self.height = Config.MAP_HEIGHT

    def plan(self, start_pos, end_pos, start_time, reservation_table, tent_seq_gen):
        """
        核心路径规划方法：执行带回溯的时空DFS路径搜索
        功能: 给定起点、终点、出发时间、全局资源预约表，生成一条无冲突的时空路径
        执行流程: 初始化DFS数据结构 -> 邻居节点合法性筛选 -> 混沌决策排序 -> 栈式深度搜索 -> 路径回溯重构
        :param start_pos: 起点坐标，元组格式(x, y)
        :param end_pos: 终点坐标，元组格式(x, y)
        :param start_time: AGV从起点出发的绝对时间戳(秒)，用于时间维度冲突检测
        :param reservation_table: 全局时空资源预约表，set集合，存储其他AGV已占用的(x,y,t)节点
        :param tent_seq_gen: Tent混沌序列迭代器，用于动态调整搜索优先级，平衡贪婪与探索
        :return: 成功返回路径列表，每个元素为(x,y,t)格式的时空节点；失败返回None
        """
        # ================ DFS核心数据结构初始化 ================
        # DFS核心栈结构，遵循"后进先出"原则，存储待处理的节点(当前坐标, 当前时间)
        stack = [(start_pos, start_time)]
        # 父节点映射表，用于找到终点后，从终点反向回溯出完整路径
        # 格式: { (子节点坐标, 子节点时间): (父节点坐标, 父节点时间) }
        parent_map = {(start_pos, start_time): None}
        # 空间访问记录表，防止算法在同一条路径中重复访问同一栅格，避免死循环
        # 设计说明: 仅记录空间坐标，实现严格的空间DFS，不重复走回头路
        visited = set()
        # 将起点标记为已访问
        visited.add(start_pos)

        # ================ 安全保护机制初始化 ================
        # 迭代步数计数器，用于触发最大步数保护
        steps = 0
        # 最大迭代步数限制，极端场景下防止程序无限循环卡死
        max_steps = 50000
        # 终点状态存储变量，找到终点后存储(终点坐标, 到达时间)，用于路径回溯
        final_state = None

        # ================ DFS主循环，栈不为空则持续搜索 ================
        while stack:
            # 1. 弹出栈顶元素，获取当前处理的节点坐标与时间（DFS核心：后进先出）
            curr_pos, curr_time = stack.pop()
            # 迭代步数+1，用于步数保护
            steps += 1

            # 2. 终点判断：如果当前节点坐标等于终点坐标，说明找到可行路径
            if curr_pos == end_pos:
                # 存储终点状态，用于后续路径回溯
                final_state = (curr_pos, curr_time)
                # 跳出主循环，终止搜索
                break

            # 3. 超步数保护：如果迭代步数超过最大值，强制终止搜索，返回失败
            if steps > max_steps:
                return None

            # 拆解当前节点的x、y坐标，用于后续邻居节点计算
            cx, cy = curr_pos

            # ================ 邻居节点生成与合法性筛选 ================
            # 定义AGV四方向移动规则：上、下、右、左，对应栅格地图中四个可移动方向
            moves = [(0, 1), (0, -1), (1, 0), (-1, 0)]
            # 初始化候选节点列表，存储通过所有合法性检查的下一步节点
            candidates = []

            # 遍历四个移动方向，生成候选节点并逐一校验
            for dx, dy in moves:
                # 计算移动后的新坐标x、y
                nx, ny = cx + dx, cy + dy
                # 计算移动后的时间戳，AGV移动一格耗时1秒，时间必然+1
                ntime = curr_time + 1

                # ---------------- 核心合法性四重校验 ----------------
                # 校验A：边界检查，新坐标必须在地图范围内，不能跑出地图外
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    # 超出地图边界，跳过该方向
                    continue
                # 校验B：静态障碍物检查，新坐标不能是墙壁/货架等静态障碍物
                if self.grid[nx][ny] == 1:
                    # 该坐标为障碍物，不可通行，跳过该方向
                    continue
                # 校验C：重复访问检查，该坐标在本次路径搜索中未被访问过，避免走回头路和死循环
                if (nx, ny) in visited:
                    # 该坐标已访问过，跳过该方向
                    continue
                # 校验D：动态避障检查，该时空节点(x,y,t)未被其他AGV预约占用
                if (nx, ny, ntime) in reservation_table:
                    # 该时空节点已被占用，会发生碰撞，跳过该方向
                    continue

                # 所有校验全部通过，将该坐标加入合法候选节点列表
                candidates.append((nx, ny))

            # 如果没有合法候选节点，说明当前路径走到死胡同，循环自动回溯到上一个父节点
            if not candidates:
                continue

            # ================ Tent混沌决策核心逻辑 ================
            # 传统DFS固定邻居搜索顺序，易陷入局部最优；此处通过混沌值动态调整搜索顺序
            # 初始化候选节点权重列表，存储(坐标, 到终点的曼哈顿距离)
            cand_weights = []
            # 遍历所有合法候选节点，计算到终点的曼哈顿距离，作为贪婪寻优的依据
            for cand in candidates:
                # 计算候选节点到终点的曼哈顿距离，距离越近，越接近目标
                dist = abs(cand[0] - end_pos[0]) + abs(cand[1] - end_pos[1])
                # 将候选节点和对应距离存入权重列表
                cand_weights.append((cand, dist))

            # 从混沌序列迭代器中获取下一个混沌值，范围0~1
            try:
                tent_val = next(tent_seq_gen)
            # 异常兜底：如果混沌序列迭代完毕，用随机数兜底，保证程序不崩溃
            except:
                tent_val = random.random()

            # 根据混沌值动态决定候选节点的排序策略，平衡贪婪寻优与随机探索
            # 阈值0.7：70%概率执行贪婪模式，优先走近路；30%概率执行随机模式，探索新路径
            if tent_val < 0.7:
                # 【贪婪模式】优先搜索距离终点最近的节点
                # 栈是后进先出，因此按距离降序排序，距离最近的节点排在列表最后，最先被弹出处理
                cand_weights.sort(key=lambda x: x[1], reverse=True)
            else:
                # 【随机模式】打乱候选节点顺序，增加搜索随机性，跳出局部死胡同
                random.shuffle(cand_weights)

            # ================ 候选节点压栈与状态更新 ================
            # 遍历排序后的候选节点，依次压入栈中
            for cand, _ in cand_weights:
                # 将候选节点标记为已访问，避免后续重复访问
                visited.add(cand)
                # 记录父子节点关系，用于后续路径回溯：子节点的父节点是当前节点
                parent_map[(cand, curr_time + 1)] = (curr_pos, curr_time)
                # 将候选节点和对应时间压入栈中，等待后续处理
                stack.append((cand, curr_time + 1))

        # ================ 路径回溯重构 ================
        # 如果final_state不为空，说明找到终点，开始反向回溯路径
        if final_state:
            # 初始化路径列表
            path = []
            # 从终点状态开始回溯
            curr = final_state
            # 循环回溯，直到回到起点（起点的父节点为None）
            while curr is not None:
                # 拆解当前状态的坐标和时间，重组为(x,y,t)格式，加入路径列表
                path.append((curr[0][0], curr[0][1], curr[1]))
                # 找到当前节点的父节点，继续回溯
                curr = parent_map[curr]
            # 因为是从终点往起点回溯，路径是倒序的，反转后得到起点到终点的正序路径
            return path[::-1]
        # 栈空了仍未找到终点，说明无可行路径，返回None
        else:
            return None