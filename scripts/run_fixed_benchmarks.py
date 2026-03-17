"""
固定场景基准批量运行脚本。
作用：
- 自动运行多个固定场景和多次重复实验。
- 从主程序输出中解析 F/N/D/T。
- 结果追加写入 CSV 与 Markdown。
"""

import argparse
import csv
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

FINAL_METRICS_PATTERN = re.compile(
    r"=== 4\.[\s\S]*?F=([0-9.]+)[\s\S]*?N=([0-9]+)[\s\S]*?D=([0-9]+)[\s\S]*?T=([0-9.]+)",
    re.MULTILINE,
)


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
        "--python",
        default=sys.executable,
        help="用于执行 main.py 的 Python 解释器路径。",
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
    return parser.parse_args()


def run_once(python_exe: str, scenario_id: int, seed: int, algorithm: str) -> dict:
    """运行一次主程序并解析 F/N/D/T。"""
    cmd = [
        python_exe,
        "main.py",
        "--scenario",
        str(scenario_id),
        "--seed",
        str(seed),
        "--algorithm",
        algorithm,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"场景 {scenario_id} 运行失败(returncode={completed.returncode})\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    match = FINAL_METRICS_PATTERN.search(completed.stdout)
    if not match:
        raise RuntimeError(f"场景 {scenario_id} 输出中未解析到 F/N/D/T 指标。")
    return {
        "F": float(match.group(1)),
        "N": int(match.group(2)),
        "D": int(match.group(3)),
        "T": float(match.group(4)),
    }


def detect_git_tag() -> str:
    """自动生成版本标签：<short_commit>[-dirty]。"""
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


def append_csv(csv_path: str, rows: list[dict]) -> None:
    """将原始运行行追加到 CSV。"""
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_file.exists()
    with csv_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize_by_scenario(rows: list[dict]) -> list[dict]:
    """按场景聚合统计均值和极值。"""
    groups: dict[int, list[dict]] = {}
    for row in rows:
        sid = row["scenario"]
        groups.setdefault(sid, []).append(row)

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


def append_markdown(
    md_path: str, batch_id: str, rows: list[dict], summary: list[dict]
) -> None:
    """将原始表与汇总表追加到 Markdown 报告。"""
    md_file = Path(md_path)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    with md_file.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Batch {batch_id}\n")
        f.write("\n### 原始结果\n\n")
        f.write("| Algorithm | Scenario | Run | F | N | D | T |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|\n")
        for row in rows:
            f.write(
                f"| {row['algorithm']} | {row['scenario']} | {row['run']} | {row['F']:.2f} | {row['N']} | {row['D']} | {row['T']:.2f} |\n"
            )

        f.write("\n### 本批次汇总\n\n")
        f.write("| Scenario | Runs | F_Mean | F_Min | F_Max | D_Mean | T_Mean |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for s in summary:
            f.write(
                f"| {s['scenario']} | {s['runs']} | {s['F_mean']:.2f} | {s['F_min']:.2f} | {s['F_max']:.2f} | {s['D_mean']:.2f} | {s['T_mean']:.2f} |\n"
            )


def main() -> None:
    """批量运行入口。"""
    args = parse_args()
    now = dt.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    run_tag = args.tag.strip() if args.tag else detect_git_tag()
    batch_id = f"{now.strftime('%Y-%m-%d %H:%M:%S')} [{run_tag}][{args.algorithm}]"
    all_rows: list[dict] = []

    for scenario_id in args.scenarios:
        for run_idx in range(1, args.runs + 1):
            seed = args.base_seed + scenario_id * 1000 + run_idx
            metrics = run_once(args.python, scenario_id, seed, args.algorithm)
            row = {
                "date": date_str,
                "batch_id": batch_id,
                "algorithm": args.algorithm,
                "scenario": scenario_id,
                "run": run_idx,
                "seed": seed,
                "F": metrics["F"],
                "N": metrics["N"],
                "D": metrics["D"],
                "T": metrics["T"],
            }
            all_rows.append(row)
            print(
                f"[OK] algorithm={args.algorithm} scenario={scenario_id} run={run_idx} -> "
                f"seed={seed} | F={metrics['F']:.2f}, N={metrics['N']}, D={metrics['D']}, T={metrics['T']:.2f}"
            )

    append_csv(args.csv, all_rows)
    summary = summarize_by_scenario(all_rows)
    append_markdown(args.md, batch_id, all_rows, summary)

    print("\n=== 本批次汇总 ===")
    for s in summary:
        print(
            f"algorithm={args.algorithm} scenario={s['scenario']} runs={s['runs']} "
            f"F_mean={s['F_mean']:.2f} F_min={s['F_min']:.2f} F_max={s['F_max']:.2f} "
            f"D_mean={s['D_mean']:.2f} T_mean={s['T_mean']:.2f}"
        )
    print(f"\n已追加到: {args.csv}")
    print(f"已追加到: {args.md}")


if __name__ == "__main__":
    main()
