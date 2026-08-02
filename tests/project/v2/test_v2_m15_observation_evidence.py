#!/usr/bin/env python3
"""Mutation tests for frozen M15 bounded-observation evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import freeze_m15_observation_evidence
import qualify_m15_observation


class M15ObservationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = freeze_m15_observation_evidence.load_json(cls.root / freeze_m15_observation_evidence.CONFIG)
        cls.schema = cls.root / freeze_m15_observation_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "observation-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_evidence_passes(self) -> None:
        summary = freeze_m15_observation_evidence.validate(self.root)
        self.assertEqual((summary.cases, summary.passed), (4, 4))

    def test_live_artifacts_pass(self) -> None:
        artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl")
        if not (artifact_base / "v2-m15-observation-evidence-c").is_dir():
            self.skipTest("retained observation artifacts are unavailable")
        self.assertTrue(freeze_m15_observation_evidence.validate(self.root, artifact_base=artifact_base).live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_observation_evidence.M15ObservationEvidenceError, "schema SHA-256"):
                freeze_m15_observation_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_binary_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][0]["binary_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_observation_evidence.M15ObservationEvidenceError, "deterministic lock"):
                freeze_m15_observation_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_case_order_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][0], value["cases"][1] = value["cases"][1], value["cases"][0]
        value["summary"] = freeze_m15_observation_evidence.summarize(value["cases"])
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_observation_evidence.M15ObservationEvidenceError, "dimensions/order"):
                freeze_m15_observation_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_live_binary_corruption_fails(self) -> None:
        artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl")
        source_root = artifact_base / "v2-m15-observation-evidence-c"
        if not source_root.is_dir():
            self.skipTest("retained observation artifacts are unavailable")
        with tempfile.TemporaryDirectory() as raw:
            temporary_base = pathlib.Path(raw)
            target_root = temporary_base / "v2-m15-observation-evidence-c"
            import shutil
            shutil.copytree(source_root, target_root)
            binary = target_root / "reset-0064x0064" / "observation-metadata.bin"
            data = bytearray(binary.read_bytes())
            data[2048] ^= 1
            binary.write_bytes(data)
            with self.assertRaisesRegex(qualify_m15_observation.M15ObservationError, "SHA-256"):
                freeze_m15_observation_evidence.case_from_artifact(self.root, target_root, "reset-0064x0064")


if __name__ == "__main__":
    unittest.main()
