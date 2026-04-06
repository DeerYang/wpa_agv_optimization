import json
import shutil
import unittest
from pathlib import Path

import numpy as np

from src.wpa_agv_optimization.exporter import (
    build_frontend_output_path,
    export_result_json,
    normalize_variant_key,
)


class DummyTask:
    def __init__(self, task_id, x, y, weight, deadline):
        self.id = task_id
        self.x = x
        self.y = y
        self.weight = weight
        self.deadline = deadline


class DummyAgv:
    def __init__(self):
        self.id = 1
        self.start_pos = (0, 0)
        self.tasks = [DummyTask(1, 2, 3, 10, 50)]
        self.load = 10
        self.finish_time = 12
        self.path = [(0, 0, 0), (2, 3, 12)]


class DummyWolf:
    def __init__(self):
        self.agv_list = [DummyAgv()]
        self.fitness = 123.4
        self.vehicle_num = 1
        self.total_dist = 9
        self.time_penalty = 2.5
        self.conflict_count = 0
        self.deadlock_count = 0
        self.deadlock_risk_count = 0
        self.replan_count = 0
        self.reroute_count = 0


class ExporterTests(unittest.TestCase):
    def make_project_root(self, name: str) -> Path:
        root = Path.cwd() / 'tests' / '_tmp' / name
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_normalize_variant_key_makes_safe_directory_name(self):
        self.assertEqual(normalize_variant_key(" improved budget/3 "), "improved-budget-3")

    def test_build_frontend_output_path_places_files_under_variant_directory(self):
        project_root = self.make_project_root('exporter-paths')
        path = build_frontend_output_path("improved", "result.json", project_root=project_root)
        self.assertEqual(path, project_root / "frontend" / "data" / "improved" / "result.json")

    def test_export_result_json_defaults_to_variant_result_path_and_updates_manifest(self):
        project_root = self.make_project_root('exporter-json')
        wolf = DummyWolf()
        tasks = [DummyTask(1, 2, 3, 10, 50)]
        grid_map = np.zeros((20, 20), dtype=int)

        output = export_result_json(
            wolf=wolf,
            grid_map=grid_map,
            task_list=tasks,
            scenario_name="test",
            algorithm="improved",
            project_root=str(project_root),
        )

        output_path = Path(output)
        self.assertEqual(output_path, project_root / "frontend" / "data" / "improved" / "result.json")
        self.assertTrue(output_path.exists())

        manifest_path = project_root / "frontend" / "data" / "manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest,
            {
                "variants": [
                    {
                        "key": "improved",
                        "label": "improved",
                        "files": ["result.json"],
                    }
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
