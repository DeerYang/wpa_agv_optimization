# wpa_ops.py
import random
import copy
from config import Config


class WPAOperators:
    def __init__(self, evaluator):
        self.evaluator = evaluator  # 引入评估器

    def scouting(self, wolf):
        """
        [游走行为 - Scouting]
        模拟探狼对当前方案的微调：随机交换某一辆车内部的两个任务执行顺序。
        """
        # 1. 深拷贝当前狼 (不能修改原狼，因为如果改坏了要撤销)
        new_wolf = copy.deepcopy(wolf)

        # 2. 随机选择一辆有任务的 AGV
        active_agvs = [agv for agv in new_wolf.agv_list if len(agv.tasks) >= 2]

        if not active_agvs:
            return wolf  # 如果所有车都只有0或1个任务，没法交换，直接返回原狼

        target_agv = random.choice(active_agvs)

        # 3. 执行任务交换 (Task Swap) - 这就是"向邻域游走"
        # 随机选两个任务索引
        idx1, idx2 = random.sample(range(len(target_agv.tasks)), 2)
        # 交换位置
        target_agv.tasks[idx1], target_agv.tasks[idx2] = target_agv.tasks[idx2], target_agv.tasks[idx1]

        # 4. 重新规划路径并算分 (因为任务顺序变了，路径必须重算)
        # 注意：这里会重新调用 Tent-DFS，所以即使任务没变，路径也可能因为 Tent 混沌值不同而产生有益的扰动
        new_wolf = self.evaluator.rebuild_wolf(new_wolf)

        # 5. 贪婪判断：如果变好了，就更新；否则保持原样
        if new_wolf.fitness < wolf.fitness:
            print(f"  [游走成功] F值优化: {wolf.fitness:.1f} -> {new_wolf.fitness:.1f}")
            return new_wolf
        else:
            return wolf