"""Package entry point and reusable execution helpers for the AGV WPA project."""

from __future__ import annotations

import argparse
import contextlib
import os
import random
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .config import Config
from .evaluator import WolfEvaluator
from .exporter import export_result_json
from .initializer import PopulationInitializer
from .models import Task
from .original_wpa import OriginalWPAConfig, OriginalWPAOptimizer
from .scenario_inputs import SCENARIO_LIBRARY
from .utils import generate_grid_map, is_valid_pick_location
from .wpa_ops import WPAOperators


@dataclass
class RunResult:
    """Structured result returned by one full algorithm run."""

    algorithm: str
    scenario: int | None
    scenario_name: str
    seed: int | None
    fitness: float
    vehicle_num: int
    total_dist: int
    time_penalty: float
    conflict_count: int
    deadlock_count: int
    deadlock_risk_count: int
    replan_count: int
    reroute_count: int
    unfinished_count: int
    wolf: Any


@contextlib.contextmanager
def _suppress_stdout(enabled: bool):
    """Suppress all stdout when benchmark workers run in quiet mode."""
    if not enabled:
        yield
        return
    with open(os.devnull, "w", encoding="utf-8") as devnull, contextlib.redirect_stdout(devnull):
        yield



def list_scenarios() -> None:
    """Print all fixed benchmark scenarios."""
    print("可用固定输入场景：")
    for idx, scenario in enumerate(SCENARIO_LIBRARY, start=1):
        print(f"  {idx}. {scenario['name']} - {scenario['description']}")



def load_scenario(scenario_index: int):
    """Load one fixed scenario by 1-based index."""
    if scenario_index < 1 or scenario_index > len(SCENARIO_LIBRARY):
        raise ValueError(f"场景编号无效: {scenario_index}")

    scenario = SCENARIO_LIBRARY[scenario_index - 1]
    grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)

    obstacles: set[tuple[int, int]] = set()
    for x, y in scenario["obstacles"]:
        if 0 <= x < Config.MAP_WIDTH and 0 <= y < Config.MAP_HEIGHT:
            if x != 0 and (x, y) != Config.DEPOT_NODE:
                grid_map[x][y] = 1
                obstacles.add((x, y))

    task_list = []
    for i, item in enumerate(scenario["tasks"], start=1):
        tx, ty = item["x"], item["y"]
        if grid_map[tx][ty] == 1:
            raise ValueError(f"场景[{scenario_index}]任务落在障碍物上: ({tx},{ty})")
        if not is_valid_pick_location((tx, ty), obstacles):
            raise ValueError(
                f"场景[{scenario_index}]任务#{i} ({tx},{ty}) 未贴货架："
                "任务必须位于至少一个 4-邻居为障碍（货架）的格子。"
            )
        task_list.append(Task(i, tx, ty, item["weight"], item["deadline"]))

    return grid_map, task_list, scenario["name"]



def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
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
    parser.add_argument(
        "--algorithm",
        choices=["improved", "original"],
        default="improved",
        help="算法版本：improved 为当前改进版，original 为论文严格对应的原始WPA版。",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默运行，仅输出最终结果。",
    )
    return parser.parse_args()



def build_random_tasks(grid_map):
    """Generate a random task set when no fixed scenario is selected."""
    width, height = grid_map.shape
    obstacles = {(x, y) for x in range(width) for y in range(height) if grid_map[x][y] == 1}
    valid_cells = [
        (x, y)
        for x in range(1, width)
        for y in range(height)
        if is_valid_pick_location((x, y), obstacles)
    ]
    if not valid_cells:
        raise ValueError("随机地图上没有任何贴货架的合法任务位置，请调高障碍密度或重生成地图。")

    task_list = []
    task_num = 15
    max_attempts = task_num * 50
    chosen: set[tuple[int, int]] = set()
    attempts = 0
    while len(task_list) < task_num:
        attempts += 1
        if attempts > max_attempts:
            raise ValueError(
                f"随机任务采样失败：{max_attempts} 次尝试内无法凑齐 {task_num} 个互不重复的贴货架任务位。"
            )
        tx, ty = random.choice(valid_cells)
        if (tx, ty) in chosen:
            continue
        chosen.add((tx, ty))
        task_list.append(Task(len(task_list) + 1, tx, ty, random.randint(10, 40), random.randint(50, 300)))
    return task_list



def run_iteration_improved(population, operators, initializer, global_best_wolf, iter_idx, max_iter, scouts_num):
    """Run one iteration of the improved WPA."""
    print("> 探狼执行游走行为...")
    for i in range(scouts_num):
        population[i] = operators.scouting(population[i])
    population.sort(key=lambda w: w.fitness)
    current_alpha = population[0]
    if current_alpha.fitness < global_best_wolf.fitness:
        global_best_wolf = current_alpha
        print(f"> 游走后更新全局最优解，新F={global_best_wolf.fitness:.2f}")

    print("> 猛狼执行召唤行为...")
    for i in range(scouts_num, len(population)):
        population[i] = operators.summoning(population[i], global_best_wolf)
    population.sort(key=lambda w: w.fitness)
    current_alpha = population[0]
    if current_alpha.fitness < global_best_wolf.fitness:
        global_best_wolf = current_alpha
        print(f"> 召唤后更新全局最优解，新F={global_best_wolf.fitness:.2f}")

    print("> 全种群执行围攻行为...")
    for i in range(1, len(population)):
        population[i] = operators.besieging(population[i], global_best_wolf, iter_idx, max_iter)
    population.sort(key=lambda w: w.fitness)
    current_alpha = population[0]
    if current_alpha.fitness < global_best_wolf.fitness:
        global_best_wolf = current_alpha
        print(f"> 围攻后更新全局最优解，新F={global_best_wolf.fitness:.2f}")

    print("> 执行种群优胜劣汰...")
    population = population[:-2]
    for _ in range(2):
        population.append(initializer._create_one_wolf())

    population.sort(key=lambda w: w.fitness)
    current_alpha = population[0]
    if current_alpha.fitness < global_best_wolf.fitness:
        global_best_wolf = current_alpha
    return population, global_best_wolf



def _run_original_paper_algorithm(grid_map, task_list, max_iter, *, verbose: bool):
    """Run the paper-faithful original WPA with minimal discrete decoding."""
    evaluator = WolfEvaluator(grid_map)
    rng = random
    optimizer = OriginalWPAOptimizer(
        grid_map,
        task_list,
        evaluator=evaluator,
        config=OriginalWPAConfig(),
        rng=rng,
    )
    result = optimizer.run(max_iter=max_iter, pop_size=Config.POP_SIZE, verbose=verbose)
    return result.best_wolf, result.convergence



def _run_algorithm_impl(
    scenario: int | None,
    seed: int | None,
    algorithm: str,
    allow_interactive: bool,
    *,
    export_json: bool,
    export_output_path: str | None,
    variant_key: str | None,
) -> RunResult:
    """Execute one full optimization run and return the final structured result."""
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        print(f"=== 0. 固定随机种子 seed={seed} ===")

    print("=== 1. 仓储环境与任务构建 ===")
    selected_scenario = scenario
    if selected_scenario is None and allow_interactive:
        list_scenarios()
        raw = input("请输入场景编号（直接回车使用随机输入）：").strip()
        if raw:
            try:
                selected_scenario = int(raw)
            except ValueError:
                selected_scenario = None
                print("  > 场景编号解析失败，自动切换为随机输入模式。")

    if selected_scenario is not None:
        grid_map, task_list, scenario_name = load_scenario(selected_scenario)
        print(f"  > 使用固定场景 #{selected_scenario}: {scenario_name}")
        print(f"  > 成功加载 {len(task_list)} 个固定任务")
    else:
        grid_map = generate_grid_map()
        task_list = build_random_tasks(grid_map)
        scenario_name = "随机任务"
        print(f"  > 成功生成 {len(task_list)} 个随机任务")

    max_iter = 50
    convergence = []

    if algorithm == "original":
        print("\n=== 2. 原始WPA连续状态初始化 ===")
        global_best_wolf, convergence = _run_original_paper_algorithm(
            grid_map,
            task_list,
            max_iter,
            verbose=True,
        )
    else:
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

        scouts_num = 5
        evaluator = WolfEvaluator(grid_map)
        operators = WPAOperators(evaluator)
        global_best_wolf = alpha_wolf

        print(f"\n=== 3. 开始狼群算法迭代，算法版本={algorithm}，最大迭代次数={max_iter} ===")
        for iter_idx in range(max_iter):
            print(f"\n--- 第 {iter_idx + 1}/{max_iter} 代迭代开始 ---")
            population, global_best_wolf = run_iteration_improved(
                population,
                operators,
                initializer,
                global_best_wolf,
                iter_idx,
                max_iter,
                scouts_num,
            )

            current_alpha = population[0]
            convergence.append({"iter": iter_idx + 1, "best_fitness": round(float(global_best_wolf.fitness), 2)})

            print(f"--- 第 {iter_idx + 1}/{max_iter} 代迭代结束 ---")
            print(f"    当前代最优F={current_alpha.fitness:.2f} | 全局最优F={global_best_wolf.fitness:.2f}")
            print(
                f"    全局最优指标：车辆数N={global_best_wolf.vehicle_num} | "
                f"总距离D={global_best_wolf.total_dist} | 时间惩罚T={global_best_wolf.time_penalty}"
            )

    print("\n=== 4. 算法迭代结束，最终优化结果 ===")
    print(f"  算法版本：{algorithm}")
    print("  全局最优调度方案核心指标：")
    print(f"    多目标适应度F={global_best_wolf.fitness:.2f}")
    print(f"    使用AGV车辆数N={global_best_wolf.vehicle_num}")
    print(f"    系统总行驶距离D={global_best_wolf.total_dist} 格")
    print(f"    时间窗总惩罚T={global_best_wolf.time_penalty} 秒")
    print("  冲突/死锁统计：")
    print(f"    冲突处理次数={getattr(global_best_wolf, 'conflict_count', 0)}")
    print(f"    死锁解锁次数={getattr(global_best_wolf, 'deadlock_count', 0)}")
    print(f"    准死锁风险触发次数={getattr(global_best_wolf, 'deadlock_risk_count', 0)}")
    print(f"    重规划触发次数={getattr(global_best_wolf, 'replan_count', 0)}")
    print(f"    局部改道触发次数={getattr(global_best_wolf, 'reroute_count', 0)}")
    print(f"    未完成客户任务数={getattr(global_best_wolf, 'unfinished_count', 0)}")
    print("  方案详情：")
    for agv in global_best_wolf.agv_list:
        print(
            f"    AGV-{agv.id}：任务数={len(agv.tasks)} | 最终载重={agv.load}kg | 完成时间={agv.finish_time}秒"
        )
        print(f"      任务执行顺序：{agv.tasks}")

    if export_json:
        json_path = export_result_json(
            wolf=global_best_wolf,
            grid_map=grid_map,
            task_list=task_list,
            convergence=convergence,
            scenario_name=scenario_name,
            algorithm=algorithm,
            seed=seed,
            output_path=export_output_path,
            variant_key=variant_key or algorithm,
        )
        print(f"\n  前端可视化数据已导出到: {json_path}")

    return RunResult(
        algorithm=algorithm,
        scenario=selected_scenario,
        scenario_name=scenario_name,
        seed=seed,
        fitness=float(global_best_wolf.fitness),
        vehicle_num=int(global_best_wolf.vehicle_num),
        total_dist=int(global_best_wolf.total_dist),
        time_penalty=float(global_best_wolf.time_penalty),
        conflict_count=int(getattr(global_best_wolf, "conflict_count", 0)),
        deadlock_count=int(getattr(global_best_wolf, "deadlock_count", 0)),
        deadlock_risk_count=int(getattr(global_best_wolf, "deadlock_risk_count", 0)),
        replan_count=int(getattr(global_best_wolf, "replan_count", 0)),
        reroute_count=int(getattr(global_best_wolf, "reroute_count", 0)),
        unfinished_count=int(getattr(global_best_wolf, "unfinished_count", 0)),
        wolf=global_best_wolf,
    )



def run_algorithm(
    scenario: int | None = None,
    seed: int | None = None,
    algorithm: str = "improved",
    *,
    verbose: bool = True,
    allow_interactive: bool = False,
    export_json: bool = True,
    export_output_path: str | None = None,
    variant_key: str | None = None,
) -> RunResult:
    """Reusable API for one run.

    Benchmark workers call this function directly to avoid subprocess startup and
    stdout parsing overhead.
    """
    with _suppress_stdout(not verbose):
        return _run_algorithm_impl(
            scenario,
            seed,
            algorithm,
            allow_interactive,
            export_json=export_json,
            export_output_path=export_output_path,
            variant_key=variant_key,
        )



def result_to_metrics(result: RunResult) -> dict[str, float | int | str | None]:
    """Convert a run result to the benchmark metric shape."""
    data = asdict(result)
    data["F"] = data.pop("fitness")
    data["N"] = data.pop("vehicle_num")
    data["D"] = data.pop("total_dist")
    data["T"] = data.pop("time_penalty")
    data.pop("wolf", None)
    return data



def main() -> None:
    """CLI entry point."""
    args = parse_args()
    if args.list_scenarios:
        list_scenarios()
        return
    run_algorithm(
        scenario=args.scenario,
        seed=args.seed,
        algorithm=args.algorithm,
        verbose=not args.quiet,
        allow_interactive=True,
    )


if __name__ == "__main__":
    main()
