# pathfinding.py
import random
from config import Config


class TentDFSPlanner:
    """
    Tent 混沌导向的深度优先搜索 (Tent-DFS) 规划器

    设计目的：
    为 AGV 寻找从起点到终点的无碰撞路径。

    核心特点：
    1. 完备性：只要物理上连通且未被动态障碍物完全封死，能通过回溯机制找到路径。
    2. 混沌决策：利用 Tent 混沌序列决定搜索邻居的优先级（是走近路还是随机探索）。
    3. 时空避障：不仅考虑静态墙壁，还通过 reservation_table 考虑时间维度上的车辆碰撞。
    """

    def __init__(self, grid_map):
        """
        初始化规划器
        :param grid_map: 全局静态地图 (0=空地, 1=障碍)
        """
        self.grid = grid_map
        # 从配置类读取地图尺寸，用于后续的边界检查
        self.width = Config.MAP_WIDTH
        self.height = Config.MAP_HEIGHT

    def plan(self, start_pos, end_pos, start_time, reservation_table, tent_seq_gen):
        """
        执行带回溯的时空路径搜索

        :param start_pos: 起点坐标 (x, y)
        :param end_pos: 终点坐标 (x, y)
        :param start_time: 出发时的绝对时间 (t)
        :param reservation_table: 全局预约表 (set)，包含其他 AGV 已经占用的 (x, y, t)
        :param tent_seq_gen: Tent 混沌序列生成器 (iterator)，用于产生随机决策值
        :return: 成功返回路径列表 [(x,y,t), ...], 失败返回 None
        """

        # --- 初始化 DFS 核心数据结构 ---

        # 栈 (Stack)：DFS 的核心，遵循“后进先出”原则。
        # 存储元组：(当前位置坐标, 当前时间步)
        stack = [(start_pos, start_time)]

        # 父节点映射表：用于在找到终点后，从终点反向回溯出完整路径。
        # 格式：{ (子节点坐标, 子节点时间): (父节点坐标, 父节点时间) }
        parent_map = {(start_pos, start_time): None}

        # 访问记录表 (Visited Set)：防止算法在同一个地方绕圈圈 (死循环)。
        # 注意：这里仅记录空间坐标 (x, y)，实行严格的空间 DFS。
        # 含义：如果某个格子在这个路径探索中走过了，就不要再走了。
        visited = set()
        visited.add(start_pos)

        # --- 安全保护机制 ---
        steps = 0
        max_steps = 50000  # 最大迭代步数，防止因为极端情况导致程序卡死

        final_state = None  # 用于存储找到终点时的状态 (坐标, 时间)

        # --- 开始主循环 (当栈不为空时一直搜索) ---
        while stack:
            # 1. 弹出栈顶元素 (当前处理的节点)
            curr_pos, curr_time = stack.pop()
            steps += 1

            # 2. 判断是否到达终点
            if curr_pos == end_pos:
                final_state = (curr_pos, curr_time)
                break  # 找到路径，跳出循环

            # 超时/超步数保护：如果搜太久还没找到，强制放弃
            if steps > max_steps:
                return None

            cx, cy = curr_pos  # 当前 x, y

            # --- 生成并筛选邻居节点 ---

            # 定义 4 个移动方向：上、下、右、左
            moves = [(0, 1), (0, -1), (1, 0), (-1, 0)]
            candidates = []  # 用于存放合法的下一步候选点

            for dx, dy in moves:
                nx, ny = cx + dx, cy + dy  # 计算新坐标
                ntime = curr_time + 1  # 时间必然流逝 1 秒

                # --- 核心合法性检查 (Validity Check) ---

                # A. 边界检查：不能跑出地图外
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue

                    # B. 静态障碍物检查：不能撞墙
                if self.grid[nx][ny] == 1:
                    continue

                    # C. 重复访问检查：不能走回头路 (防止死循环)
                if (nx, ny) in visited:
                    continue

                    # D. 动态避障检查：核心逻辑
                # 查询 reservation_table，看 (nx, ny) 在 ntime时刻 是否被其他车占用了
                if (nx, ny, ntime) in reservation_table:
                    continue  # 如果被占用，这个方向不能走

                # 如果所有检查都通过，加入候选名单
                candidates.append((nx, ny))

            # 如果没有合法的邻居 (死胡同)，循环会自动进入下一次迭代 (相当于回溯到上一个父节点)
            if not candidates:
                continue

                # --- Tent 混沌决策逻辑 (核心创新点) ---
            # 传统的 DFS 是固定顺序的。这里引入 Tent 映射来动态调整搜索顺序。

            # 1. 计算所有候选点到终点的曼哈顿距离 (作为贪婪的依据)
            cand_weights = []
            for cand in candidates:
                # 距离 = |x1-x2| + |y1-y2|
                dist = abs(cand[0] - end_pos[0]) + abs(cand[1] - end_pos[1])
                cand_weights.append((cand, dist))  # 存入 (坐标, 距离)

            # 2. 从生成器获取下一个 Tent 混沌值 (0到1之间)
            try:
                tent_val = next(tent_seq_gen)
            except:
                tent_val = random.random()  # 如果序列用完了，用伪随机兜底

            # 3. 根据混沌值决定排序策略
            # 阈值 0.7：意味着 70% 的概率表现得像“贪婪算法”，30% 的概率“随机探索”
            if tent_val < 0.7:
                # [贪婪模式]
                # 我们希望优先访问“距离终点最近”的点。
                # 因为是 Stack (后进先出)，所以要把“距离最小”的点放在“列表最后”压入栈。
                # sort(reverse=True) 会把距离大的排前面，距离小的排后面。
                # 压栈顺序：[远, 中, 近] -> 出栈顺序：近 -> 中 -> 远
                cand_weights.sort(key=lambda x: x[1], reverse=True)
            else:
                # [随机模式]
                # 打乱列表，增加搜索的随机性，有助于跳出局部死胡同
                random.shuffle(cand_weights)

            # --- 压栈与状态更新 ---
            for cand, _ in cand_weights:
                # 标记为已访问 (防止同一个路径分支中重复走)
                visited.add(cand)

                # 记录父子关系：cand 的父亲是 curr_pos
                parent_map[(cand, curr_time + 1)] = (curr_pos, curr_time)

                # 压入栈中，等待后续处理
                stack.append((cand, curr_time + 1))

        # --- 路径重构 (Backtracking) ---
        if final_state:
            path = []
            curr = final_state  # 从终点开始

            # 一直找爸爸，直到回到起点 (起点在 parent_map 中的值为 None)
            while curr is not None:
                # curr 结构是 ((x,y), t)，拆解并重组为 (x, y, t)
                path.append((curr[0][0], curr[0][1], curr[1]))
                curr = parent_map[curr]

            # 因为是从终点往起点找的，所以需要反转列表
            return path[::-1]
        else:
            # 栈空了也没找到终点，说明确实无路可走
            return None