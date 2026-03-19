"""固定场景基准批量运行脚本。

优化点：
- 直接调用包内 run_algorithm，不再反复启动 main.py 子进程。
- 支持多进程并行运行 benchmark。
- worker 以静默模式运行，关闭详细算法日志。
- 最终仍按原有 CSV/Markdown 格式落盘。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from wpa_agv_optimization.main import result_to_metrics, run_algorithm


CSV_FIELDS = [
    "date",
    "batch_id",
    "algorithm",
    "scenario",
    "run",
    "seed",
    "F",
    "N",
    "D",
    "T",
]


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="自动运行固定场景基准（默认3个场景，每场景10次）并追加记录。"
    )
    parser.add_argument(
        "--algorithm",
        choices=["improved", "original"],
        default="improved",
        help="选择算法版本。",
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        nargs="+",
        default=[1, 2, 3],
        help="要运行的场景编号列表，例如：--scenarios 1 2 3",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="每个场景运行次数，默认10。",
    )
    parser.add_argument(
        "--csv",
        default="docs/benchmarks/benchmark_runs.csv",
        help="CSV 结果文件路径。",
    )
    parser.add_argument(
        "--md",
        default="docs/benchmarks/benchmark_summary.md",
        help="Markdown 结果文件路径。",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="本批次标签。不填则自动读取 git 提交号。",
    )
    parser.add_argument(
        "--base-seed",
        type=int,
        default=20260220,
        help="基础种子。实际种子 = base_seed + scenario*1000 + run。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) - 1),
        help="并行进程数，默认使用 CPU 核心数减一。",
    )
    return parser.parse_args()



def detect_git_tag() -> str:
    """自动生成版本标签：<short_commit>[-dirty]。"""
    import subprocess

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return f"{commit}-dirty" if dirty else commit
    except Exception:
        return "unknown"



def build_tasks(args: argparse.Namespace) -> list[dict]:
    """展开 benchmark 任务列表。"""
    tasks: list[dict] = []
    for scenario_id in args.scenarios:
        for run_idx in range(1, args.runs + 1):
            seed = args.base_seed + scenario_id * 1000 + run_idx
            tasks.append(
                {
                    "algorithm": args.algorithm,
                    "scenario": scenario_id,
                    "run": run_idx,
                    "seed": seed,
                }
            )
    return tasks



def run_one_task(task: dict) -> dict:
    """Worker entry: run one benchmark case in-process and return metrics."""
    result = run_algorithm(
        scenario=task["scenario"],
        seed=task["seed"],
        algorithm=task["algorithm"],
        verbose=False,
        allow_interactive=False,
    )
    metrics = result_to_metrics(result)
    return {
        "algorithm": task["algorithm"],
        "scenario": task["scenario"],
        "run": task["run"],
        "seed": task["seed"],
        "F": float(metrics["F"]),
        "N": int(metrics["N"]),
        "D": int(metrics["D"]),
        "T": float(metrics["T"]),
    }



def append_csv(csv_path: str, rows: list[dict]) -> None:
    """将原始运行行追加到 CSV。"""
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_file.exists()
    with csv_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)



def read_csv_rows(csv_path: str) -> list[dict]:
    """读取全部历史 CSV 记录。"""
    csv_file = Path(csv_path)
    if not csv_file.exists():
        return []
    with csv_file.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict] = []
        for row in reader:
            normalized = {str(key).lstrip("\ufeff").strip('"'): value for key, value in row.items()}
            rows.append(
                {
                    "date": normalized["date"],
                    "batch_id": normalized["batch_id"],
                    "algorithm": normalized["algorithm"],
                    "scenario": int(normalized["scenario"]),
                    "run": int(normalized["run"]),
                    "seed": int(normalized["seed"]),
                    "F": float(normalized["F"]),
                    "N": int(normalized["N"]),
                    "D": int(normalized["D"]),
                    "T": float(normalized["T"]),
                }
            )
        return rows



def summarize_by_scenario(rows: list[dict]) -> list[dict]:
    """按场景聚合统计均值和极值。"""
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["scenario"], []).append(row)

    summary: list[dict] = []
    for sid in sorted(groups.keys()):
        g = groups[sid]
        f_values = [x["F"] for x in g]
        d_values = [x["D"] for x in g]
        t_values = [x["T"] for x in g]
        summary.append(
            {
                "scenario": sid,
                "runs": len(g),
                "F_mean": round(sum(f_values) / len(f_values), 2),
                "F_min": min(f_values),
                "F_max": max(f_values),
                "D_mean": round(sum(d_values) / len(d_values), 2),
                "T_mean": round(sum(t_values) / len(t_values), 2),
            }
        )
    return summary



def latest_batch_rows(rows: list[dict], algorithm: str) -> list[dict]:
    """Get the latest batch rows for one algorithm from CSV history."""
    selected = [row for row in rows if row["algorithm"] == algorithm]
    if not selected:
        return []
    latest_batch_id = selected[-1]["batch_id"]
    return [row for row in selected if row["batch_id"] == latest_batch_id]



def write_markdown(md_path: str, all_rows: list[dict]) -> None:
    """重建 Markdown 报告，保留顶部对比和全部历史 batch。"""
    md_file = Path(md_path)
    md_file.parent.mkdir(parents=True, exist_ok=True)

    improved_rows = latest_batch_rows(all_rows, "improved")
    original_rows = latest_batch_rows(all_rows, "original")
    improved_summary = summarize_by_scenario(improved_rows) if improved_rows else []
    original_summary = summarize_by_scenario(original_rows) if original_rows else []

    batch_order: list[str] = []
    batch_groups: dict[str, list[dict]] = {}
    for row in all_rows:
        batch_id = row["batch_id"]
        if batch_id not in batch_groups:
            batch_groups[batch_id] = []
            batch_order.append(batch_id)
        batch_groups[batch_id].append(row)

    with md_file.open("w", encoding="utf-8") as f:
        f.write("# 算法对比基准结果\n\n")
        f.write("本轮结果基于固定场景与固定种子，配置为 `3 场景 × 10 次`。\n")

        if original_summary and improved_summary:
            improved_by_scenario = {item["scenario"]: item for item in improved_summary}
            original_by_scenario = {item["scenario"]: item for item in original_summary}

            f.write("\n## 汇总对比\n\n")
            f.write("| Scenario | Original F_mean | Improved F_mean | Improved - Original | Better |\n")
            f.write("|---|---:|---:|---:|---|\n")
            for scenario in sorted(set(original_by_scenario) & set(improved_by_scenario)):
                old = original_by_scenario[scenario]
                new = improved_by_scenario[scenario]
                diff = round(new["F_mean"] - old["F_mean"], 2)
                better = "improved" if diff < 0 else "original"
                f.write(
                    f"| {scenario} | {old['F_mean']:.2f} | {new['F_mean']:.2f} | {diff:.2f} | {better} |\n"
                )

            f.write("\n## Original\n\n")
            f.write("| Scenario | Runs | F_Mean | F_Min | F_Max | D_Mean | T_Mean |\n")
            f.write("|---|---:|---:|---:|---:|---:|---:|\n")
            for item in original_summary:
                f.write(
                    f"| {item['scenario']} | {item['runs']} | {item['F_mean']:.2f} | {item['F_min']:.2f} | {item['F_max']:.2f} | {item['D_mean']:.2f} | {item['T_mean']:.2f} |\n"
                )

            f.write("\n## Improved\n\n")
            f.write("| Scenario | Runs | F_Mean | F_Min | F_Max | D_Mean | T_Mean |\n")
            f.write("|---|---:|---:|---:|---:|---:|---:|\n")
            for item in improved_summary:
                f.write(
                    f"| {item['scenario']} | {item['runs']} | {item['F_mean']:.2f} | {item['F_min']:.2f} | {item['F_max']:.2f} | {item['D_mean']:.2f} | {item['T_mean']:.2f} |\n"
                )

        for batch_id in batch_order:
            batch_rows = batch_groups[batch_id]
            batch_rows.sort(key=lambda row: (row["scenario"], row["run"]))
            batch_summary = summarize_by_scenario(batch_rows)

            f.write(f"\n\n## Batch {batch_id}\n")
            f.write("\n### 原始结果\n\n")
            f.write("| Algorithm | Scenario | Run | F | N | D | T |\n")
            f.write("|---|---|---:|---:|---:|---:|---:|\n")
            for row in batch_rows:
                f.write(
                    f"| {row['algorithm']} | {row['scenario']} | {row['run']} | {row['F']:.2f} | {row['N']} | {row['D']} | {row['T']:.2f} |\n"
                )

            f.write("\n### 本批次汇总\n\n")
            f.write("| Scenario | Runs | F_Mean | F_Min | F_Max | D_Mean | T_Mean |\n")
            f.write("|---|---:|---:|---:|---:|---:|---:|\n")
            for item in batch_summary:
                f.write(
                    f"| {item['scenario']} | {item['runs']} | {item['F_mean']:.2f} | {item['F_min']:.2f} | {item['F_max']:.2f} | {item['D_mean']:.2f} | {item['T_mean']:.2f} |\n"
                )



def main() -> None:
    """批量运行入口。"""
    args = parse_args()
    tasks = build_tasks(args)
    workers = max(1, min(args.workers, len(tasks)))

    now = dt.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    run_tag = args.tag.strip() if args.tag else detect_git_tag()
    batch_id = f"{now.strftime('%Y-%m-%d %H:%M:%S')} [{run_tag}][{args.algorithm}]"

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(run_one_task, task): task for task in tasks}
        completed_count = 0
        total = len(future_map)
        for future in as_completed(future_map):
            row = future.result()
            completed_count += 1
            results.append(row)
            print(
                f"[OK {completed_count}/{total}] algorithm={row['algorithm']} scenario={row['scenario']} "
                f"run={row['run']} -> seed={row['seed']} | F={row['F']:.2f}, N={row['N']}, D={row['D']}, T={row['T']:.2f}"
            )

    results.sort(key=lambda row: (row["scenario"], row["run"]))
    rows_to_append = [
        {
            "date": date_str,
            "batch_id": batch_id,
            **row,
        }
        for row in results
    ]

    append_csv(args.csv, rows_to_append)
    all_rows = read_csv_rows(args.csv)
    write_markdown(args.md, all_rows)

    summary = summarize_by_scenario(rows_to_append)
    print("\n=== 本批次汇总 ===")
    for item in summary:
        print(
            f"algorithm={args.algorithm} scenario={item['scenario']} runs={item['runs']} "
            f"F_mean={item['F_mean']:.2f} F_min={item['F_min']:.2f} F_max={item['F_max']:.2f} "
            f"D_mean={item['D_mean']:.2f} T_mean={item['T_mean']:.2f}"
        )
    print(f"\n已追加到: {args.csv}")
    print(f"已写入: {args.md}")


if __name__ == "__main__":
    main()
