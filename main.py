# ===================== 文件级说明 =====================
# 文件名: main.py
# 功能: 多AGV调度系统主程序入口，完整实现狼群算法全流程迭代闭环
# 迭代流程: 环境构建→任务生成→种群初始化→[游走→召唤→围攻→优胜劣汰]迭代→结果输出
# 开题对应: 基于改进狼群算法的求解流程图，完整匹配技术路线
# ======================================================

# 引入命令行参数库，用于选择固定场景
import argparse
# 引入随机数库，用于任务随机生成
import random
# 引入数值计算库，用于构建固定场景地图
import numpy as np
# 引入全局配置类
from config import Config
# 引入任务实体类
from models import Task
# 引入工具函数：栅格地图生成
from utils import generate_grid_map
# 引入固定场景库
from scenario_inputs import SCENARIO_LIBRARY
# 引入种群初始化器
from initializer import PopulationInitializer
# 引入狼评估器
from evaluator import WolfEvaluator
# 引入狼群算法算子
from wpa_ops import WPAOperators


def list_scenarios():
    """打印固定场景列表"""
    print("可用固定输入场景：")
    for idx, scenario in enumerate(SCENARIO_LIBRARY, start=1):
        print(f"  {idx}. {scenario['name']} - {scenario['description']}")


def load_scenario(scenario_index):
    """
    按编号加载固定场景
    :param scenario_index: 场景编号（从1开始）
    :return: (grid_map, task_list, scenario_name)
    """
    if scenario_index < 1 or scenario_index > len(SCENARIO_LIBRARY):
        raise ValueError(f"场景编号无效: {scenario_index}")

    scenario = SCENARIO_LIBRARY[scenario_index - 1]
    grid_map = np.zeros((Config.MAP_WIDTH, Config.MAP_HEIGHT), dtype=int)

    for x, y in scenario["obstacles"]:
        if 0 <= x < Config.MAP_WIDTH and 0 <= y < Config.MAP_HEIGHT:
            if x != 0 and (x, y) != Config.DEPOT_NODE:
                grid_map[x][y] = 1

    task_list = []
    for i, item in enumerate(scenario["tasks"], start=1):
        tx, ty = item["x"], item["y"]
        if grid_map[tx][ty] == 1:
            raise ValueError(f"场景[{scenario_index}]任务落在障碍物上: ({tx},{ty})")
        task = Task(
            i,
            tx,
            ty,
            item["weight"],
            item["deadline"],
        )
        task_list.append(task)

    return grid_map, task_list, scenario["name"]


def parse_args():
    parser = argparse.ArgumentParser(description="多AGV狼群算法调度仿真")
    parser.add_argument(
        "--scenario",
        type=int,
        default=None,
        help="固定输入场景编号（从1开始）。不填则询问或走随机任务。",
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
        help="随机种子。传入后可复现实验结果。",
    )
    return parser.parse_args()


def main():
    """
    主程序入口函数
    功能: 完整执行多AGV调度仿真全流程，实现基于改进狼群算法的路径优化
    """
    args = parse_args()
    if args.list_scenarios:
        list_scenarios()
        return

    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        print(f"=== 0. 固定随机种子 seed={args.seed} ===")

    # ================ Step1: 仿真环境与任务构建 ================
    print("=== 1. 仓储环境与任务构建 ===")
    selected_scenario = args.scenario
    if selected_scenario is None:
        list_scenarios()
        raw = input("请输入场景编号（直接回车使用随机输入）: ").strip()
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
        # 生成带随机障碍物的20×20栅格地图
        grid_map = generate_grid_map()
        # 初始化全局任务列表
        task_list = []
        # 生成15个随机取货任务，可根据需求调整数量
        task_num = 15
        for i in range(task_num):
            # 循环生成任务坐标，确保坐标在可通行区域，不在障碍物上
            while True:
                # 随机生成1~19的坐标，避开出发区(x=0)和地图边界
                tx, ty = random.randint(1, 19), random.randint(1, 19)
                # 校验坐标为可通行区域，跳出循环
                if grid_map[tx][ty] == 0:
                    break
            # 实例化任务对象：任务ID、坐标、重量(10~40kg)、截止时间(50~300秒)
            t = Task(i + 1, tx, ty, random.randint(10, 40), random.randint(50, 300))
            # 将任务加入全局任务列表
            task_list.append(t)
        # 打印任务生成结果
        print(f"  > 成功生成 {len(task_list)} 个随机取货任务")

    # ================ Step2: 狼群种群初始化 ================
    print("\n=== 2. 狼群种群初始化 ===")
    # 实例化种群初始化器
    initializer = PopulationInitializer(grid_map, task_list)
    # 生成初始种群，规模由Config.POP_SIZE配置
    population = initializer.generate_population()
    # 按适应度从小到大排序（值越小越优），选出初始头狼（全局最优解）
    population.sort(key=lambda w: w.fitness)
    alpha_wolf = population[0]
    # 打印初始头狼的核心指标，对应开题的多目标优化函数
    print(f"  > 初始头狼生成完成")
    print(f"    适应度F={alpha_wolf.fitness:.2f} | 使用车辆数N={alpha_wolf.vehicle_num} | 总行驶距离D={alpha_wolf.total_dist} | 时间窗惩罚T={alpha_wolf.time_penalty}")

    # ================ Step3: 算法核心参数配置 ================
    # 算法最大迭代次数，可根据需求调整，毕设初期建议50~100代
    MAX_ITER = 50
    # 探狼数量：种群中Top-K个最优个体作为探狼，执行游走行为
    SCOUTS_NUM = 5
    # 实例化评估器与算法算子
    evaluator = WolfEvaluator(grid_map)
    operators = WPAOperators(evaluator)
    # 全局最优解保存变量，用于记录迭代过程中的全局最优头狼
    global_best_wolf = alpha_wolf

    # ================ Step4: 狼群算法主迭代循环 ================
    print(f"\n=== 3. 开始狼群算法迭代，最大迭代次数={MAX_ITER} ===")
    for iter in range(MAX_ITER):
        print(f"\n--- 第 {iter+1}/{MAX_ITER} 代迭代开始 ---")

        # -------------------------- 步骤1：探狼执行游走行为，全局广域勘探 --------------------------
        print("> 探狼执行游走行为...")
        # 对前SCOUTS_NUM个探狼，依次执行游走行为
        for i in range(SCOUTS_NUM):
            wolf = population[i]
            new_wolf = operators.scouting(wolf)
            # 用新个体更新种群
            population[i] = new_wolf

        # 迭代后重新排序种群，更新头狼
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        # 更新全局最优解
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
            print(f"> 游走后更新全局最优解！新F={global_best_wolf.fitness:.2f}")

        # -------------------------- 步骤2：猛狼执行召唤行为，向头狼靠拢，信息共享 --------------------------
        print("> 猛狼执行召唤行为...")
        # 猛狼范围：探狼之后的所有个体（SCOUTS_NUM到种群末尾）
        for i in range(SCOUTS_NUM, len(population)):
            wolf = population[i]
            new_wolf = operators.summoning(wolf, global_best_wolf)
            # 用新个体更新种群
            population[i] = new_wolf

        # 迭代后重新排序种群，更新头狼
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        # 更新全局最优解
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
            print(f"> 召唤后更新全局最优解！新F={global_best_wolf.fitness:.2f}")

        # -------------------------- 步骤3：全种群执行围攻行为，局部优化+防早熟 --------------------------
        print("> 全种群执行围攻行为...")
        # 遍历全种群，依次执行围攻行为，头狼除外（保护全局最优解）
        for i in range(1, len(population)):
            wolf = population[i]
            new_wolf = operators.besieging(wolf, iter, MAX_ITER)
            # 用新个体更新种群
            population[i] = new_wolf

        # 迭代后重新排序种群，更新头狼
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        # 更新全局最优解
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
            print(f"> 围攻后更新全局最优解！新F={global_best_wolf.fitness:.2f}")

        # -------------------------- 步骤4：种群优胜劣汰，维持多样性 --------------------------
        print("> 执行种群优胜劣汰...")
        # 淘汰种群中最差的2个个体
        population = population[:-2]
        # 用Tent混沌映射生成2个新个体补充进种群，维持多样性
        for _ in range(2):
            new_wolf = initializer._create_one_wolf()
            population.append(new_wolf)

        # -------------------------- 本代迭代结束，打印结果 --------------------------
        population.sort(key=lambda w: w.fitness)
        current_alpha = population[0]
        if current_alpha.fitness < global_best_wolf.fitness:
            global_best_wolf = current_alpha
        print(f"--- 第 {iter+1}/{MAX_ITER} 代迭代结束 ---")
        print(f"    当前代最优F={current_alpha.fitness:.2f} | 全局最优F={global_best_wolf.fitness:.2f}")
        print(f"    全局最优指标：车辆数N={global_best_wolf.vehicle_num} | 总距离D={global_best_wolf.total_dist} | 时间惩罚T={global_best_wolf.time_penalty}")

    # ================ Step5: 迭代结束，输出最终结果 ================
    print("\n=== 4. 算法迭代结束，最终优化结果 ===")
    print(f"  全局最优调度方案核心指标：")
    print(f"    多目标适应度F={global_best_wolf.fitness:.2f}")
    print(f"    使用AGV车辆数N={global_best_wolf.vehicle_num}")
    print(f"    系统总行驶距离D={global_best_wolf.total_dist} 格")
    print(f"    时间窗总惩罚T={global_best_wolf.time_penalty} 秒")
    print(f"  方案详情：")
    for idx, agv in enumerate(global_best_wolf.agv_list):
        print(f"    AGV-{agv.id}：任务数={len(agv.tasks)} | 最终载重={agv.load}kg | 完成时间={agv.finish_time}秒")
        print(f"      任务执行顺序：{agv.tasks}")


# 主程序执行入口
if __name__ == "__main__":
    main()
