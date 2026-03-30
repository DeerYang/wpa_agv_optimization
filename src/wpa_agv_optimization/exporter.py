"""
前端可视化数据导出模块。

将算法最优调度方案导出为 JSON，供前端 Canvas 动画回放。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config


def export_result_json(
    wolf,
    grid_map,
    task_list,
    convergence: Optional[List[Dict[str, Any]]] = None,
    scenario_name: str = "",
    algorithm: str = "improved",
    seed: Optional[int] = None,
    output_path: Optional[str] = None,
) -> str:
    """将最优狼个体导出为前端可消费的 JSON 文件。

    Parameters
    ----------
    wolf : Wolf
        全局最优狼个体。
    grid_map : ndarray
        栅格地图 (MAP_WIDTH x MAP_HEIGHT), 1=障碍。
    task_list : list[Task]
        本次运行的任务列表。
    convergence : list[dict], optional
        收敛曲线数据, 每项 {"iter": int, "best_fitness": float}。
    scenario_name : str
        场景名称。
    algorithm : str
        算法版本标识。
    seed : int, optional
        随机种子。
    output_path : str, optional
        输出文件路径, 默认为 frontend/data/result.json。

    Returns
    -------
    str
        实际写入的文件路径。
    """
    # 构建障碍物列表
    obstacles = []
    for x in range(grid_map.shape[0]):
        for y in range(grid_map.shape[1]):
            if grid_map[x][y] == 1:
                obstacles.append([int(x), int(y)])

    # 构建任务列表
    tasks = []
    for task in task_list:
        tasks.append({
            "id": int(task.id),
            "x": int(task.x),
            "y": int(task.y),
            "weight": int(task.weight),
            "deadline": int(task.deadline),
        })

    # 构建 AGV 列表
    agvs = []
    for agv in wolf.agv_list:
        agv_data = {
            "id": int(agv.id),
            "start_pos": [int(agv.start_pos[0]), int(agv.start_pos[1])],
            "tasks": [int(t.id) for t in agv.tasks],
            "load": int(agv.load),
            "finish_time": int(agv.finish_time),
            "path": [[int(x), int(y), int(t)] for x, y, t in agv.path],
        }
        agvs.append(agv_data)

    # 构建结果
    result = {
        "meta": {
            "scenario_name": scenario_name,
            "algorithm": algorithm,
            "seed": seed,
        },
        "map": {
            "width": int(Config.MAP_WIDTH),
            "height": int(Config.MAP_HEIGHT),
            "obstacles": obstacles,
            "start_nodes": [[int(x), int(y)] for x, y in Config.START_NODES],
            "depot": [int(Config.DEPOT_NODE[0]), int(Config.DEPOT_NODE[1])],
        },
        "tasks": tasks,
        "agvs": agvs,
        "fitness": {
            "F": round(float(wolf.fitness), 2),
            "N": int(wolf.vehicle_num),
            "D": int(wolf.total_dist),
            "T": round(float(wolf.time_penalty), 2),
            "conflict_count": int(getattr(wolf, "conflict_count", 0)),
            "deadlock_count": int(getattr(wolf, "deadlock_count", 0)),
            "deadlock_risk_count": int(getattr(wolf, "deadlock_risk_count", 0)),
            "replan_count": int(getattr(wolf, "replan_count", 0)),
            "reroute_count": int(getattr(wolf, "reroute_count", 0)),
        },
        "convergence": convergence or [],
    }

    # 写入文件
    if output_path is None:
        project_root = Path(__file__).resolve().parents[2]
        output_dir = project_root / "frontend" / "data"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / "result.json")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return str(out)
