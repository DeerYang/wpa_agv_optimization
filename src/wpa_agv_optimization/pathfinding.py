from collections import deque
import heapq
import itertools

from .config import Config


class TentDFSPlanner:
    """Time-space heuristic planner with explicit wait actions."""

    def __init__(self, grid_map):
        self.grid = grid_map
        self.width = Config.MAP_WIDTH
        self.height = Config.MAP_HEIGHT
        self._neighbor_cache = {}
        self._distance_cache = {}
        self._build_neighbor_cache()

    def _valid_cell(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[x][y] == 0

    def _build_neighbor_cache(self):
        for x in range(self.width):
            for y in range(self.height):
                if not self._valid_cell(x, y):
                    continue
                neighbors = []
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nx, ny = x + dx, y + dy
                    if self._valid_cell(nx, ny):
                        neighbors.append((nx, ny))
                self._neighbor_cache[(x, y)] = tuple(neighbors)

    @staticmethod
    def _manhattan(start_pos, end_pos):
        return abs(start_pos[0] - end_pos[0]) + abs(start_pos[1] - end_pos[1])

    def _distance_map(self, end_pos):
        cached = self._distance_cache.get(end_pos)
        if cached is not None:
            return cached
        if not self._valid_cell(end_pos[0], end_pos[1]):
            self._distance_cache[end_pos] = {}
            return self._distance_cache[end_pos]

        dist = {end_pos: 0}
        queue = deque([end_pos])
        while queue:
            curr = queue.popleft()
            next_dist = dist[curr] + 1
            for neighbor in self._neighbor_cache.get(curr, ()):
                if neighbor in dist:
                    continue
                dist[neighbor] = next_dist
                queue.append(neighbor)

        self._distance_cache[end_pos] = dist
        return dist

    def _heuristic(self, start_pos, end_pos):
        dist_map = self._distance_map(end_pos)
        return dist_map.get(start_pos, self._manhattan(start_pos, end_pos))

    @staticmethod
    def _reconstruct_path(parent_map, end_state):
        path = []
        curr = end_state
        while curr is not None:
            path.append((curr[0][0], curr[0][1], curr[1]))
            curr = parent_map[curr]
        return path[::-1]

    def plan(
        self,
        start_pos,
        end_pos,
        start_time,
        reservation_table,
        extra_blocks=None,
        occupied_edges=None,
        max_time=None,
    ):
        extra_blocks = set() if extra_blocks is None else extra_blocks
        occupied_edges = set() if occupied_edges is None else occupied_edges
        start_state = (start_pos, start_time)
        parent_map = {start_state: None}
        best_cost = {start_state: start_time}
        tie_counter = itertools.count()

        dist_map = self._distance_map(end_pos)
        heuristic_fallback = self._manhattan
        neighbor_cache = self._neighbor_cache
        reservation_contains = reservation_table.__contains__
        extra_contains = extra_blocks.__contains__
        occupied_edge_contains = occupied_edges.__contains__
        best_cost_get = best_cost.get
        heap_push = heapq.heappush
        heap_pop = heapq.heappop

        base_dist = dist_map.get(start_pos, heuristic_fallback(start_pos, end_pos))
        max_steps = 120000
        if max_time is None:
            max_time = start_time + max(20, base_dist * 4 + 30)
        steps = 0

        open_heap = []
        heap_push(
            open_heap,
            (start_time + base_dist, base_dist, 0, next(tie_counter), start_state),
        )

        while open_heap:
            _, _, _, _, current_state = heap_pop(open_heap)
            curr_pos, curr_time = current_state

            if curr_time != best_cost_get(current_state):
                continue

            steps += 1
            if steps > max_steps:
                return None

            if curr_pos == end_pos:
                return self._reconstruct_path(parent_map, current_state)

            if curr_time >= max_time:
                continue

            ntime = curr_time + 1
            if ntime > max_time:
                continue

            move_candidates = []
            for next_pos in neighbor_cache.get(curr_pos, ()):
                timed_node = (next_pos[0], next_pos[1], ntime)
                if reservation_contains(timed_node) or extra_contains(timed_node):
                    continue
                if occupied_edge_contains((next_pos, curr_pos, ntime)):
                    continue

                next_state = (next_pos, ntime)
                prev_best = best_cost_get(next_state)
                if prev_best is not None and prev_best <= ntime:
                    continue

                heuristic = dist_map.get(next_pos, heuristic_fallback(next_pos, end_pos))
                move_candidates.append((heuristic, 0, next_state))

            wait_node = (curr_pos[0], curr_pos[1], ntime)
            if not reservation_contains(wait_node) and not extra_contains(wait_node):
                wait_state = (curr_pos, ntime)
                prev_best = best_cost_get(wait_state)
                if prev_best is None or prev_best > ntime:
                    heuristic = dist_map.get(curr_pos, heuristic_fallback(curr_pos, end_pos))
                    move_candidates.append((heuristic, 1, wait_state))

            if not move_candidates:
                continue

            # Lexicographic tie-break: lower heuristic first, then non-wait first.
            # Deterministic — do not shuffle.
            move_candidates.sort(key=lambda item: (item[0], item[1]))

            for heuristic, is_wait, next_state in move_candidates:
                ntime = next_state[1]
                best_cost[next_state] = ntime
                parent_map[next_state] = current_state
                heap_push(
                    open_heap,
                    (ntime + heuristic, heuristic, is_wait, next(tie_counter), next_state),
                )

        return None
