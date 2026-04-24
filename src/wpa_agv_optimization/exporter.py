"""
前端可视化数据导出模块。

将算法最优调度方案导出为 JSON，供前端 Canvas 动画回放。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config


def normalize_variant_key(variant_key: str) -> str:
    """Normalize one frontend algorithm key into a filesystem-safe name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(variant_key).strip())
    cleaned = cleaned.strip(".-")
    if not cleaned:
        raise ValueError("算法标识不能为空")
    return cleaned


def get_frontend_data_dir(project_root: Optional[Path] = None) -> Path:
    """Return the frontend data root directory."""
    base_root = project_root or Path(__file__).resolve().parents[2]
    return base_root / "frontend" / "data"


def build_frontend_output_path(
    variant_key: str,
    filename: str,
    *,
    project_root: Optional[Path] = None,
) -> Path:
    """Build one frontend data output path under the algorithm-specific folder."""
    safe_key = normalize_variant_key(variant_key)
    data_root = get_frontend_data_dir(project_root=project_root)
    return data_root / safe_key / filename


def _update_frontend_manifest(data_root: Path, variant_key: str, filename: str) -> None:
    """Record available frontend data files for one algorithm variant."""
    manifest_path = data_root / "manifest.json"
    manifest = {"variants": []}
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict) and isinstance(loaded.get("variants"), list):
            manifest = loaded

    safe_key = normalize_variant_key(variant_key)
    entries = {
        item["key"]: {
            "key": item["key"],
            "label": item.get("label", item["key"]),
            "files": list(item.get("files", [])),
        }
        for item in manifest["variants"]
        if isinstance(item, dict) and "key" in item
    }

    entry = entries.setdefault(
        safe_key,
        {
            "key": safe_key,
            "label": safe_key,
            "files": [],
        },
    )
    if filename not in entry["files"]:
        entry["files"].append(filename)
        entry["files"].sort()

    manifest["variants"] = [entries[key] for key in sorted(entries.keys())]
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)


def export_result_json(
    wolf,
    grid_map,
    task_list,
    convergence: Optional[List[Dict[str, Any]]] = None,
    scenario_name: str = "",
    algorithm: str = "improved",
    seed: Optional[int] = None,
    output_path: Optional[str] = None,
    variant_key: Optional[str] = None,
    project_root: Optional[str] = None,
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
        输出文件路径, 默认为 frontend/data/<algorithm>/result.json。
    variant_key : str, optional
        前端目录下的算法键, 默认为 algorithm。
    project_root : str, optional
        项目根目录覆盖值, 主要用于测试。

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
        task_completion_times = {
            str(int(task_id)): int(finish_time)
            for task_id, finish_time in getattr(agv, "task_completion_times", {}).items()
        }
        agv_data = {
            "id": int(agv.id),
            "start_pos": [int(agv.start_pos[0]), int(agv.start_pos[1])],
            "tasks": [int(t.id) for t in agv.tasks],
            "load": int(agv.load),
            "finish_time": int(agv.finish_time),
            "travel_distance": int(getattr(agv, "travel_distance", len(getattr(agv, "path", [])))),
            "wait_time": int(getattr(agv, "wait_time", 0)),
            "service_time": int(getattr(agv, "service_time", 0)),
            "task_completion_times": task_completion_times,
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
            "unfinished_count": int(getattr(wolf, "unfinished_count", 0)),
        },
        "timing": {
            "wait_time": int(getattr(wolf, "total_wait_time", 0)),
            "service_time": int(getattr(wolf, "total_service_time", 0)),
        },
        "convergence": convergence or [],
    }

    # 写入文件
    selected_variant_key = normalize_variant_key(variant_key or algorithm)
    resolved_project_root = Path(project_root) if project_root is not None else None
    data_root = get_frontend_data_dir(project_root=resolved_project_root)
    if output_path is None:
        output_path = str(
            build_frontend_output_path(
                selected_variant_key,
                "result.json",
                project_root=resolved_project_root,
            )
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    _update_frontend_manifest(data_root, selected_variant_key, out.name)

    return str(out)
