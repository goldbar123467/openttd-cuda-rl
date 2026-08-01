#!/usr/bin/env python3
"""Unit and mutation tests for the V1 runtime-resource protocol."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import measure_runtime_resources


class V1RuntimeResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.plan_path = cls.root / "config/v1/resource-measurement-plan.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-resource-measurement-plan.schema.json"
        cls.plan = measure_runtime_resources.load_json(cls.plan_path)

    def validate_mutation(self, value: object) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "plan.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            loaded = measure_runtime_resources.load_json(path)
            measure_runtime_resources.validate_plan(loaded, self.schema_path)

    def test_repository_plan_is_complete_and_preregistered(self) -> None:
        measure_runtime_resources.validate_plan(self.plan, self.schema_path)
        self.assertEqual(self.plan["sampling"]["measurement_repetitions"], 5)
        self.assertEqual(self.plan["sampling"]["warmup_repetitions"], 1)

    def test_workload_omission_fails(self) -> None:
        value = copy.deepcopy(self.plan)
        value["workloads"].pop()
        with self.assertRaisesRegex(measure_runtime_resources.ResourceMeasurementError, "workloads.*too short"):
            self.validate_mutation(value)

    def test_throughput_metric_omission_fails(self) -> None:
        value = copy.deepcopy(self.plan)
        value["workloads"][1]["metrics"].remove("ticks_per_second")
        with self.assertRaisesRegex(measure_runtime_resources.ResourceMeasurementError, "metric inventory mismatch"):
            self.validate_mutation(value)

    def test_too_few_samples_fail_schema(self) -> None:
        value = copy.deepcopy(self.plan)
        value["sampling"]["measurement_repetitions"] = 1
        with self.assertRaisesRegex(measure_runtime_resources.ResourceMeasurementError, "less than the minimum"):
            self.validate_mutation(value)

    def test_aggregate_reports_median_and_full_range(self) -> None:
        samples = [
            {"wall_seconds": 3.0, "cpu_seconds": 2.0, "max_rss_kib": 30},
            {"wall_seconds": 1.0, "cpu_seconds": 4.0, "max_rss_kib": 10},
            {"wall_seconds": 2.0, "cpu_seconds": 3.0, "max_rss_kib": 20},
        ]
        result = measure_runtime_resources.aggregate(
            samples, ["wall_seconds", "cpu_seconds", "max_rss_kib"]
        )
        self.assertEqual(
            result["wall_seconds"],
            {"median": 2.0, "minimum": 1.0, "maximum": 3.0},
        )

    def test_accepted_identity_drift_fails_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            (root / "build-manifest.json").write_text(
                json.dumps({"result": "PASS", "build_identity_sha256": "0" * 64}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(measure_runtime_resources.ResourceMeasurementError, "identity mismatch"):
                measure_runtime_resources.load_accepted_binary(root, "1" * 64)

    def test_json_output_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "report.json"
            measure_runtime_resources.write_json(path, {"result": "PASS"})
            with self.assertRaisesRegex(measure_runtime_resources.ResourceMeasurementError, "refusing to overwrite"):
                measure_runtime_resources.write_json(path, {"result": "FAIL"})


if __name__ == "__main__":
    unittest.main()
