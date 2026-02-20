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


def parse_args():
    parser = argparse.ArgumentParser(
        description="自动运行固定场景基准（默认3个场景×每场景10次）并追加记录。"
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        nargs="+",
        default=[1, 2, 3],
        help="要运行的场景编号列表，例如: --scenarios 1 2 3",
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
        help="用于执行 main.py 的 Python 可执行文件路径，默认当前解释器。",
    )
    parser.add_argument(
        "--csv",
        default="benchmark_fixed_inputs_runs.csv",
        help="CSV 结果文件路径，默认 benchmark_fixed_inputs_runs.csv",
    )
    parser.add_argument(
        "--md",
        default="benchmark_fixed_inputs_summary.md",
        help="Markdown 结果文件路径，默认 benchmark_fixed_inputs_summary.md",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="本次基准的版本标识（例如 old-summoning / mid-summoning）。不填则自动用 git 提交号。",
    )
    return parser.parse_args()


def run_once(python_exe, scenario_id):
    cmd = [python_exe, "main.py", "--scenario", str(scenario_id)]
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


def detect_git_tag():
    """
    自动生成版本标签：<short_commit>[-dirty]
    非 git 环境时返回 unknown。
    """
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
        if dirty:
            return f"{commit}-dirty"
        return commit
    except Exception:
        return "unknown"


def append_csv(csv_path, rows):
    csv_file = Path(csv_path)
    file_exists = csv_file.exists()
    with csv_file.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "batch_id", "scenario", "run", "F", "N", "D", "T"],
        )
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize_by_scenario(rows):
    groups = {}
    for row in rows:
        sid = row["scenario"]
        groups.setdefault(sid, []).append(row)
    summary = []
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


def append_markdown(md_path, batch_id, rows, summary):
    md_file = Path(md_path)
    with md_file.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Batch {batch_id}\n")
        f.write("\n### 原始结果\n\n")
        f.write("| Scenario | Run | F | N | D | T |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for row in rows:
            f.write(
                f"| {row['scenario']} | {row['run']} | {row['F']:.2f} | {row['N']} | {row['D']} | {row['T']:.2f} |\n"
            )

        f.write("\n### 本批次汇总\n\n")
        f.write("| Scenario | Runs | F_Mean | F_Min | F_Max | D_Mean | T_Mean |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for s in summary:
            f.write(
                f"| {s['scenario']} | {s['runs']} | {s['F_mean']:.2f} | {s['F_min']:.2f} | {s['F_max']:.2f} | {s['D_mean']:.2f} | {s['T_mean']:.2f} |\n"
            )


def main():
    args = parse_args()
    now = dt.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    run_tag = args.tag.strip() if args.tag else detect_git_tag()
    batch_id = f"{now.strftime('%Y-%m-%d %H:%M:%S')} [{run_tag}]"
    all_rows = []

    for scenario_id in args.scenarios:
        for run_idx in range(1, args.runs + 1):
            metrics = run_once(args.python, scenario_id)
            row = {
                "date": date_str,
                "batch_id": batch_id,
                "scenario": scenario_id,
                "run": run_idx,
                "F": metrics["F"],
                "N": metrics["N"],
                "D": metrics["D"],
                "T": metrics["T"],
            }
            all_rows.append(row)
            print(
                f"[OK] scenario={scenario_id} run={run_idx} -> "
                f"F={metrics['F']:.2f}, N={metrics['N']}, D={metrics['D']}, T={metrics['T']:.2f}"
            )

    append_csv(args.csv, all_rows)
    summary = summarize_by_scenario(all_rows)
    append_markdown(args.md, batch_id, all_rows, summary)

    print("\n=== 本批次汇总 ===")
    for s in summary:
        print(
            f"scenario={s['scenario']} runs={s['runs']} "
            f"F_mean={s['F_mean']:.2f} F_min={s['F_min']:.2f} F_max={s['F_max']:.2f} "
            f"D_mean={s['D_mean']:.2f} T_mean={s['T_mean']:.2f}"
        )
    print(f"\n已追加到: {args.csv}")
    print(f"已追加到: {args.md}")


if __name__ == "__main__":
    main()
