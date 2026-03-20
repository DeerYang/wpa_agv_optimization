import random

from .config import Config


class TentDFSPlanner:
    """Time-space DFS planner with explicit wait actions."""

    def __init__(self, grid_map):
        self.grid = grid_map
        self.width = Config.MAP_WIDTH
        self.height = Config.MAP_HEIGHT

    def _valid_cell(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[x][y] == 0

    def plan(self, start_pos, end_pos, start_time, reservation_table, tent_seq_gen, extra_blocks=None):
        extra_blocks = set() if extra_blocks is None else extra_blocks
        start_state = (start_pos, start_time)
        stack = [start_state]
        parent_map = {start_state: None}
        visited = {start_state}
        best_time_by_pos = {start_pos: start_time}

        base_dist = abs(start_pos[0] - end_pos[0]) + abs(start_pos[1] - end_pos[1])
        max_steps = 120000
        max_time = start_time + max(20, base_dist * 4 + 30)
        revisit_slack = 3
        steps = 0

        while stack:
            curr_pos, curr_time = stack.pop()
            steps += 1

            if curr_pos == end_pos:
                path = []
                curr = (curr_pos, curr_time)
                while curr is not None:
                    path.append((curr[0][0], curr[0][1], curr[1]))
                    curr = parent_map[curr]
                return path[::-1]

            if steps > max_steps:
                return None
            if curr_time >= max_time:
                continue

            cx, cy = curr_pos
            candidates = []
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)):
                nx, ny = cx + dx, cy + dy
                ntime = curr_time + 1
                if ntime > max_time:
                    continue

                if dx == 0 and dy == 0:
                    next_pos = curr_pos
                else:
                    if not self._valid_cell(nx, ny):
                        continue
                    next_pos = (nx, ny)

                if (next_pos[0], next_pos[1], ntime) in reservation_table or (next_pos[0], next_pos[1], ntime) in extra_blocks:
                    continue

                next_state = (next_pos, ntime)
                if next_state in visited:
                    continue

                best_seen = best_time_by_pos.get(next_pos)
                if best_seen is not None and ntime > best_seen + revisit_slack:
                    continue

                heuristic = abs(next_pos[0] - end_pos[0]) + abs(next_pos[1] - end_pos[1])
                if dx == 0 and dy == 0:
                    heuristic += 0.5
                candidates.append((next_state, heuristic))

            if not candidates:
                continue

            try:
                tent_val = next(tent_seq_gen)
            except Exception:
                tent_val = random.random()

            if tent_val < 0.7:
                candidates.sort(key=lambda item: item[1], reverse=True)
            else:
                random.shuffle(candidates)

            for next_state, _ in candidates:
                visited.add(next_state)
                parent_map[next_state] = (curr_pos, curr_time)
                prev_best_time = best_time_by_pos.get(next_state[0])
                if prev_best_time is None or next_state[1] < prev_best_time:
                    best_time_by_pos[next_state[0]] = next_state[1]
                stack.append(next_state)

        return None
