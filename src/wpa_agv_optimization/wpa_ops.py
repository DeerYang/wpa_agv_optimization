"""
WPA operator module.

This file contains two operator sets that share the same evaluator:
1. Improved operators: the current project version.
2. Original operators: a discrete mapping of the original WPA paper.

Both variants reuse the same evaluation, path planning, and conflict handling
pipeline so benchmark comparisons stay fair.
"""

import copy
import random

import numpy as np
from scipy.special import gamma

from .config import Config
from .models import AGV
from .utils import manhattan_dist


class WPAOperators:
    """Collection of improved and original WPA operators."""

    def __init__(self, evaluator):
        self.evaluator = evaluator

    def _flatten_tasks(self, wolf):
        """Flatten all AGV task lists into one global sequence."""
        seq = []
        for agv in wolf.agv_list:
            seq.extend(agv.tasks)
        return seq

    @staticmethod
    def _copy_wolf_tasks(task_seq):
        """Return a safe shallow copy for sequence reordering."""
        return list(task_seq)

    @staticmethod
    def _index_map(task_seq):
        """Build a task id to index mapping."""
        return {task.id: idx for idx, task in enumerate(task_seq)}

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

    def _rebuild_from_task_sequence(self, base_wolf, task_seq, decoder="cost_based"):
        """Decode, rebuild routes, and return a new evaluated wolf."""
        new_wolf = copy.deepcopy(base_wolf)
        if decoder == "simple":
            decoded_agvs = self._decode_sequence_to_agvs(task_seq)
        else:
            decoded_agvs = self._decode_sequence_to_agvs_cost_based(task_seq)
        if decoded_agvs is None:
            return None
        new_wolf.agv_list = decoded_agvs
        return self.evaluator.rebuild_wolf(new_wolf)

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

    def scouting(self, wolf):
        """Improved scouting: multi-direction discrete probing with择优接受."""
        current_seq = self._flatten_tasks(wolf)
        if len(current_seq) < 2:
            return wolf

        candidate_best = None
        for operator_name in ["swap", "insert", "reverse"]:
            candidate_seq = self._neighbor_by_operator(current_seq, operator_name)
            if candidate_seq is None:
                continue
            candidate_wolf = self._rebuild_from_task_sequence(wolf, candidate_seq, decoder="cost_based")
            if candidate_wolf is None:
                continue
            if (candidate_best is None) or (candidate_wolf.fitness < candidate_best.fitness):
                candidate_best = candidate_wolf

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(f"  [scout improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f}")
            return candidate_best
        return wolf

    def summoning(self, wolf, alpha_wolf):
        """Improved summoning: short OX inheritance plus soft leader alignment."""
        alpha_copy = copy.deepcopy(alpha_wolf)
        if not alpha_copy.agv_list or not wolf.agv_list:
            return wolf
        if random.random() > 0.75:
            return wolf

        alpha_tasks = self._flatten_tasks(alpha_copy)
        wolf_tasks = self._flatten_tasks(wolf)
        if len(alpha_tasks) < 2 or len(wolf_tasks) < 2:
            return wolf

        candidates = []

        ox_seq = self._ox_inherit(wolf_tasks, alpha_tasks, seg_len_min=2, seg_len_max=3)
        if ox_seq is not None:
            candidates.append(("ox", ox_seq))

        align_seq = self._soft_align_to_alpha(wolf_tasks, alpha_tasks, steps=2)
        if align_seq is not None:
            candidates.append(("align", align_seq))

        if ox_seq is not None:
            ox_align_seq = self._soft_align_to_alpha(ox_seq, alpha_tasks, steps=1)
            if ox_align_seq is not None:
                candidates.append(("ox+align", ox_align_seq))

        candidate_best = None
        candidate_name = None
        for name, candidate_seq in candidates:
            candidate_wolf = self._rebuild_from_task_sequence(wolf, candidate_seq, decoder="cost_based")
            if candidate_wolf is None:
                continue
            if (candidate_best is None) or (candidate_wolf.fitness < candidate_best.fitness):
                candidate_best = candidate_wolf
                candidate_name = name

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(f"  [summon improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f} ({candidate_name})")
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
        """Improved besieging: constrained Levy-guided local/global refinement."""
        current_seq = self._flatten_tasks(wolf)
        alpha_seq = self._flatten_tasks(alpha_wolf)
        if len(current_seq) < 2 or len(current_seq) != len(alpha_seq):
            return wolf
        if random.random() > 0.8:
            return wolf

        step_scale = 2.0 * (1 - curr_iter / max_iter)
        levy_step = self._levy_flight_step(step_scale=step_scale)
        step_threshold = 1.0

        candidates = []
        if levy_step < step_threshold:
            align_seq = self._soft_align_to_alpha(current_seq, alpha_seq, steps=1)
            if align_seq is not None:
                candidates.append(("local-align", align_seq))
            swap_seq = self._neighbor_by_operator(current_seq, random.choice(["swap", "insert"]))
            if swap_seq is not None:
                candidates.append(("local-neighbor", swap_seq))
        else:
            align_seq = self._soft_align_to_alpha(current_seq, alpha_seq, steps=2)
            if align_seq is not None:
                candidates.append(("global-align", align_seq))
            reverse_seq = self._short_reverse(current_seq, seg_len_max=4)
            if reverse_seq is not None:
                candidates.append(("bounded-reverse", reverse_seq))

        candidate_best = None
        candidate_name = None
        for name, candidate_seq in candidates:
            candidate_wolf = self._rebuild_from_task_sequence(wolf, candidate_seq, decoder="cost_based")
            if candidate_wolf is None:
                continue
            if (candidate_best is None) or (candidate_wolf.fitness < candidate_best.fitness):
                candidate_best = candidate_wolf
                candidate_name = name

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(
                f"  [besiege improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f} "
                f"(levy={levy_step:.2f}, {candidate_name})"
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
            candidate_best = None

            for _ in range(h):
                operator_name = random.choice(["swap", "insert"])
                candidate_seq = self._neighbor_by_operator(current_seq, operator_name)
                if candidate_seq is None:
                    continue
                candidate_wolf = self._rebuild_from_task_sequence(current_best, candidate_seq, decoder="simple")
                if candidate_wolf is None:
                    continue
                if (candidate_best is None) or (candidate_wolf.fitness < candidate_best.fitness):
                    candidate_best = candidate_wolf

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

        candidate_wolf = self._rebuild_from_task_sequence(wolf, new_seq, decoder="simple")
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
        candidate_wolf = self._rebuild_from_task_sequence(wolf, base_seq, decoder="simple")
        if candidate_wolf is not None and candidate_wolf.fitness < wolf.fitness:
            return candidate_wolf
        return wolf
