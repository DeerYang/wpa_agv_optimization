"""Fixed-scenario benchmark runner with multi-metric outputs."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from statistics import pstdev

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from wpa_agv_optimization.exporter import build_frontend_output_path, export_result_json
from wpa_agv_optimization.main import load_scenario, result_to_metrics, run_algorithm

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
    "conflict_count",
    "replan_count",
    "deadlock_risk_count",
    "deadlock_count",
    "reroute_count",
    "unfinished_count",
]

MAIN_SCENARIOS = [1, 2, 3]
SUPPLEMENTARY_SCENARIOS = [4, 5]
DEFAULT_RUNS = 10
DEFAULT_BASE_SEED = 20260220


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixed-scenario benchmarks and append structured results."
    )
    parser.add_argument("--algorithm", choices=["improved", "original"], default="improved")
    parser.add_argument("--scenarios", type=int, nargs="+", default=MAIN_SCENARIOS)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--csv", default="docs/benchmarks/benchmark_runs.csv")
    parser.add_argument("--md", default="docs/benchmarks/benchmark_summary.md")
    parser.add_argument("--tag", default=None)
    parser.add_argument("--base-seed", type=int, default=DEFAULT_BASE_SEED)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) - 1))
    return parser.parse_args()


def detect_git_tag() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip()
        return f"{commit}-dirty" if dirty else commit
    except Exception:
        return "unknown"


def build_tasks(args: argparse.Namespace) -> list[dict]:
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
    result = run_algorithm(
        scenario=task["scenario"],
        seed=task["seed"],
        algorithm=task["algorithm"],
        verbose=False,
        allow_interactive=False,
        export_json=False,
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
        "conflict_count": int(metrics["conflict_count"]),
        "replan_count": int(metrics["replan_count"]),
        "deadlock_risk_count": int(metrics["deadlock_risk_count"]),
        "deadlock_count": int(metrics["deadlock_count"]),
        "reroute_count": int(metrics["reroute_count"]),
        "unfinished_count": int(metrics["unfinished_count"]),
    }


def select_best_rows_by_scenario(rows: list[dict]) -> dict[int, dict]:
    """Pick the lowest-fitness run for each scenario."""
    best_rows: dict[int, dict] = {}
    for row in rows:
        scenario = row["scenario"]
        current_best = best_rows.get(scenario)
        if current_best is None or row["F"] < current_best["F"]:
            best_rows[scenario] = row
    return best_rows


def export_best_scenario_examples(rows: list[dict], algorithm: str, project_root: Path = PROJECT_ROOT) -> None:
    """Export one best-of-batch example JSON for each benchmark scenario."""
    for scenario, row in sorted(select_best_rows_by_scenario(rows).items()):
        result = run_algorithm(
            scenario=scenario,
            seed=row["seed"],
            algorithm=algorithm,
            verbose=False,
            allow_interactive=False,
            export_json=False,
        )
        grid_map, task_list, _ = load_scenario(scenario)
        output_path = build_frontend_output_path(
            algorithm,
            f"scenario-{scenario}.json",
            project_root=project_root,
        )
        export_result_json(
            wolf=result.wolf,
            grid_map=grid_map,
            task_list=task_list,
            convergence=[],
            scenario_name=result.scenario_name,
            algorithm=algorithm,
            seed=result.seed,
            output_path=str(output_path),
            variant_key=algorithm,
            project_root=str(project_root),
        )


def append_csv(csv_path: str, rows: list[dict]) -> None:
    csv_file = Path(csv_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_file.exists()
    if file_exists:
        with csv_file.open("r", encoding="utf-8-sig", newline="") as handle:
            existing_header = next(csv.reader(handle), [])
        if existing_header and existing_header != CSV_FIELDS:
            raise ValueError(
                f"CSV schema mismatch: existing={existing_header} vs expected={CSV_FIELDS}. "
                f"Migrate {csv_path} before appending."
            )
    with csv_file.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def read_csv_rows(csv_path: str) -> list[dict]:
    csv_file = Path(csv_path)
    if not csv_file.exists():
        return []
    with csv_file.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
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
                    "conflict_count": int(normalized.get("conflict_count", 0)),
                    "replan_count": int(normalized.get("replan_count", 0)),
                    "deadlock_risk_count": int(normalized.get("deadlock_risk_count", 0)),
                    "deadlock_count": int(normalized.get("deadlock_count", 0)),
                    "reroute_count": int(normalized.get("reroute_count", 0)),
                    "unfinished_count": int(normalized.get("unfinished_count", 0)),
                }
            )
        return rows


def summarize_by_scenario(rows: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["scenario"], []).append(row)

    summary: list[dict] = []
    for sid in sorted(groups.keys()):
        group = groups[sid]
        f_values = [x["F"] for x in group]
        n_values = [x["N"] for x in group]
        d_values = [x["D"] for x in group]
        t_values = [x["T"] for x in group]
        c_values = [x["conflict_count"] for x in group]
        r_values = [x["replan_count"] for x in group]
        q_values = [x["deadlock_risk_count"] for x in group]
        summary.append(
            {
                "scenario": sid,
                "runs": len(group),
                "F_mean": round(sum(f_values) / len(f_values), 2),
                "F_std": round(pstdev(f_values), 2) if len(f_values) > 1 else 0.0,
                "F_min": min(f_values),
                "F_max": max(f_values),
                "N_mean": round(sum(n_values) / len(n_values), 2),
                "D_mean": round(sum(d_values) / len(d_values), 2),
                "T_mean": round(sum(t_values) / len(t_values), 2),
                "T_std": round(pstdev(t_values), 2) if len(t_values) > 1 else 0.0,
                "conflict_mean": round(sum(c_values) / len(c_values), 2),
                "replan_mean": round(sum(r_values) / len(r_values), 2),
                "risk_mean": round(sum(q_values) / len(q_values), 2),
            }
        )
    return summary


def latest_batch_rows(rows: list[dict], algorithm: str) -> list[dict]:
    selected = [row for row in rows if row["algorithm"] == algorithm]
    if not selected:
        return []
    latest = selected[-1]["batch_id"]
    return [row for row in selected if row["batch_id"] == latest]


def latest_batch_id(rows: list[dict], algorithm: str) -> str | None:
    selected = [row for row in rows if row["algorithm"] == algorithm]
    if not selected:
        return None
    return selected[-1]["batch_id"]


def write_summary_table(handle, summary: list[dict]) -> None:
    handle.write("| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |\n")
    handle.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for item in summary:
        handle.write(
            f"| {item['scenario']} | {item['runs']} | {item['F_mean']:.2f} | {item['F_std']:.2f} | {item['F_min']:.2f} | {item['F_max']:.2f} | {item['N_mean']:.2f} | {item['D_mean']:.2f} | {item['T_mean']:.2f} | {item['T_std']:.2f} | {item['conflict_mean']:.2f} | {item['replan_mean']:.2f} | {item['risk_mean']:.2f} |\n"
        )


def write_compact_metric_table(handle, original_summary: list[dict], improved_summary: list[dict]) -> None:
    old_map = {item["scenario"]: item for item in original_summary}
    new_map = {item["scenario"]: item for item in improved_summary}
    handle.write("| Scenario | Original F_mean | Improved F_mean | Delta F | Delta % | Original T_mean | Improved T_mean | Original N_mean | Improved N_mean | Better |\n")
    handle.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|\n")
    for scenario in sorted(set(old_map) & set(new_map)):
        old = old_map[scenario]
        new = new_map[scenario]
        delta = round(new["F_mean"] - old["F_mean"], 2)
        delta_pct = 0.0 if old["F_mean"] == 0 else round(delta / old["F_mean"] * 100.0, 2)
        better = "improved" if delta < 0 else "original"
        handle.write(
            f"| {scenario} | {old['F_mean']:.2f} | {new['F_mean']:.2f} | {delta:.2f} | {delta_pct:.2f}% | {old['T_mean']:.2f} | {new['T_mean']:.2f} | {old['N_mean']:.2f} | {new['N_mean']:.2f} | {better} |\n"
        )


def write_stability_table(handle, original_summary: list[dict], improved_summary: list[dict]) -> None:
    old_map = {item["scenario"]: item for item in original_summary}
    new_map = {item["scenario"]: item for item in improved_summary}
    handle.write("| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |\n")
    handle.write("|---|---:|---:|---:|---:|\n")
    for scenario in sorted(set(old_map) & set(new_map)):
        old = old_map[scenario]
        new = new_map[scenario]
        handle.write(
            f"| {scenario} | {old['F_std']:.2f} | {new['F_std']:.2f} | {old['T_std']:.2f} | {new['T_std']:.2f} |\n"
        )


def write_markdown(md_path: str, all_rows: list[dict]) -> None:
    md_file = Path(md_path)
    md_file.parent.mkdir(parents=True, exist_ok=True)

    original_rows = latest_batch_rows(all_rows, "original")
    improved_rows = latest_batch_rows(all_rows, "improved")
    original_summary = summarize_by_scenario(original_rows) if original_rows else []
    improved_summary = summarize_by_scenario(improved_rows) if improved_rows else []
    csv_path = md_file.with_name("benchmark_runs.csv")

    with md_file.open("w", encoding="utf-8") as handle:
        handle.write("# Benchmark Results\n\n")
        handle.write("## Fixed Protocol\n\n")
        handle.write(f"- Main scenarios: `{MAIN_SCENARIOS[0]} {MAIN_SCENARIOS[1]} {MAIN_SCENARIOS[2]}`\n")
        handle.write(f"- Supplementary scenarios: `{SUPPLEMENTARY_SCENARIOS[0]} {SUPPLEMENTARY_SCENARIOS[1]}` (run separately)\n")
        handle.write(f"- Runs per scenario: `{DEFAULT_RUNS}`\n")
        handle.write(f"- Base seed: `{DEFAULT_BASE_SEED}`\n")
        handle.write("- Metrics: `F / N / D / T / conflict / replan / risk`\n")

        if original_summary and improved_summary:
            handle.write("\n## Core Comparison\n\n")
            write_compact_metric_table(handle, original_summary, improved_summary)
            handle.write("\n## Stability\n\n")
            write_stability_table(handle, original_summary, improved_summary)
            handle.write("\n## Original Summary\n\n")
            write_summary_table(handle, original_summary)
            handle.write("\n## Improved Summary\n\n")
            write_summary_table(handle, improved_summary)

        handle.write("\n## Current Batches\n\n")
        handle.write(f"- Latest original batch: `{latest_batch_id(all_rows, 'original')}`\n")
        handle.write(f"- Latest improved batch: `{latest_batch_id(all_rows, 'improved')}`\n")
        handle.write(f"- Raw rows file: `{csv_path.as_posix()}`\n")


def main() -> None:
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
                f"run={row['run']} -> seed={row['seed']} | F={row['F']:.2f}, N={row['N']}, D={row['D']}, T={row['T']:.2f}, "
                f"C={row['conflict_count']}, R={row['replan_count']}, Q={row['deadlock_risk_count']}"
            )

    results.sort(key=lambda row: (row["scenario"], row["run"]))
    rows_to_append = [{"date": date_str, "batch_id": batch_id, **row} for row in results]

    append_csv(args.csv, rows_to_append)
    all_rows = read_csv_rows(args.csv)
    write_markdown(args.md, all_rows)
    export_best_scenario_examples(results, args.algorithm)

    summary = summarize_by_scenario(rows_to_append)
    print("\n=== Batch Summary ===")
    for item in summary:
        print(
            f"algorithm={args.algorithm} scenario={item['scenario']} runs={item['runs']} "
            f"F_mean={item['F_mean']:.2f} F_std={item['F_std']:.2f} F_min={item['F_min']:.2f} F_max={item['F_max']:.2f} "
            f"N_mean={item['N_mean']:.2f} D_mean={item['D_mean']:.2f} T_mean={item['T_mean']:.2f} T_std={item['T_std']:.2f} "
            f"C_mean={item['conflict_mean']:.2f} R_mean={item['replan_mean']:.2f} Q_mean={item['risk_mean']:.2f}"
        )
    print(f"\nAppended to: {args.csv}")
    print(f"Written to: {args.md}")


if __name__ == "__main__":
    main()
