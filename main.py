# main.py (更新版)
import random
from config import Config
from models import Task
from utils import generate_grid_map
from initializer import PopulationInitializer
from evaluator import WolfEvaluator
from wpa_ops import WPAOperators


def main():
    print("=== 1. 环境构建 ===")
    grid_map = generate_grid_map()

    task_list = []
    for i in range(15):
        while True:
            tx, ty = random.randint(1, 19), random.randint(1, 19)
            if grid_map[tx][ty] == 0: break
        t = Task(i + 1, tx, ty, random.randint(10, 40), random.randint(50, 300))
        task_list.append(t)
    print(f"  > 生成 {len(task_list)} 个任务")

    # --- 初始化 ---
    print("\n=== 2. 狼群初始化 ===")
    initializer = PopulationInitializer(grid_map, task_list)
    population = initializer.generate_population()

    # 选出初始头狼
    population.sort(key=lambda w: w.fitness)
    alpha_wolf = population[0]
    print(f"  > 初始头狼 F={alpha_wolf.fitness:.2f}")

    # --- 准备 WPA 算子 ---
    evaluator = WolfEvaluator(grid_map)
    operators = WPAOperators(evaluator)

    # --- 开始迭代 (这里演示 1 代游走) ---
    print("\n=== 3. 执行游走行为 (Scouting) ===")
    # 假设前 5 只狼是探狼 (Top-k)
    scouts_num = 5

    for i in range(scouts_num):
        wolf = population[i]
        print(f"  > 探狼 {i + 1} 开始游走 (原F={wolf.fitness:.1f})...")

        # 执行游走
        new_wolf = operators.scouting(wolf)

        # 更新种群
        population[i] = new_wolf

    # 再次选出头狼 (看看有没有谁篡位成功)
    population.sort(key=lambda w: w.fitness)
    new_alpha = population[0]

    print("\n=== 游走结束 ===")
    if new_alpha.fitness < alpha_wolf.fitness:
        print(f"  >>> 头狼更新！新 F={new_alpha.fitness:.2f} (优化了 {alpha_wolf.fitness - new_alpha.fitness:.1f})")
    else:
        print("  > 头狼未变，需继续迭代...")


if __name__ == "__main__":
    main()