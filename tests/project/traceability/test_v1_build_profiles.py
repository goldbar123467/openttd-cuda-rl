#!/usr/bin/env python3
"""Unit and mutation tests for the V1 build-profile matrix."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_build_profiles


class V1BuildProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.matrix_path = cls.root / "config/v1/build-profile-matrix.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-build-profile-matrix.schema.json"
        cls.matrix = validate_build_profiles.load_json(cls.matrix_path)

    def validate_mutation(self, value: object) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "matrix.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return validate_build_profiles.validate(path, self.schema_path)

    @staticmethod
    def profile(value: dict[str, object], identifier: str) -> dict[str, object]:
        return next(item for item in value["profiles"] if item["id"] == identifier)  # type: ignore[index]

    def test_repository_matrix_is_complete(self) -> None:
        summary = validate_build_profiles.validate(self.matrix_path, self.schema_path)
        self.assertEqual(summary["profiles"], 7)
        self.assertEqual(summary["baselines"], 3)
        self.assertEqual(summary["pending_profiles"], 5)

    def test_profile_omission_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["profiles"].pop()
        with self.assertRaisesRegex(validate_build_profiles.BuildProfileError, "profiles.*too short"):
            self.validate_mutation(value)

    def test_python_runtime_dependency_fails_closed(self) -> None:
        value = copy.deepcopy(self.matrix)
        self.profile(value, "playable-inference-only")["dependencies"]["python_runtime"] = True  # type: ignore[index]
        with self.assertRaisesRegex(Exception, "python_runtime"):
            self.validate_mutation(value)

    def test_inference_package_rejects_training_dependency(self) -> None:
        value = copy.deepcopy(self.matrix)
        self.profile(value, "playable-inference-only")["dependencies"]["libtorch"] = True  # type: ignore[index]
        with self.assertRaisesRegex(validate_build_profiles.BuildProfileError, "dependency boundary"):
            self.validate_mutation(value)

    def test_dedicated_baseline_cannot_become_worker(self) -> None:
        value = copy.deepcopy(self.matrix)
        baseline = next(
            item
            for item in value["accepted_baselines"]
            if item["id"] == "dedicated-headless-release-evidence"
        )
        baseline["worker_eligible"] = True
        with self.assertRaisesRegex(validate_build_profiles.BuildProfileError, "worker eligible"):
            self.validate_mutation(value)

    def test_required_sanitizer_cannot_be_disabled(self) -> None:
        value = copy.deepcopy(self.matrix)
        self.profile(value, "asan")["instrumentation"]["address_sanitizer"] = False  # type: ignore[index]
        with self.assertRaisesRegex(validate_build_profiles.BuildProfileError, "does not enable"):
            self.validate_mutation(value)

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "matrix.json"
            path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(validate_build_profiles.BuildProfileError, "duplicate JSON key"):
                validate_build_profiles.load_json(path)


if __name__ == "__main__":
    unittest.main()
