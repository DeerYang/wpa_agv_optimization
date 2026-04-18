"""
WPA operator module.

This file contains two operator sets that share the same evaluator:
1. Improved operators: the current project version.
2. Original operators: a discrete mapping of the original WPA paper.

Both variants reuse the same evaluation, path planning, and conflict handling
pipeline so benchmark comparisons stay fair.
"""

import random

import numpy as np
from scipy.special import gamma

from .config import Config, ImprovedOperatorConfig
from .models import AGV, Wolf
from .utils import manhattan_dist


class WPAOperators:
    """Collection of improved and original WPA operators."""

    def __init__(self, evaluator, operator_config: ImprovedOperatorConfig | None = None):
        self.evaluator = evaluator
        self.op_config = operator_config or ImprovedOperatorConfig()

    def _flatten_tasks(self, wolf):
        """Flatten all AGV task lists into one global sequence."""
        seq = []
        for agv in wolf.agv_list:
            seq.extend(agv.tasks)
        return seq

    @staticmethod
    def _flatten_agv_task_groups(task_groups):
        """Flatten one list of per-AGV task groups into a single sequence."""
        seq = []
        for tasks in task_groups:
            seq.extend(tasks)
        return seq

    @staticmethod
    def _weighted_component_scores(wolf):
        """Return the weighted objective contributions for one evaluated wolf."""
        return {
            "distance": Config.W1_DIST * float(getattr(wolf, "total_dist", 0)),
            "vehicle": Config.W2_NUM * float(getattr(wolf, "vehicle_num", 0)),
            "time": Config.W3_TIME * float(getattr(wolf, "time_penalty", 0)),
            "conflict": Config.W4_CONFLICT * float(getattr(wolf, "conflict_count", 0)),
            "replan": Config.W5_REPLAN * float(getattr(wolf, "replan_count", 0)),
            "risk": Config.W6_RISK * float(getattr(wolf, "deadlock_risk_count", 0)),
        }

    def _dominant_objective_component(self, wolf):
        """Return the dominant weighted objective component of one wolf."""
        scores = self._weighted_component_scores(wolf)
        return max(scores.items(), key=lambda item: (item[1], item[0]))[0]

    def _estimate_task_finish_times(self, agv):
        """Approximate task completion times for one AGV using the fast route model."""
        curr = agv.start_pos
        curr_time = 0
        finish_times = {}

        for task in agv.tasks:
            step = manhattan_dist(curr, (task.x, task.y))
            curr_time += step + Config.SERVICE_TIME
            finish_times[task.id] = curr_time
            curr = (task.x, task.y)

        return finish_times

    def _most_tardy_task_ids(self, wolf, top_k=2):
        """Return task ids with the highest approximate deadline pressure."""
        ranked = []
        for agv in wolf.agv_list:
            if not agv.tasks:
                continue
            finish_times = self._estimate_task_finish_times(agv)
            for task in agv.tasks:
                lateness = max(0, finish_times[task.id] - task.deadline)
                urgency = max(0.0, 220.0 - float(task.deadline)) / 20.0
                ranked.append((lateness * 6.0 + urgency, task.id))

        if not ranked:
            return []

        ranked.sort(reverse=True)
        chosen = [task_id for score, task_id in ranked[:top_k] if score > 0]
        if chosen:
            return chosen

        fallback = sorted(
            (task.deadline, task.id)
            for agv in wolf.agv_list
            for task in agv.tasks
        )
        return [task_id for _, task_id in fallback[:top_k]]

    def _lightest_agv(self, wolf):
        """Return the lightest active AGV, used for fleet-compression moves."""
        active_agvs = [agv for agv in wolf.agv_list if agv.tasks]
        if len(active_agvs) < 2:
            return None
        return min(
            active_agvs,
            key=lambda agv: (
                len(agv.tasks),
                agv.load,
                self._estimate_route_cost(agv.tasks, agv.start_pos),
            ),
        )

    def _priority_focus_ids(self, wolf, dominant, top_k=3):
        """Pick the task ids that deserve focused operator effort."""
        if dominant == "time":
            return set(self._most_tardy_task_ids(wolf, top_k=top_k))

        if dominant == "vehicle":
            light_agv = self._lightest_agv(wolf)
            if light_agv is None:
                return set()
            return {task.id for task in light_agv.tasks[:top_k]}

        focus_ids = self._bottleneck_task_ids(wolf)
        if not focus_ids:
            return set()
        current_seq = self._flatten_tasks(wolf)
        ranked = sorted(
            (
                (self._task_risk_score(current_seq, idx, focus_ids), task.id)
                for idx, task in enumerate(current_seq)
                if task.id in focus_ids
            ),
            reverse=True,
        )
        return {task_id for _, task_id in ranked[:top_k]}

    def _move_task_ids_earlier(self, task_seq, task_ids, step_cap=3):
        """Move a few target tasks earlier in the global order."""
        if len(task_seq) < 2:
            return None

        new_seq = self._copy_wolf_tasks(task_seq)
        original_ids = [task.id for task in task_seq]
        moved = False

        for task_id in task_ids:
            current_idx = next((idx for idx, task in enumerate(new_seq) if task.id == task_id), None)
            if current_idx is None or current_idx == 0:
                continue
            item = new_seq.pop(current_idx)
            new_idx = max(0, current_idx - step_cap)
            new_seq.insert(new_idx, item)
            moved = moved or (new_idx != current_idx)

        if not moved or [task.id for task in new_seq] == original_ids:
            return None
        return new_seq

    def _merge_lightest_agv_sequence(self, wolf):
        """Try to absorb the lightest AGV into the remaining fleet."""
        active_agvs = [agv for agv in wolf.agv_list if agv.tasks]
        if len(active_agvs) < 2:
            return None

        donor = self._lightest_agv(wolf)
        if donor is None:
            return None

        recipient_agvs = [agv for agv in active_agvs if agv.id != donor.id]
        route_map = {agv.id: list(agv.tasks) for agv in recipient_agvs}
        load_map = {agv.id: sum(task.weight for task in agv.tasks) for agv in recipient_agvs}

        for task in donor.tasks:
            best_plan = None
            for agv in recipient_agvs:
                if load_map[agv.id] + task.weight > Config.AGV_CAPACITY:
                    continue

                base_tasks = route_map[agv.id]
                base_cost = self._estimate_route_cost(base_tasks, agv.start_pos)
                for pos in range(len(base_tasks) + 1):
                    candidate_tasks = base_tasks[:pos] + [task] + base_tasks[pos:]
                    delta = self._estimate_route_cost(candidate_tasks, agv.start_pos) - base_cost
                    if (best_plan is None) or (delta < best_plan[0]):
                        best_plan = (delta, agv.id, pos)

            if best_plan is None:
                return None

            _, agv_id, pos = best_plan
            route_map[agv_id].insert(pos, task)
            load_map[agv_id] += task.weight

        merged_seq = self._flatten_agv_task_groups([route_map[agv.id] for agv in recipient_agvs])
        if [task.id for task in merged_seq] == [task.id for task in self._flatten_tasks(wolf)]:
            return None
        return merged_seq

    def _spread_focus_tasks(self, task_seq, focus_ids):
        """Spread bottleneck tasks apart to reduce localized congestion pressure."""
        focus_tasks = [task for task in task_seq if task.id in focus_ids]
        other_tasks = [task for task in task_seq if task.id not in focus_ids]
        if len(focus_tasks) < 2 or not other_tasks:
            return None

        result = [focus_tasks[0]]
        remaining_focus = focus_tasks[1:]
        chunk_size = max(1, len(other_tasks) // max(1, len(remaining_focus)))
        chunk_fill = 0

        for task in other_tasks:
            result.append(task)
            chunk_fill += 1
            if remaining_focus and chunk_fill >= chunk_size:
                result.append(remaining_focus.pop(0))
                chunk_fill = 0

        result.extend(remaining_focus)
        if [task.id for task in result] == [task.id for task in task_seq]:
            return None
        return result

    def _replace_agv_tasks(self, wolf, target_agv_id, replacement_tasks):
        """Return one flattened sequence with a single AGV subsequence replaced."""
        task_groups = []
        for agv in wolf.agv_list:
            if agv.id == target_agv_id:
                task_groups.append(list(replacement_tasks))
            else:
                task_groups.append(list(agv.tasks))
        return self._flatten_agv_task_groups(task_groups)

    def _route_detour_score(self, tasks, idx, start_pos):
        """Approximate how much one task hurts local route compactness."""
        prev_pos = start_pos if idx == 0 else self._task_pos(tasks[idx - 1])
        curr_pos = self._task_pos(tasks[idx])
        next_pos = Config.DEPOT_NODE if idx == len(tasks) - 1 else self._task_pos(tasks[idx + 1])
        return (
            manhattan_dist(prev_pos, curr_pos)
            + manhattan_dist(curr_pos, next_pos)
            - manhattan_dist(prev_pos, next_pos)
        )

    def _shorten_bottleneck_route_sequence(self, wolf, top_k=4):
        """Locally reorder the bottleneck AGV route to reduce fast route cost."""
        active_agvs = [agv for agv in wolf.agv_list if agv.tasks]
        if not active_agvs:
            return None

        bottleneck_agv = max(active_agvs, key=self._agv_route_cost)
        base_tasks = list(bottleneck_agv.tasks)
        if len(base_tasks) < 3:
            return None

        start_pos = bottleneck_agv.start_pos
        base_cost = self._estimate_route_cost(base_tasks, start_pos)
        ranked_indices = sorted(
            range(len(base_tasks)),
            key=lambda idx: (
                self._route_detour_score(base_tasks, idx, start_pos),
                -base_tasks[idx].deadline,
            ),
            reverse=True,
        )
        focus_indices = ranked_indices[: min(top_k, len(base_tasks))]
        best_tasks = None
        best_cost = base_cost

        for idx in focus_indices:
            remainder = list(base_tasks)
            task = remainder.pop(idx)
            for insert_idx in range(len(remainder) + 1):
                if insert_idx == idx:
                    continue
                candidate = remainder[:insert_idx] + [task] + remainder[insert_idx:]
                cost = self._estimate_route_cost(candidate, start_pos)
                if cost < best_cost:
                    best_cost = cost
                    best_tasks = candidate

        for focus_i, i in enumerate(focus_indices):
            for j in focus_indices[focus_i + 1 :]:
                candidate = list(base_tasks)
                candidate[i], candidate[j] = candidate[j], candidate[i]
                cost = self._estimate_route_cost(candidate, start_pos)
                if cost < best_cost:
                    best_cost = cost
                    best_tasks = candidate

        for idx in focus_indices:
            for seg_len in range(2, min(4, len(base_tasks)) + 1):
                start = max(0, min(idx, len(base_tasks) - seg_len))
                candidate = list(base_tasks)
                candidate[start : start + seg_len] = reversed(candidate[start : start + seg_len])
                cost = self._estimate_route_cost(candidate, start_pos)
                if cost < best_cost:
                    best_cost = cost
                    best_tasks = candidate

        if best_tasks is None:
            return None

        candidate_seq = self._replace_agv_tasks(wolf, bottleneck_agv.id, best_tasks)
        if [task.id for task in candidate_seq] == [task.id for task in self._flatten_tasks(wolf)]:
            return None
        return candidate_seq

    def _alpha_priority_task_ids(self, alpha_wolf, dominant, max_tasks=4):
        """Select the alpha tasks that are most worth inheriting."""
        alpha_tasks = self._flatten_tasks(alpha_wolf)
        if not alpha_tasks:
            return []

        if dominant == "time":
            urgent_ids = {
                task.id for task in sorted(alpha_tasks, key=lambda task: task.deadline)[:max_tasks]
            }
            return [task.id for task in alpha_tasks if task.id in urgent_ids]

        if dominant == "vehicle":
            active_agvs = [agv for agv in alpha_wolf.agv_list if agv.tasks]
            if not active_agvs:
                return []
            anchor_agv = max(
                active_agvs,
                key=lambda agv: (len(agv.tasks), -self._estimate_route_cost(agv.tasks, agv.start_pos)),
            )
            return [task.id for task in anchor_agv.tasks[:max_tasks]]

        focus_ids = self._bottleneck_task_ids(alpha_wolf)
        selected = [task.id for task in alpha_tasks if task.id in focus_ids][:max_tasks]
        if selected:
            return selected
        return [task.id for task in alpha_tasks[:max_tasks]]

    def _inherit_priority_tasks(self, wolf_tasks, alpha_tasks, priority_ids, front_bias=False):
        """Keep a selected alpha task subset contiguous in the follower sequence."""
        if not priority_ids:
            return None

        wolf_task_map = {task.id: task for task in wolf_tasks}
        chosen_ids = [task_id for task_id in priority_ids if task_id in wolf_task_map]
        if not chosen_ids:
            return None

        base_ids = [task.id for task in wolf_tasks if task.id not in chosen_ids]
        if front_bias:
            child_ids = chosen_ids + base_ids
        else:
            alpha_pos = self._index_map(alpha_tasks)
            target_center = sum(alpha_pos[task_id] for task_id in chosen_ids if task_id in alpha_pos) / len(chosen_ids)
            insert_idx = max(0, min(len(base_ids), round(target_center) - (len(chosen_ids) // 2)))
            child_ids = base_ids[:insert_idx] + chosen_ids + base_ids[insert_idx:]

        if child_ids == [task.id for task in wolf_tasks]:
            return None
        return [wolf_task_map[task_id] for task_id in child_ids]


    @staticmethod
    def _follow_shape_base(wolf, alpha_wolf):
        """Prefer the lower-vehicle layout when borrowing route boundaries."""
        if alpha_wolf is None:
            return wolf
        if getattr(alpha_wolf, "vehicle_num", 0) <= getattr(wolf, "vehicle_num", 0):
            return alpha_wolf
        return wolf

    @staticmethod
    def _copy_wolf_tasks(task_seq):
        """Return a safe shallow copy for sequence reordering."""
        return list(task_seq)

    @staticmethod
    def _index_map(task_seq):
        """Build a task id to index mapping."""
        return {task.id: idx for idx, task in enumerate(task_seq)}

    @staticmethod
    def _task_pos(task):
        """Return one task's grid position."""
        return (task.x, task.y)

    def _agv_route_cost(self, agv):
        """Estimate one AGV route cost for bottleneck detection."""
        return self._estimate_route_cost(agv.tasks, agv.start_pos)

    def _bottleneck_task_ids(self, wolf):
        """Return all task ids on the currently worst AGV route."""
        active_agvs = [agv for agv in wolf.agv_list if agv.tasks]
        if not active_agvs:
            return set()
        bottleneck_agv = max(active_agvs, key=self._agv_route_cost)
        return {task.id for task in bottleneck_agv.tasks}

    def _task_risk_score(self, task_seq, idx, focus_ids=None):
        """Approximate which tasks deserve priority adjustment."""
        focus_ids = set() if focus_ids is None else set(focus_ids)
        task = task_seq[idx]

        prev_pos = Config.DEPOT_NODE if idx == 0 else self._task_pos(task_seq[idx - 1])
        curr_pos = self._task_pos(task)
        next_pos = Config.DEPOT_NODE if idx == len(task_seq) - 1 else self._task_pos(task_seq[idx + 1])
        detour = (
            manhattan_dist(prev_pos, curr_pos)
            + manhattan_dist(curr_pos, next_pos)
            - manhattan_dist(prev_pos, next_pos)
        )
        deadline_bias = max(0, 260 - task.deadline) / 12.0
        focus_bias = 6.0 if task.id in focus_ids else 0.0
        return detour + deadline_bias + focus_bias

    def _best_insert_position(self, base_seq, task):
        """Find the lowest local-cost insertion slot for one task."""
        best_seq = None
        best_cost = None

        for insert_idx in range(len(base_seq) + 1):
            candidate = base_seq[:insert_idx] + [task] + base_seq[insert_idx:]
            cost = 0.0
            for idx in range(len(candidate)):
                cost += self._task_risk_score(candidate, idx)
            if (best_cost is None) or (cost < best_cost):
                best_cost = cost
                best_seq = candidate

        return best_seq

    def _guided_reinsert_by_risk(self, task_seq, focus_ids=None, top_k=3):
        """Move one high-risk task to its best local insertion slot."""
        if len(task_seq) < 3:
            return None

        focus_ids = set() if focus_ids is None else set(focus_ids)
        ranked = sorted(
            ((self._task_risk_score(task_seq, idx, focus_ids), idx) for idx in range(len(task_seq))),
            reverse=True,
        )

        best_candidate = None
        best_cost = None
        for _, idx in ranked[:top_k]:
            base_seq = self._copy_wolf_tasks(task_seq)
            task = base_seq.pop(idx)
            candidate = self._best_insert_position(base_seq, task)
            if candidate is None:
                continue
            cost = sum(self._task_risk_score(candidate, i, focus_ids) for i in range(len(candidate)))
            if (best_cost is None) or (cost < best_cost):
                best_cost = cost
                best_candidate = candidate

        return best_candidate

    def _pull_forward_high_risk_task(self, task_seq, focus_ids=None, step_cap=3):
        """Pull one high-risk task forward by a few positions."""
        if len(task_seq) < 3:
            return None

        focus_ids = set() if focus_ids is None else set(focus_ids)
        idx = max(range(len(task_seq)), key=lambda i: self._task_risk_score(task_seq, i, focus_ids))
        if idx == 0:
            return None

        new_seq = self._copy_wolf_tasks(task_seq)
        item = new_seq.pop(idx)
        new_idx = max(0, idx - step_cap)
        new_seq.insert(new_idx, item)
        return new_seq

    def _swap_across_regions(self, task_seq, focus_ids=None):
        """Swap one bottleneck-region task with one non-bottleneck task."""
        if len(task_seq) < 2:
            return None

        focus_ids = set() if focus_ids is None else set(focus_ids)
        focus_indices = [idx for idx, task in enumerate(task_seq) if task.id in focus_ids]
        other_indices = [idx for idx, task in enumerate(task_seq) if task.id not in focus_ids]
        if not focus_indices or not other_indices:
            return None

        i = max(focus_indices, key=lambda idx: self._task_risk_score(task_seq, idx, focus_ids))
        j = min(other_indices, key=lambda idx: self._task_risk_score(task_seq, idx, focus_ids))
        if i == j:
            return None

        new_seq = self._copy_wolf_tasks(task_seq)
        new_seq[i], new_seq[j] = new_seq[j], new_seq[i]
        return new_seq

    def _choose_alpha_cluster(self, alpha_wolf, seg_len_min=2, seg_len_max=4):
        """Choose one compact leader task cluster for structured inheritance."""
        best_cluster = None
        best_score = None

        for agv in alpha_wolf.agv_list:
            tasks = agv.tasks
            if len(tasks) < seg_len_min:
                continue
            max_len = min(seg_len_max, len(tasks))
            for seg_len in range(seg_len_min, max_len + 1):
                for start in range(len(tasks) - seg_len + 1):
                    cluster = tasks[start : start + seg_len]
                    score = 0.0
                    for idx in range(len(cluster) - 1):
                        score += manhattan_dist(self._task_pos(cluster[idx]), self._task_pos(cluster[idx + 1]))
                    score += sum(task.deadline for task in cluster) / (150.0 * len(cluster))
                    if (best_score is None) or (score < best_score):
                        best_score = score
                        best_cluster = cluster

        return best_cluster

    def _inherit_cluster_sequence(self, wolf_tasks, alpha_tasks, cluster_tasks):
        """Keep one alpha task cluster contiguous inside the follower sequence."""
        if not cluster_tasks:
            return None

        cluster_ids = [task.id for task in cluster_tasks]
        wolf_task_map = {task.id: task for task in wolf_tasks}
        if any(task_id not in wolf_task_map for task_id in cluster_ids):
            return None

        alpha_pos = self._index_map(alpha_tasks)
        base_ids = [task.id for task in wolf_tasks if task.id not in cluster_ids]
        target_center = sum(alpha_pos[task_id] for task_id in cluster_ids) / len(cluster_ids)
        insert_idx = max(0, min(len(base_ids), round(target_center) - (len(cluster_ids) // 2)))
        child_ids = base_ids[:insert_idx] + cluster_ids + base_ids[insert_idx:]
        return [wolf_task_map[task_id] for task_id in child_ids]

    def _destroy_repair_sequence(self, task_seq, focus_ids=None, remove_count=2):
        """Remove a few high-risk tasks and greedily repair the sequence."""
        if len(task_seq) <= remove_count:
            return None

        focus_ids = set() if focus_ids is None else set(focus_ids)
        ranked_indices = sorted(
            range(len(task_seq)),
            key=lambda idx: self._task_risk_score(task_seq, idx, focus_ids),
            reverse=True,
        )
        remove_indices = sorted(ranked_indices[:remove_count], reverse=True)
        remaining = self._copy_wolf_tasks(task_seq)
        removed_tasks = []

        for idx in remove_indices:
            removed_tasks.append(remaining.pop(idx))

        rebuilt = remaining
        for task in removed_tasks:
            candidate = self._best_insert_position(rebuilt, task)
            if candidate is None:
                return None
            rebuilt = candidate

        return rebuilt

    def _decode_sequence_to_agvs(self, task_seq):
        """Decode by capacity only. Kept as a simple fallback decoder."""
        if not task_seq:
            return []

        agv_list = []
        agv_id = 0
        curr_agv = AGV(agv_id=agv_id, start_pos=Config.START_NODES[agv_id])
        curr_load = 0

        for task in task_seq:
            if task.weight > Config.AGV_CAPACITY:
                return None

            if curr_load + task.weight > Config.AGV_CAPACITY:
                if curr_agv.tasks:
                    curr_agv.load = curr_load
                    agv_list.append(curr_agv)
                agv_id += 1
                if agv_id >= len(Config.START_NODES):
                    return None
                curr_agv = AGV(agv_id=agv_id, start_pos=Config.START_NODES[agv_id])
                curr_load = 0

            curr_agv.tasks.append(task)
            curr_load += task.weight

        if curr_agv.tasks:
            curr_agv.load = curr_load
            agv_list.append(curr_agv)

        return agv_list

    def _estimate_route_cost(self, tasks, start_pos):
        """Fast route cost estimate used only inside operator decoding."""
        if not tasks:
            return 0.0

        curr = start_pos
        curr_time = 0
        dist = 0
        tardy = 0

        for task in tasks:
            step = manhattan_dist(curr, (task.x, task.y))
            dist += step
            curr_time += step + Config.SERVICE_TIME
            tardy += max(0, curr_time - task.deadline)
            curr = (task.x, task.y)

        dist += manhattan_dist(curr, Config.DEPOT_NODE)
        return dist + (Config.W3_TIME * tardy)

    def _decode_sequence_to_agvs_cost_based(self, task_seq):
        """Decode by inserting each task into the least-cost feasible place."""
        if not task_seq:
            return []

        agv_list = []
        next_id = 0
        max_agv = len(Config.START_NODES)

        for task in task_seq:
            if task.weight > Config.AGV_CAPACITY:
                return None

            best_plan = None

            for agv_idx, agv in enumerate(agv_list):
                if agv.load + task.weight > Config.AGV_CAPACITY:
                    continue

                base_cost = self._estimate_route_cost(agv.tasks, agv.start_pos)
                for pos in range(len(agv.tasks) + 1):
                    new_tasks = agv.tasks[:pos] + [task] + agv.tasks[pos:]
                    new_cost = self._estimate_route_cost(new_tasks, agv.start_pos)
                    delta = new_cost - base_cost
                    if (best_plan is None) or (delta < best_plan["delta"]):
                        best_plan = {
                            "mode": "insert",
                            "agv_idx": agv_idx,
                            "pos": pos,
                            "delta": delta,
                        }

            if next_id < max_agv:
                new_start = Config.START_NODES[next_id]
                new_cost = self._estimate_route_cost([task], new_start)
                open_bias = Config.W2_NUM * 0.05
                open_delta = new_cost + open_bias
                if (best_plan is None) or (open_delta < best_plan["delta"]):
                    best_plan = {"mode": "new", "delta": open_delta}

            if best_plan is None:
                return None

            if best_plan["mode"] == "insert":
                target = agv_list[best_plan["agv_idx"]]
                target.tasks.insert(best_plan["pos"], task)
                target.load += task.weight
            else:
                new_agv = AGV(agv_id=next_id, start_pos=Config.START_NODES[next_id])
                new_agv.tasks = [task]
                new_agv.load = task.weight
                agv_list.append(new_agv)
                next_id += 1

        return agv_list

    def _decode_sequence_to_agvs_stable(self, task_seq, base_wolf=None):
        """Decode by preserving base AGV segment boundaries whenever feasible."""
        if not task_seq:
            return []
        if base_wolf is None or not getattr(base_wolf, "agv_list", None):
            return self._decode_sequence_to_agvs_cost_based(task_seq)

        base_agvs = [agv for agv in base_wolf.agv_list if agv.tasks]
        if not base_agvs:
            return self._decode_sequence_to_agvs_cost_based(task_seq)
        if sum(len(agv.tasks) for agv in base_agvs) != len(task_seq):
            return self._decode_sequence_to_agvs_cost_based(task_seq)

        decoded = []
        offset = 0
        total_segments = len(base_agvs)

        for idx, base_agv in enumerate(base_agvs):
            remaining_tasks = len(task_seq) - offset
            remaining_segments = total_segments - idx
            if remaining_tasks <= 0:
                break

            min_take = remaining_tasks if remaining_segments == 1 else 1
            max_take = remaining_tasks - max(0, remaining_segments - 1)
            take = min(len(base_agv.tasks), max_take)
            take = max(min_take, take)

            segment = list(task_seq[offset : offset + take])
            segment_load = sum(task.weight for task in segment)
            while segment_load > Config.AGV_CAPACITY and take > min_take:
                take -= 1
                segment = list(task_seq[offset : offset + take])
                segment_load = sum(task.weight for task in segment)

            if segment_load > Config.AGV_CAPACITY:
                return self._decode_sequence_to_agvs_cost_based(task_seq)

            new_agv = AGV(agv_id=base_agv.id, start_pos=base_agv.start_pos)
            new_agv.tasks = segment
            new_agv.load = segment_load
            decoded.append(new_agv)
            offset += take

        if offset != len(task_seq):
            return self._decode_sequence_to_agvs_cost_based(task_seq)

        return decoded

    def _approximate_candidate_score(self, decoded_agvs):
        """Cheap score used to rank candidates before strict evaluation."""
        active_agvs = [agv for agv in decoded_agvs if agv.tasks]
        route_cost = sum(self._estimate_route_cost(agv.tasks, agv.start_pos) for agv in active_agvs)
        vehicle_cost = Config.W2_NUM * len(active_agvs)
        return route_cost + vehicle_cost

    def _prepare_candidate(self, name, task_seq, decoder="cost_based", base_wolf=None):
        """Decode one candidate and attach a cheap approximate score."""
        if decoder == "simple":
            decoded_agvs = self._decode_sequence_to_agvs(task_seq)
        elif decoder == "stable":
            decoded_agvs = self._decode_sequence_to_agvs_stable(task_seq, base_wolf=base_wolf)
        else:
            decoded_agvs = self._decode_sequence_to_agvs_cost_based(task_seq)
        if decoded_agvs is None:
            return None
        return (name, decoded_agvs, self._approximate_candidate_score(decoded_agvs))

    def _prepare_strategy_candidate(
        self,
        name,
        task_seq,
        *,
        decoder="cost_based",
        decode_base_wolf=None,
        eval_base_wolf=None,
    ):
        """Prepare one candidate with separated decode and evaluation bases."""
        prepared = self._prepare_candidate(
            name,
            task_seq,
            decoder=decoder,
            base_wolf=decode_base_wolf,
        )
        if prepared is None:
            return None
        _, decoded_agvs, approx_score = prepared
        return {
            "name": name,
            "decoded_agvs": decoded_agvs,
            "approx_score": approx_score,
            "eval_base_wolf": eval_base_wolf,
        }

    def _evaluate_strategy_candidates(self, prepared_candidates, *, top_k=None):
        """Strictly evaluate prepared candidates with per-candidate evaluation bases."""
        if not prepared_candidates:
            return None

        normalized = [
            (item["name"], item["decoded_agvs"], item["approx_score"], item.get("eval_base_wolf"))
            for item in prepared_candidates
        ]
        if top_k is None:
            limit = self._adaptive_strict_budget([(name, decoded_agvs, approx) for name, decoded_agvs, approx, _ in normalized])
        else:
            limit = max(1, min(top_k, len(normalized)))

        candidate_best = None
        candidate_best_fitness = None
        for name, decoded_agvs, _, eval_base_wolf in sorted(normalized, key=lambda item: item[2])[:limit]:
            result = self._strict_candidate_from_agvs(eval_base_wolf, name, decoded_agvs)
            fitness = self._result_fitness(result)
            if fitness is None:
                continue
            if candidate_best is None or fitness < candidate_best_fitness:
                candidate_best = result
                candidate_best_fitness = fitness

        return candidate_best

    @staticmethod
    def _result_fitness(result):
        """Read one strict evaluation result's numeric fitness."""
        if result is None:
            return None
        if isinstance(result, dict):
            return float(result["fitness"])
        return float(result.fitness)

    def _adaptive_strict_budget(self, prepared_candidates, fallback_top_k=2, close_gap=8.0):
        """Use fewer strict evaluations when the approximate winner is clearly ahead."""
        if not prepared_candidates:
            return 0
        ordered = sorted(prepared_candidates, key=lambda item: item[2])
        if len(ordered) == 1:
            return 1
        if ordered[1][2] - ordered[0][2] >= close_gap:
            return 1
        return min(fallback_top_k, len(ordered))

    def _evaluate_prepared_candidates(self, prepared_candidates, strict_eval, top_k=2):
        """Strictly evaluate only the best-looking prepared candidates."""
        if not prepared_candidates:
            return None

        if top_k is None:
            limit = self._adaptive_strict_budget(prepared_candidates)
        else:
            limit = max(1, min(top_k, len(prepared_candidates)))
        candidate_best = None
        candidate_best_fitness = None

        for name, payload, _ in sorted(prepared_candidates, key=lambda item: item[2])[:limit]:
            result = strict_eval(name, payload)
            fitness = self._result_fitness(result)
            if fitness is None:
                continue
            if candidate_best is None or fitness < candidate_best_fitness:
                candidate_best = result
                candidate_best_fitness = fitness

        return candidate_best

    def _strict_candidate_from_agvs(self, base_wolf, candidate_name, decoded_agvs):
        """Run the strict evaluator on one decoded candidate."""
        new_wolf = Wolf()
        new_wolf.agv_list = decoded_agvs
        candidate = self.evaluator.rebuild_wolf(new_wolf, base_wolf=base_wolf)
        if candidate is not None:
            setattr(candidate, "_candidate_name", candidate_name)
        return candidate

    def _rebuild_from_task_sequence(self, base_wolf, task_seq, decoder="cost_based"):
        """Decode, rebuild routes, and return a new evaluated wolf."""
        prepared = self._prepare_candidate("candidate", task_seq, decoder=decoder, base_wolf=base_wolf)
        if prepared is None:
            return None
        _, decoded_agvs, _ = prepared
        return self._strict_candidate_from_agvs(base_wolf, "candidate", decoded_agvs)

    def _evaluate_task_sequence_candidates(self, base_wolf, candidates, *, top_k=None, decoder="stable"):
        """Run shared prepare+strict-eval pipeline for task-sequence candidates."""
        prepared_candidates = []
        for name, task_seq in candidates:
            prepared = self._prepare_candidate(name, task_seq, decoder=decoder, base_wolf=base_wolf)
            if prepared is not None:
                prepared_candidates.append(prepared)

        return self._evaluate_prepared_candidates(
            prepared_candidates=prepared_candidates,
            strict_eval=lambda name, decoded_agvs: self._strict_candidate_from_agvs(
                base_wolf, name, decoded_agvs
            ),
            top_k=top_k,
        )

    def _neighbor_by_operator(self, task_seq, operator_name):
        """Generate one neighbor sequence with a simple discrete move."""
        if len(task_seq) < 2:
            return None

        new_seq = self._copy_wolf_tasks(task_seq)

        if operator_name == "swap":
            i, j = random.sample(range(len(new_seq)), 2)
            new_seq[i], new_seq[j] = new_seq[j], new_seq[i]
        elif operator_name == "insert":
            i, j = random.sample(range(len(new_seq)), 2)
            task = new_seq.pop(i)
            new_seq.insert(j, task)
        elif operator_name == "reverse":
            i, j = sorted(random.sample(range(len(new_seq)), 2))
            new_seq[i : j + 1] = list(reversed(new_seq[i : j + 1]))
        else:
            return None

        return new_seq

    def _soft_align_to_alpha(self, task_seq, alpha_seq, steps=1):
        """Move a few highly mismatched tasks one step toward leader order."""
        if len(task_seq) < 2 or len(task_seq) != len(alpha_seq):
            return None

        new_seq = self._copy_wolf_tasks(task_seq)
        alpha_pos = self._index_map(alpha_seq)

        mismatched = [
            (abs(idx - alpha_pos[task.id]), task.id)
            for idx, task in enumerate(new_seq)
            if idx != alpha_pos[task.id]
        ]
        if not mismatched:
            return None

        mismatched.sort(reverse=True)
        used = 0
        for _, task_id in mismatched:
            if used >= steps:
                break
            current_idx = next(i for i, task in enumerate(new_seq) if task.id == task_id)
            target_idx = alpha_pos[task_id]
            if current_idx == target_idx:
                continue
            direction = 1 if target_idx > current_idx else -1
            item = new_seq.pop(current_idx)
            new_seq.insert(current_idx + direction, item)
            used += 1

        return new_seq

    def _ox_inherit(self, wolf_tasks, alpha_tasks, seg_len_min=2, seg_len_max=3):
        """Build one OX-style child with a short elite segment."""
        if len(wolf_tasks) < 2 or len(alpha_tasks) != len(wolf_tasks):
            return None

        wolf_task_map = {t.id: t for t in wolf_tasks}
        wolf_ids = [t.id for t in wolf_tasks]
        alpha_ids = [t.id for t in alpha_tasks if t.id in wolf_task_map]
        if len(alpha_ids) != len(wolf_ids):
            return None

        n = len(wolf_ids)
        seg_len_max = min(seg_len_max, n)
        if seg_len_max < seg_len_min:
            return None

        seg_len = random.randint(seg_len_min, seg_len_max)
        alpha_start = random.randint(0, n - seg_len)
        alpha_segment = alpha_ids[alpha_start : alpha_start + seg_len]
        child_start = random.randint(0, n - seg_len)

        child_ids = [None] * n
        child_ids[child_start : child_start + seg_len] = alpha_segment

        fill_candidates = [tid for tid in wolf_ids if tid not in alpha_segment]
        fill_idx = 0
        for i in range(n):
            if child_ids[i] is None:
                child_ids[i] = fill_candidates[fill_idx]
                fill_idx += 1

        return [wolf_task_map[tid] for tid in child_ids]

    def _short_reverse(self, task_seq, seg_len_max=4):
        """Reverse a short segment as a bounded medium-strength perturbation."""
        if len(task_seq) < 3:
            return None
        new_seq = self._copy_wolf_tasks(task_seq)
        seg_len = random.randint(2, min(seg_len_max, len(new_seq)))
        start = random.randint(0, len(new_seq) - seg_len)
        end = start + seg_len
        new_seq[start:end] = list(reversed(new_seq[start:end]))
        return new_seq

    def _append_sampled_neighbors(
        self,
        candidates,
        task_seq,
        *,
        operator_name,
        count,
        label,
        decoder,
        decode_base_wolf,
        eval_base_wolf,
    ):
        """Append several sampled neighbors, deduplicated by task id order."""
        seen = set()
        for sample_idx in range(count):
            candidate_seq = self._neighbor_by_operator(task_seq, operator_name)
            if candidate_seq is None:
                continue
            key = tuple(task.id for task in candidate_seq)
            if key in seen:
                continue
            seen.add(key)
            name = label if sample_idx == 0 else f"{label}-{sample_idx + 1}"
            candidates.append((name, candidate_seq, decoder, decode_base_wolf, eval_base_wolf))

    def scouting(self, wolf):
        """Improved scouting: pressure-aware candidate generation focused on F reduction."""
        current_seq = self._flatten_tasks(wolf)
        if len(current_seq) < 2:
            return wolf

        dominant = self._dominant_objective_component(wolf)
        focus_ids = self._priority_focus_ids(wolf, dominant, top_k=3)
        candidates = []

        if dominant == "time":
            deadline_ids = self._most_tardy_task_ids(wolf, top_k=2)
            promoted = self._move_task_ids_earlier(current_seq, deadline_ids, step_cap=4)
            if promoted is not None:
                candidates.append(("deadline-promote", promoted, "stable", wolf, wolf))

            repaired = self._guided_reinsert_by_risk(current_seq, focus_ids=set(deadline_ids), top_k=3)
            if repaired is not None:
                candidates.append(("deadline-reinsert", repaired, "stable", wolf, wolf))
        elif dominant == "vehicle":
            merged = self._merge_lightest_agv_sequence(wolf)
            if merged is not None:
                candidates.append(("fleet-merge", merged, "cost_based", None, wolf))

            repaired = self._destroy_repair_sequence(current_seq, focus_ids=focus_ids, remove_count=2)
            if repaired is not None:
                candidates.append(("fleet-repair", repaired, "cost_based", None, wolf))
        else:
            shortened = self._shorten_bottleneck_route_sequence(wolf)
            if shortened is not None:
                candidates.append(("bottleneck-shorten", shortened, "stable", wolf, wolf))

            spread = self._spread_focus_tasks(current_seq, focus_ids)
            if spread is not None:
                candidates.append(("conflict-spread", spread, "stable", wolf, wolf))

            guided = self._guided_reinsert_by_risk(current_seq, focus_ids=focus_ids, top_k=3)
            if guided is not None:
                candidates.append(("bottleneck-reinsert", guided, "stable", wolf, wolf))

            repaired = self._destroy_repair_sequence(current_seq, focus_ids=focus_ids, remove_count=2)
            if repaired is not None:
                candidates.append(("conflict-repair", repaired, "stable", wolf, wolf))

        self._append_sampled_neighbors(
            candidates,
            current_seq,
            operator_name="swap",
            count=3,
            label="random-swap",
            decoder="stable",
            decode_base_wolf=wolf,
            eval_base_wolf=wolf,
        )
        self._append_sampled_neighbors(
            candidates,
            current_seq,
            operator_name="insert",
            count=2,
            label="random-insert",
            decoder="stable",
            decode_base_wolf=wolf,
            eval_base_wolf=wolf,
        )
        self._append_sampled_neighbors(
            candidates,
            current_seq,
            operator_name="reverse",
            count=2,
            label="reverse",
            decoder="stable",
            decode_base_wolf=wolf,
            eval_base_wolf=wolf,
        )

        prepared_candidates = []
        for name, candidate_seq, decoder, decode_base_wolf, eval_base_wolf in candidates:
            prepared = self._prepare_strategy_candidate(
                name,
                candidate_seq,
                decoder=decoder,
                decode_base_wolf=decode_base_wolf,
                eval_base_wolf=eval_base_wolf,
            )
            if prepared is not None:
                prepared_candidates.append(prepared)

        candidate_best = self._evaluate_strategy_candidates(prepared_candidates, top_k=None)
        candidate_name = getattr(candidate_best, "_candidate_name", None) if candidate_best is not None else None

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(
                f"  [scout improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f} "
                f"({dominant}, {candidate_name})"
            )
            return candidate_best
        return wolf

    def summoning(self, wolf, alpha_wolf):
        """Improved summoning: inherit alpha structures that target the dominant F component."""
        if not alpha_wolf.agv_list or not wolf.agv_list:
            return wolf

        cfg = self.op_config
        fitness_gap = max(0.0, float(wolf.fitness) - float(alpha_wolf.fitness))
        activation_prob = (
            cfg.summoning_prob_close
            if fitness_gap < cfg.summoning_gap_threshold
            else cfg.summoning_prob_far
        )
        if random.random() > activation_prob:
            return wolf

        alpha_tasks = self._flatten_tasks(alpha_wolf)
        wolf_tasks = self._flatten_tasks(wolf)
        if len(alpha_tasks) < 2 or len(wolf_tasks) < 2:
            return wolf

        dominant = self._dominant_objective_component(alpha_wolf)
        follow_base = self._follow_shape_base(wolf, alpha_wolf)
        alpha_cluster = self._choose_alpha_cluster(alpha_wolf, seg_len_min=2, seg_len_max=4)
        alpha_priority_ids = self._alpha_priority_task_ids(alpha_wolf, dominant, max_tasks=4)
        candidates = []

        ox_seq = self._ox_inherit(wolf_tasks, alpha_tasks, seg_len_min=2, seg_len_max=3)
        if ox_seq is not None:
            candidates.append(("ox", ox_seq, "stable", follow_base, follow_base))

        priority_seq = self._inherit_priority_tasks(
            wolf_tasks,
            alpha_tasks,
            alpha_priority_ids,
            front_bias=(dominant == "time"),
        )
        if priority_seq is not None:
            candidates.append(("priority-inherit", priority_seq, "stable", follow_base, follow_base))

        cluster_seq = self._inherit_cluster_sequence(wolf_tasks, alpha_tasks, alpha_cluster)
        if cluster_seq is not None:
            candidates.append(("cluster-inherit", cluster_seq, "stable", follow_base, follow_base))

        align_seq = self._soft_align_to_alpha(wolf_tasks, alpha_tasks, steps=2)
        if align_seq is not None:
            candidates.append(("align", align_seq, "stable", follow_base, follow_base))

        if wolf.vehicle_num > alpha_wolf.vehicle_num:
            merged = self._merge_lightest_agv_sequence(wolf)
            if merged is not None:
                candidates.append(("alpha-fleet-merge", merged, "cost_based", None, wolf))

        prepared_candidates = []
        for name, candidate_seq, decoder, decode_base_wolf, eval_base_wolf in candidates:
            prepared = self._prepare_strategy_candidate(
                name,
                candidate_seq,
                decoder=decoder,
                decode_base_wolf=decode_base_wolf,
                eval_base_wolf=eval_base_wolf,
            )
            if prepared is not None:
                prepared_candidates.append(prepared)

        candidate_best = self._evaluate_strategy_candidates(prepared_candidates, top_k=None)
        candidate_name = getattr(candidate_best, "_candidate_name", None) if candidate_best is not None else None

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(
                f"  [summon improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f} "
                f"({dominant}, {candidate_name})"
            )
            return candidate_best
        return wolf

    def _levy_flight_step(self, beta=1.5, step_scale=1.0):
        """Generate one Levy flight step with Mantegna's method."""
        sigma_num = gamma(1 + beta) * np.sin(np.pi * beta / 2)
        sigma_den = gamma((1 + beta) / 2) * beta * np.power(2, (beta - 1) / 2)
        sigma = np.power(sigma_num / sigma_den, 1 / beta)
        u = np.random.normal(0, sigma, 1)
        v = np.random.normal(0, 1, 1)
        step = step_scale * u / np.power(np.abs(v), 1 / beta)
        return abs(step[0])

    def besieging(self, wolf, alpha_wolf, curr_iter, max_iter):
        """Improved besieging: local refinement biased toward the dominant F component."""
        current_seq = self._flatten_tasks(wolf)
        alpha_seq = self._flatten_tasks(alpha_wolf)
        if len(current_seq) < 2 or len(current_seq) != len(alpha_seq):
            return wolf

        cfg = self.op_config
        early_cutoff = max_iter // cfg.besieging_early_phase_divisor
        activation_prob = (
            cfg.besieging_prob_early if curr_iter < early_cutoff else cfg.besieging_prob_late
        )
        if random.random() > activation_prob:
            return wolf

        dominant = self._dominant_objective_component(wolf)
        follow_base = self._follow_shape_base(wolf, alpha_wolf)
        focus_ids = self._priority_focus_ids(wolf, dominant, top_k=3)
        step_scale = 2.0 * (1 - curr_iter / max_iter)
        levy_step = self._levy_flight_step(step_scale=step_scale)
        candidates = []

        if dominant == "time":
            promoted = self._move_task_ids_earlier(current_seq, list(focus_ids), step_cap=2)
            if promoted is not None:
                candidates.append(("local-deadline-promote", promoted, "stable", wolf, wolf))

            reinserted = self._guided_reinsert_by_risk(current_seq, focus_ids=focus_ids, top_k=2)
            if reinserted is not None:
                candidates.append(("local-deadline-reinsert", reinserted, "stable", wolf, wolf))
        elif dominant == "vehicle":
            merged = self._merge_lightest_agv_sequence(wolf)
            if merged is not None:
                candidates.append(("local-fleet-merge", merged, "cost_based", None, wolf))

            align_seq = self._soft_align_to_alpha(current_seq, alpha_seq, steps=1)
            if align_seq is not None:
                candidates.append(("local-align", align_seq, "stable", follow_base, follow_base))
        else:
            shortened = self._shorten_bottleneck_route_sequence(wolf)
            if shortened is not None:
                candidates.append(("local-bottleneck-shorten", shortened, "stable", wolf, wolf))

            spread = self._spread_focus_tasks(current_seq, focus_ids)
            if spread is not None:
                candidates.append(("local-conflict-spread", spread, "stable", wolf, wolf))

            repaired = self._destroy_repair_sequence(current_seq, focus_ids=focus_ids, remove_count=2)
            if repaired is not None:
                candidates.append(("local-conflict-repair", repaired, "stable", wolf, wolf))

        if levy_step >= 1.0:
            align_seq = self._soft_align_to_alpha(current_seq, alpha_seq, steps=2)
            if align_seq is not None:
                candidates.append(("global-align", align_seq, "stable", follow_base, follow_base))
        else:
            self._append_sampled_neighbors(
                candidates,
                current_seq,
                operator_name="swap",
                count=2,
                label="local-neighbor-swap",
                decoder="stable",
                decode_base_wolf=wolf,
                eval_base_wolf=wolf,
            )
            self._append_sampled_neighbors(
                candidates,
                current_seq,
                operator_name="insert",
                count=2,
                label="local-neighbor-insert",
                decoder="stable",
                decode_base_wolf=wolf,
                eval_base_wolf=wolf,
            )

        for reverse_idx in range(2):
            reverse_seq = self._short_reverse(current_seq, seg_len_max=4)
            if reverse_seq is not None:
                name = "bounded-reverse" if reverse_idx == 0 else f"bounded-reverse-{reverse_idx + 1}"
                candidates.append((name, reverse_seq, "stable", wolf, wolf))

        prepared_candidates = []
        for name, candidate_seq, decoder, decode_base_wolf, eval_base_wolf in candidates:
            prepared = self._prepare_strategy_candidate(
                name,
                candidate_seq,
                decoder=decoder,
                decode_base_wolf=decode_base_wolf,
                eval_base_wolf=eval_base_wolf,
            )
            if prepared is not None:
                prepared_candidates.append(prepared)

        candidate_best = self._evaluate_strategy_candidates(prepared_candidates, top_k=None)
        candidate_name = getattr(candidate_best, "_candidate_name", None) if candidate_best is not None else None

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(
                f"  [besiege improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f} "
                f"(levy={levy_step:.2f}, {dominant}, {candidate_name})"
            )
            return candidate_best
        return wolf

    def original_scouting(self, wolf, alpha_wolf, max_walks=4):
        """
        Original WPA scouting mapped to a discrete task sequence.

        Original idea:
        - one scout probes h directions
        - each direction is one exploratory step
        - move toward the best direction
        - stop if leader is beaten or max walks is reached
        """
        current_best = wolf
        current_seq = self._flatten_tasks(current_best)
        if len(current_seq) < 2:
            return wolf

        for _ in range(max_walks):
            h = random.randint(4, 8)
            candidate_pool = []

            for _ in range(h):
                operator_name = random.choice(["swap", "insert"])
                candidate_seq = self._neighbor_by_operator(current_seq, operator_name)
                if candidate_seq is None:
                    continue
                candidate_pool.append((f"original-scout-{operator_name}", candidate_seq))

            candidate_best = self._evaluate_task_sequence_candidates(
                current_best,
                candidate_pool,
                top_k=None,
                decoder="stable",
            )

            if candidate_best is None or candidate_best.fitness >= current_best.fitness:
                break

            current_best = candidate_best
            current_seq = self._flatten_tasks(current_best)
            if current_best.fitness < alpha_wolf.fitness:
                break

        return current_best

    def original_summoning(self, wolf, alpha_wolf):
        """
        Original WPA summoning mapped to sequence order attraction.

        Original idea:
        - fierce wolves rush toward the leader with a larger stride
        Here:
        - several tasks are moved toward their leader indices in one update
        """
        wolf_tasks = self._flatten_tasks(wolf)
        alpha_tasks = self._flatten_tasks(alpha_wolf)
        if len(wolf_tasks) < 2 or len(alpha_tasks) != len(wolf_tasks):
            return wolf

        new_seq = self._copy_wolf_tasks(wolf_tasks)
        alpha_pos = self._index_map(alpha_tasks)

        # Pick the task with the largest order mismatch and move it one step
        # toward the leader, which is closer to the paper's fixed stride move.
        mismatched = [
            (abs(idx - alpha_pos[task.id]), idx, task)
            for idx, task in enumerate(new_seq)
            if idx != alpha_pos[task.id]
        ]
        if not mismatched:
            return wolf

        _, current_idx, task = max(mismatched, key=lambda item: item[0])
        target_idx = alpha_pos[task.id]
        direction = 1 if target_idx > current_idx else -1
        next_idx = current_idx + direction

        item = new_seq.pop(current_idx)
        new_seq.insert(next_idx, item)

        candidate_wolf = self._evaluate_task_sequence_candidates(
            wolf,
            [("original-summon", new_seq)],
            top_k=None,
            decoder="stable",
        )
        if candidate_wolf is not None and candidate_wolf.fitness < wolf.fitness:
            return candidate_wolf
        return wolf

    def original_besieging(self, wolf, alpha_wolf):
        """
        Original WPA besieging mapped to local random attack near the leader.

        Original idea:
        - wolves close to the prey perform fine-grained local attacks
        Here:
        - start from the leader sequence and apply one small local perturbation
        """
        wolf_tasks = self._flatten_tasks(wolf)
        alpha_tasks = self._flatten_tasks(alpha_wolf)
        if len(wolf_tasks) < 2 or len(alpha_tasks) != len(wolf_tasks):
            return wolf

        base_seq = self._copy_wolf_tasks(wolf_tasks)
        alpha_pos = self._index_map(alpha_tasks)
        near_leader_indices = [
            idx for idx, task in enumerate(base_seq) if abs(idx - alpha_pos[task.id]) <= 1
        ]
        if len(near_leader_indices) < 2:
            return wolf

        i, j = sorted(random.sample(near_leader_indices, 2))
        if abs(i - j) != 1:
            if i + 1 < len(base_seq):
                j = i + 1
            else:
                i = j - 1

        base_seq[i], base_seq[j] = base_seq[j], base_seq[i]
        candidate_wolf = self._evaluate_task_sequence_candidates(
            wolf,
            [("original-besiege", base_seq)],
            top_k=None,
            decoder="stable",
        )
        if candidate_wolf is not None and candidate_wolf.fitness < wolf.fitness:
            return candidate_wolf
        return wolf
