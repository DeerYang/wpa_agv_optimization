import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scripts.run_fixed_benchmarks as bench


class BenchmarkExportTests(unittest.TestCase):
    def make_project_root(self, name: str) -> Path:
        root = Path.cwd() / 'tests' / '_tmp' / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_select_best_rows_by_scenario_uses_lowest_fitness(self):
        rows = [
            {"scenario": 1, "seed": 11, "F": 300.0},
            {"scenario": 1, "seed": 12, "F": 250.0},
            {"scenario": 2, "seed": 21, "F": 500.0},
            {"scenario": 2, "seed": 22, "F": 510.0},
        ]

        best = bench.select_best_rows_by_scenario(rows)

        self.assertEqual(best[1]["seed"], 12)
        self.assertEqual(best[2]["seed"], 21)

    def test_export_best_scenario_examples_writes_algorithm_scoped_paths(self):
        rows = [
            {"scenario": 1, "seed": 12, "F": 250.0},
            {"scenario": 2, "seed": 21, "F": 500.0},
        ]
        run_result = SimpleNamespace(
            scenario_name="场景",
            seed=999,
            algorithm="improved",
            wolf=SimpleNamespace(),
        )
        project_root = self.make_project_root('benchmark-export')

        with patch.object(bench, "run_algorithm", return_value=run_result) as mocked_run:
            with patch.object(bench, "export_result_json") as mocked_export:
                with patch.object(bench, "load_scenario", return_value=(None, [], "场景")):
                    bench.export_best_scenario_examples(
                        rows=rows,
                        algorithm="improved",
                        project_root=project_root,
                    )

        self.assertEqual(mocked_run.call_count, 2)
        self.assertEqual(mocked_export.call_count, 2)
        exported_paths = [Path(call.kwargs["output_path"]) for call in mocked_export.call_args_list]
        self.assertEqual(
            exported_paths,
            [
                project_root / "frontend" / "data" / "improved" / "scenario-1.json",
                project_root / "frontend" / "data" / "improved" / "scenario-2.json",
            ],
        )

    def test_write_markdown_includes_classic_algorithm_summaries(self):
        project_root = self.make_project_root("benchmark-md")
        md_path = project_root / "benchmark_summary.md"

        def row(algorithm: str, fitness: float) -> dict:
            return {
                "date": "2026-05-09",
                "batch_id": f"batch-{algorithm}",
                "algorithm": algorithm,
                "scenario": 1,
                "run": 1,
                "seed": 1,
                "F": fitness,
                "N": 1,
                "D": 10,
                "T": 0.0,
                "conflict_count": 0,
                "replan_count": 0,
                "deadlock_risk_count": 0,
                "deadlock_count": 0,
                "reroute_count": 0,
                "unfinished_count": 0,
            }

        bench.write_markdown(
            str(md_path),
            [
                row("original", 300.0),
                row("improved", 200.0),
                row("ga", 240.0),
                row("sa", 260.0),
            ],
        )

        text = md_path.read_text(encoding="utf-8")
        self.assertIn("## GA Summary", text)
        self.assertIn("## SA Summary", text)
        self.assertIn("Latest ga batch", text)
        self.assertIn("Latest sa batch", text)


if __name__ == "__main__":
    unittest.main()
