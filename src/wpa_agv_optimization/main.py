"""
项目主入口（包内）。

阅读顺序建议：
1. parse_args：看参数入口。
2. load_scenario：看固定场景加载规则。
3. main：看完整算法执行流程（环境构建 -> 初始化 -> 迭代 -> 输出）。
"""

import argparse
import random

import numpy as np

from .config import Config
from .evaluator import WolfEvaluator
from .initializer import PopulationInitializer
from .models import Task
from .scenario_inputs import SCENARIO_LIBRARY
from .utils import generate_grid_map
from .wpa_ops import WPAOperators


def list_scenarios():
    """打印固定场景列表。"""
    print("可用固定输入场景：")
    for idx, scenario in enumerate(SCENARIO_LIBRARY, start=1):
        print(f"  {idx}. {scenario['name']} - {scenario['description']}")


def load_scenario(scenario_index):
    """
    按编号加载固定场景。

    返回：
    - grid_map: 场景地图（含障碍）。
    - task_list: Task 列表。
    - scenario_name: 场景名称。
    """
    if scenario_index < 1 or scenario_index > len(SCENARIO_LIBRARY):
        raise ValueError(f"场景编号无效: {scenario_index}")

    scenario = SCENARIO_LIBRARY[scenario_index - 1]
    grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)

    # 按场景障碍坐标写入地图。
    for x, y in scenario["obstacles"]:
        if 0 <= x < Config.MAP_WIDTH and 0 <= y < Config.MAP_HEIGHT:
            if x != 0 and (x, y) != Config.DEPOT_NODE:
                grid_map[x][y] = 1

    # 构造任务对象列表。
    task_list = []
    for i, item in enumerate(scenario["tasks"], start=1):
        tx, ty = item["x"], item["y"]
        if grid_map[tx][ty] == 1:
            raise ValueError(f"场景[{scenario_index}]任务落在障碍物上: ({tx},{ty})")
        task = Task(i, tx, ty, item["weight"], item["deadline"])
        task_list.append(task)

    return grid_map, task_list, scenario["name"]


def parse_args():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="多AGV狼群算法调度仿真")
    parser.add_argument(
        "--scenario",
        type=int,
        default=None,
        help="固定输入场景编号（从1开始）。不填则交互选择或随机任务。",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="仅显示固定场景列表并退出。",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="随机种子。传入后结果可复现。",
    )
    return parser.parse_args()


def main():
    """程序主流程。"""
    args = parse_args()
    if args.list_scenarios:
        list_scenarios()
        return

    # 若用户指定随机种子，则固定 Python 与 NumPy 的随机行为。
    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        print(f"=== 0. 固定随机种子 seed={args.seed} ===")

    # ===================== Step1: 环境与任务构建 =====================
    print("=== 1. 仓储环境与任务构建 ===")
    selected_scenario = args.scenario
    if selected_scenario is None:
        list_scenarios()
        raw = input("请输入场景编号（直接回车使用随机输入）：").strip()
        if raw:
            try:
                selected_scenario = int(raw)
            except ValueError:
                selected_scenario = None
                print("  > 场景编号解析失败，自动切换为随机输入模式。")

    if selected_scenario is not None:
        try:
            grid_map, task_list, scenario_name = load_scenario(selected_scenario)
            print(f"  > 使用固定场景 #{selected_scenario}: {scenario_name}")
            print(f"  > 成功加载 {len(task_list)} 个固定任务")
        except ValueError as e:
            print(f"  > 固定场景加载失败：{e}")
            return
    else:
        grid_map = generate_grid_map()
        task_list = []
        task_num = 15
        for i in range(task_num):
            while True:
                tx, ty = random.randint(1, 19), random.randint(1, 19)
                if grid_map[tx][ty] == 0:
                    break
            t = Task(i + 1, tx, ty, random.randint(10, 40), random.randint(50, 300))
            task_list.append(t)
        print(f"  > 成功生成 {len(task_list)} 个随机取货任务")

    # ===================== Step2: 种群初始化 =====================
    print("\n=== 2. 狼群种群初始化 ===")
    initializer = PopulationInitializer(grid_map, task_list)
    population = initializer.generate_population()
    population.sort(key=lambda w: w.fitness)
    alpha_wolf = population[0]
    print("  > 初始头狼生成完成")
    print(
        f"    适应度F={alpha_wolf.fitness:.2f} | 使用车辆数N={alpha_wolf.vehicle_num} | "
        f"总行驶距离D={alpha_wolf.total_dist} | 时间窗惩罚T={alpha_wolf.time_penalty}"
    )

    # ===================== Step3: 算法参数 =====================
    MAX_ITER = 50
    SCOUTS_NUM = 5
    evaluator = WolfEvaluator(grid_map)
    operators = WPAOperators(evaluator)
    global_best_wolf = alpha_wolf

    # ===================== Step4: 主迭代 =====================
    print(f"\n=== 3. 开始狼群算法迭代，最大迭代次数={MAX_ITER} ===")
    for iter_idx in range(MAX_ITER):
        print(f"\n--- 第 {iter_idx + 1}/{MAX_ITER} 代迭代开始 ---")

        # 4.1 游走：前 SCOUTS_NUM 只探狼执行局部探索。
        print("> 探狼执行游走行为...")
        for i in range(SCOUTS_NUM):
            wolf = population[i]
            new_wolf = operators.scouting(wolf)
            population[i] = new_wolf
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
            print(f"> 游走后更新全局最优解！新F={global_best_wolf.fitness:.2f}")

        # 4.2 召唤：其余个体向头狼靠拢学习。
        print("> 猛狼执行召唤行为...")
        for i in range(SCOUTS_NUM, len(population)):
            wolf = population[i]
            new_wolf = operators.summoning(wolf, global_best_wolf)
            population[i] = new_wolf
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
            print(f"> 召唤后更新全局最优解！新F={global_best_wolf.fitness:.2f}")

        # 4.3 围攻：全群局部开发+全局跳变（头狼保护）。
        print("> 全种群执行围攻行为...")
        for i in range(1, len(population)):
            wolf = population[i]
            new_wolf = operators.besieging(wolf, iter_idx, MAX_ITER)
            population[i] = new_wolf
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
            print(f"> 围攻后更新全局最优解！新F={global_best_wolf.fitness:.2f}")

        # 4.4 优胜劣汰：淘汰末尾个体并补充新个体，维持多样性。
        print("> 执行种群优胜劣汰...")
        population = population[:-2]
        for _ in range(2):
            new_wolf = initializer._create_one_wolf()
            population.append(new_wolf)

        # 迭代末汇报。
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
        print(f"--- 第 {iter_idx + 1}/{MAX_ITER} 代迭代结束 ---")
        print(f"    当前代最优F={current_alpha.fitness:.2f} | 全局最优F={global_best_wolf.fitness:.2f}")
        print(
            f"    全局最优指标：车辆数N={global_best_wolf.vehicle_num} | "
            f"总距离D={global_best_wolf.total_dist} | 时间惩罚T={global_best_wolf.time_penalty}"
        )

    # ===================== Step5: 最终输出 =====================
    print("\n=== 4. 算法迭代结束，最终优化结果 ===")
    print("  全局最优调度方案核心指标：")
    print(f"    多目标适应度F={global_best_wolf.fitness:.2f}")
    print(f"    使用AGV车辆数N={global_best_wolf.vehicle_num}")
    print(f"    系统总行驶距离D={global_best_wolf.total_dist} 格")
    print(f"    时间窗总惩罚T={global_best_wolf.time_penalty} 秒")
    print("  冲突/死锁统计：")
    print(f"    冲突处理次数={getattr(global_best_wolf, 'conflict_count', 0)}")
    print(f"    死锁解锁次数={getattr(global_best_wolf, 'deadlock_count', 0)}")
    print(f"    重规划触发次数={getattr(global_best_wolf, 'replan_count', 0)}")
    print("  方案详情：")
    for agv in global_best_wolf.agv_list:
        print(
            f"    AGV-{agv.id}：任务数={len(agv.tasks)} | "
            f"最终载重={agv.load}kg | 完成时间={agv.finish_time}秒"
        )
        print(f"      任务执行顺序：{agv.tasks}")


if __name__ == "__main__":
    main()

