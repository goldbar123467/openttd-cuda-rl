#!/usr/bin/env python3
"""Mutation tests for complete native M19 aircraft evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
import validate_m19_air_evidence as validator


def _probe(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record["metrics"]
    if record["probe"] == "catalog":
        return {"status": "CATALOG_ONLY"}
    if record["probe"] == "construction":
        return {
            "buildable_types": list(range(9)),
            "disabled_oilrig_rejected": True,
            "footprint_mask": [True],
            "ownership_mask": [True],
            "spread_mask": [True],
            "terrain_mask": [True],
        }
    if record["probe"] == "lifecycle":
        return {
            "clone_and_sale": True,
            "range_mask": {"bounded_rejected": True, "limit": 8, "unlimited_accepted": True},
            "replacement": {"executed": True, "from_engine": 1, "to_engine": 2},
            "save_load": {"bytes": 64, "restored": True},
            "timetable": {"speed_limit_rejected": True, "travel": 256, "wait": 64},
        }
    if record["probe"] == "occupancy":
        return {"aircraft": 4, "block_state_count": 3, "headings": [14], "nonzero_block_ticks": 1,
                "peak_destination_contenders": 2}
    if record["probe"] == "failure":
        return {"airport_close_open": True, "crash": {"crashed": True, "seeded_fixture": True}, "removal_blocked": True}
    if record["probe"] in ("service", "helicopter"):
        return {
            "accounting": {"delivered": metrics["delivered"], "income": metrics["income"],
                           "payment_events": [{"transfer": False}]},
            "aircraft": {"kind": "airplane" if record["probe"] == "service" else "helicopter"},
            "ticks": metrics["ticks"],
        }
    if record["probe"] == "multimodal":
        return {
            "conservation": {"delivered": metrics["delivered"], "loaded": metrics["delivered"], "transferred": metrics["delivered"]},
            "final": {"company_income_delta": metrics["income"], "payment_count": 1},
            "modes": ["road", "water", "air"],
            "ticks": {"air": metrics["ticks"] - 2, "road": 1, "water": 1},
            "transfer_payment_count": 2,
        }
    if record["probe"] == "recovery":
        return {"delivery": {"delivered": metrics["delivered"], "income": metrics["income"]}, "recovery_ticks": metrics["ticks"],
                "reopened": True, "saw_flying_while_closed": True}
    return {"checkpoint_exact": True, "edges": list(range(8)), "no_privileged_inputs": True,
            "route_costs": {"cargo_sink": 14, "passenger_sink": 6}}


def make_live_evidence_fixture(
    directory: pathlib.Path,
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path]:
    value = copy.deepcopy(evidence)
    artifact_set = directory / "v2-m19-air-matrix-a"
    artifact_set.mkdir(parents=True)
    for record in value["cases"]:
        for twin in record["twins"]:
            run_id = f"{record['case_id']}-{twin['name']}"
            report = {
                "catalog": {
                    "aircraft_engines": [
                        {"kind": "helicopter" if index < 3 else "airplane"}
                        for index in range(41)
                    ],
                    "airport_specs": [{"enabled": index < 9} for index in range(10)],
                    "movement_blocks": 64,
                    "movement_headings": 22,
                },
                "executable_sha256": value["executable_sha256"],
                "map": {"height": 64, "width": 64},
                "probe": _probe(record),
                "request": {"cargo_label": record["cargo"], "probe": record["probe"], "run_id": run_id, "seed": record["seed"]},
                "run_id": run_id,
                "schema_version": "openttd-rl-v2-m19-air-report-1",
                "status": "PASS",
            }
            path = artifact_set / twin["report_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
            twin["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            twin["normalized_sha256"] = hashlib.sha256(validator.matrix.normalized(report)).hexdigest()
    config_path = directory / "evidence.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, artifact_set


class M19AirEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.schema = cls.root / validator.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M19EvidenceError, pattern) if pattern else self.assertRaises((validator.M19EvidenceError, ValueError))
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema,
                                   artifact_context=ArtifactContext.offline())

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_evidence_passes(self) -> None:
        summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual((summary["cases"], summary["runs"], summary["twin_exact"]), (20, 40, 20))

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        real_load = validator.load

        def reject_retained(path: pathlib.Path) -> dict[str, object]:
            candidate = pathlib.Path(path)
            if candidate.is_absolute() and not candidate.is_relative_to(self.root):
                raise AssertionError("unexpected live read")
            return real_load(candidate)

        with mock.patch.object(validator, "load", side_effect=reject_retained):
            summary = validator.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary["live"])

    def test_retained_live_evidence_passes(self) -> None:
        self.assertTrue(validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )["live"])

    def test_required_live_inputs_are_the_exact_report_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        expected = [
            (twin["report_path"], twin["report_sha256"])
            for record in self.config["cases"]
            for twin in record["twins"]
        ]
        self.assertEqual(len(requirements), 40)
        self.assertEqual([(item.relative_path, item.expected_sha256) for item in requirements], expected)
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m19-air-matrix-a"})
        self.assertEqual({item.consumer for item in requirements}, {"m19-air-evidence"})

    def test_relocated_live_reports_pass(self) -> None:
        retained = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _ = make_live_evidence_fixture(base, self.config)
            summary = validator.validate(self.root, config_path, self.schema,
                                         artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual(self.config, retained)

    def test_live_tamper_fails_preflight_before_semantic_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(base, self.config)
            report = artifact_set / self.config["cases"][0]["twins"][0]["report_path"]
            report.write_bytes(report.read_bytes() + b"tamper\n")
            with mock.patch.object(validator.matrix, "validate_common", side_effect=AssertionError("preflight did not run first")) as helper:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    validator.validate(self.root, config_path, self.schema,
                                       artifact_context=ArtifactContext.live(base))
            helper.assert_not_called()

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_case_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][5]["seed"] ^= 1
        self.mutation_fails(value, "metadata")

    def test_vacuous_income_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        target = next(item for item in value["cases"] if item["probe"] == "service")
        target["metrics"]["income"] = 0
        self.mutation_fails(value, "metrics")

    def test_report_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config)
            value["cases"][0]["twins"][0]["report_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_twin_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["twins"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "normalized report")

    def test_baseline_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["baselines"]["lufthansa"]["archive_sha256"] = "0" * 64
        self.mutation_fails(value, "baseline")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
