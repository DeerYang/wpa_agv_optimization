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
from .models import AGV, Wolf
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

    def scouting(self, wolf):
        """Improved scouting: bottleneck-guided multi-direction discrete probing."""
        current_seq = self._flatten_tasks(wolf)
        if len(current_seq) < 2:
            return wolf

        focus_ids = self._bottleneck_task_ids(wolf)
        use_heavy_structure = wolf.vehicle_num >= 5
        candidates = []

        if use_heavy_structure:
            guided_reinsert = self._guided_reinsert_by_risk(current_seq, focus_ids=focus_ids, top_k=3)
            if guided_reinsert is not None:
                candidates.append(("bottleneck-reinsert", guided_reinsert))

            pull_forward = self._pull_forward_high_risk_task(current_seq, focus_ids=focus_ids, step_cap=3)
            if pull_forward is not None:
                candidates.append(("deadline-pull", pull_forward))

            cross_swap = self._swap_across_regions(current_seq, focus_ids=focus_ids)
            if cross_swap is not None:
                candidates.append(("cross-region-swap", cross_swap))

        random_swap = self._neighbor_by_operator(current_seq, "swap")
        if random_swap is not None:
            candidates.append(("random-swap", random_swap))

        random_insert = self._neighbor_by_operator(current_seq, "insert")
        if random_insert is not None:
            candidates.append(("random-insert", random_insert))

        reverse_seq = self._neighbor_by_operator(current_seq, "reverse")
        if reverse_seq is not None:
            candidates.append(("reverse", reverse_seq))

        prepared_candidates = []
        for name, candidate_seq in candidates:
            prepared = self._prepare_candidate(name, candidate_seq, decoder="stable", base_wolf=wolf)
            if prepared is not None:
                prepared_candidates.append(prepared)

        candidate_best = self._evaluate_prepared_candidates(
            prepared_candidates=prepared_candidates,
            strict_eval=lambda name, decoded_agvs: self._strict_candidate_from_agvs(wolf, name, decoded_agvs),
            top_k=None,
        )
        candidate_name = getattr(candidate_best, "_candidate_name", None) if candidate_best is not None else None

        if candidate_best is not None and candidate_best.fitness < wolf.fitness:
            print(
                f"  [scout improved] F {wolf.fitness:.1f} -> {candidate_best.fitness:.1f} "
                f"({candidate_name})"
            )
            return candidate_best
        return wolf

    def summoning(self, wolf, alpha_wolf):
        """Improved summoning: cluster inheritance with cost-based structural decoding."""
        alpha_copy = copy.deepcopy(alpha_wolf)
        if not alpha_copy.agv_list or not wolf.agv_list:
            return wolf
        if random.random() > 0.8:
            return wolf

        alpha_tasks = self._flatten_tasks(alpha_copy)
        wolf_tasks = self._flatten_tasks(wolf)
        if len(alpha_tasks) < 2 or len(wolf_tasks) < 2:
            return wolf

        use_heavy_structure = wolf.vehicle_num >= 4
        alpha_cluster = self._choose_alpha_cluster(alpha_copy, seg_len_min=2, seg_len_max=4) if use_heavy_structure else None
        focus_ids = {task.id for task in alpha_cluster} if alpha_cluster else set()
        candidates = []

        ox_seq = self._ox_inherit(wolf_tasks, alpha_tasks, seg_len_min=2, seg_len_max=3)
        if ox_seq is not None:
            candidates.append(("ox", ox_seq))

        if use_heavy_structure:
            cluster_seq = self._inherit_cluster_sequence(wolf_tasks, alpha_tasks, alpha_cluster)
            if cluster_seq is not None:
                candidates.append(("cluster-inherit", cluster_seq))
        else:
            cluster_seq = None

        align_seq = self._soft_align_to_alpha(wolf_tasks, alpha_tasks, steps=2)
        if align_seq is not None:
            candidates.append(("align", align_seq))

        if cluster_seq is not None:
            cluster_align_seq = self._soft_align_to_alpha(cluster_seq, alpha_tasks, steps=2)
            if cluster_align_seq is not None:
                candidates.append(("cluster+align", cluster_align_seq))

            cluster_repair_seq = self._guided_reinsert_by_risk(cluster_seq, focus_ids=focus_ids, top_k=2)
            if cluster_repair_seq is not None:
                candidates.append(("cluster+repair", cluster_repair_seq))

        if ox_seq is not None:
            ox_align_seq = self._soft_align_to_alpha(ox_seq, alpha_tasks, steps=1)
            if ox_align_seq is not None:
                candidates.append(("ox+align", ox_align_seq))

        prepared_candidates = []
        for name, candidate_seq in candidates:
            prepared = self._prepare_candidate(name, candidate_seq, decoder="stable", base_wolf=wolf)
            if prepared is not None:
                prepared_candidates.append(prepared)

        candidate_best = self._evaluate_prepared_candidates(
            prepared_candidates=prepared_candidates,
            strict_eval=lambda name, decoded_agvs: self._strict_candidate_from_agvs(wolf, name, decoded_agvs),
            top_k=None,
        )
        candidate_name = getattr(candidate_best, "_candidate_name", None) if candidate_best is not None else None

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
        """Improved besieging: Levy-driven dual-mode local refinement and destroy-repair."""
        current_seq = self._flatten_tasks(wolf)
        alpha_seq = self._flatten_tasks(alpha_wolf)
        if len(current_seq) < 2 or len(current_seq) != len(alpha_seq):
            return wolf
        if random.random() > 0.85:
            return wolf

        step_scale = 2.0 * (1 - curr_iter / max_iter)
        levy_step = self._levy_flight_step(step_scale=step_scale)
        step_threshold = 1.15
        focus_ids = self._bottleneck_task_ids(wolf)
        use_heavy_structure = wolf.vehicle_num >= 5

        candidates = []
        if levy_step < step_threshold:
            align_seq = self._soft_align_to_alpha(current_seq, alpha_seq, steps=1)
            if align_seq is not None:
                candidates.append(("local-align", align_seq))

            if use_heavy_structure:
                local_reinsert = self._guided_reinsert_by_risk(current_seq, focus_ids=focus_ids, top_k=2)
                if local_reinsert is not None:
                    candidates.append(("local-reinsert", local_reinsert))

                pull_forward = self._pull_forward_high_risk_task(current_seq, focus_ids=focus_ids, step_cap=2)
                if pull_forward is not None:
                    candidates.append(("local-pull", pull_forward))

            local_neighbor = self._neighbor_by_operator(current_seq, random.choice(["swap", "insert"]))
            if local_neighbor is not None:
                candidates.append(("local-neighbor", local_neighbor))
        else:
            align_seq = self._soft_align_to_alpha(current_seq, alpha_seq, steps=2)
            if align_seq is not None:
                candidates.append(("global-align", align_seq))

            if use_heavy_structure:
                repair_seq = self._destroy_repair_sequence(current_seq, focus_ids=focus_ids, remove_count=2)
                if repair_seq is not None:
                    candidates.append(("destroy-repair-2", repair_seq))

                if curr_iter >= max_iter // 3:
                    repair_heavy_seq = self._destroy_repair_sequence(
                        current_seq,
                        focus_ids=focus_ids,
                        remove_count=3,
                    )
                    if repair_heavy_seq is not None:
                        candidates.append(("destroy-repair-3", repair_heavy_seq))

            reverse_seq = self._short_reverse(current_seq, seg_len_max=4)
            if reverse_seq is not None:
                candidates.append(("bounded-reverse", reverse_seq))

        prepared_candidates = []
        for name, candidate_seq in candidates:
            prepared = self._prepare_candidate(name, candidate_seq, decoder="stable", base_wolf=wolf)
            if prepared is not None:
                prepared_candidates.append(prepared)

        candidate_best = self._evaluate_prepared_candidates(
            prepared_candidates=prepared_candidates,
            strict_eval=lambda name, decoded_agvs: self._strict_candidate_from_agvs(wolf, name, decoded_agvs),
            top_k=None,
        )
        candidate_name = getattr(candidate_best, "_candidate_name", None) if candidate_best is not None else None

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
