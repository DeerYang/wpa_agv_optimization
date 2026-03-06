"""
路径规划模块（Tent-DFS）。

核心思想：
- 以 DFS 为主体搜索时空路径。
- 使用 reservation_table 避开已占用的时空节点。
- 使用 Tent 混沌序列动态调整候选扩展顺序，兼顾贪婪与探索。
"""

import random

from .config import Config


class TentDFSPlanner:
    """
    面向单台 AGV 的时空路径规划器。

    输入：
    - 起点、终点、起始时间、全局时空预约表、混沌序列迭代器。

    输出：
    - 成功时返回 [(x, y, t), ...] 路径。
    - 失败时返回 None。
    """

    def __init__(self, grid_map):
        # 保存静态地图（0=可走，1=障碍）。
        self.grid = grid_map
        # 缓存地图宽度。
        self.width = Config.MAP_WIDTH
        # 缓存地图高度。
        self.height = Config.MAP_HEIGHT

    def plan(self, start_pos, end_pos, start_time, reservation_table, tent_seq_gen):
        """
        规划一段从 start_pos 到 end_pos 的时空路径。

        说明：
        - 每步移动时间固定 +1。
        - 不允许进入 reservation_table 中的 (x,y,t)。
        """
        # DFS 栈：元素格式 ((x,y), t)。
        stack = [(start_pos, start_time)]
        # 父指针映射：用于最终回溯路径。
        parent_map = {(start_pos, start_time): None}
        # 访问集合：当前搜索中避免重复走回头路。
        visited = {start_pos}

        # 安全保护：限制最大扩展次数，避免极端场景长时间卡住。
        steps = 0
        max_steps = 50000
        final_state = None

        # 当栈非空时持续搜索。
        while stack:
            # 取出当前节点（DFS 后进先出）。
            curr_pos, curr_time = stack.pop()
            steps += 1

            # 命中终点则结束搜索。
            if curr_pos == end_pos:
                final_state = (curr_pos, curr_time)
                break

            # 超过上限则判失败。
            if steps > max_steps:
                return None

            # 拆分当前坐标。
            cx, cy = curr_pos

            # 四连通移动方向。
            moves = [(0, 1), (0, -1), (1, 0), (-1, 0)]
            # 合法候选下一步。
            candidates = []

            # 枚举每个方向构造候选。
            for dx, dy in moves:
                nx, ny = cx + dx, cy + dy
                ntime = curr_time + 1

                # 越界检查。
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                # 障碍检查。
                if self.grid[nx][ny] == 1:
                    continue
                # 重复访问检查（当前轮搜索中避免环）。
                if (nx, ny) in visited:
                    continue
                # 时空冲突检查。
                if (nx, ny, ntime) in reservation_table:
                    continue

                # 通过检查则加入候选。
                candidates.append((nx, ny))

            # 无候选时自动回溯到上层分支。
            if not candidates:
                continue

            # 为候选计算启发式权重（到终点的曼哈顿距离）。
            cand_weights = []
            for cand in candidates:
                dist = abs(cand[0] - end_pos[0]) + abs(cand[1] - end_pos[1])
                cand_weights.append((cand, dist))

            # 读取混沌值，失败时用随机数兜底。
            try:
                tent_val = next(tent_seq_gen)
            except Exception:
                tent_val = random.random()

            # 70% 走贪婪模式（优先近终点），30% 走随机模式（增加探索）。
            if tent_val < 0.7:
                # DFS 是后进先出，所以按距离降序排后，最近点最后压栈先被探索。
                cand_weights.sort(key=lambda x: x[1], reverse=True)
            else:
                random.shuffle(cand_weights)

            # 将候选逐个压栈。
            for cand, _ in cand_weights:
                visited.add(cand)
                parent_map[(cand, curr_time + 1)] = (curr_pos, curr_time)
                stack.append((cand, curr_time + 1))

        # 若成功到达终点，则从终点按父指针回溯路径。
        if final_state:
            path = []
            curr = final_state
            while curr is not None:
                path.append((curr[0][0], curr[0][1], curr[1]))
                curr = parent_map[curr]
            # 回溯得到的是终点到起点，需反转。
            return path[::-1]

        # 搜索耗尽仍未命中终点，返回失败。
        return None

