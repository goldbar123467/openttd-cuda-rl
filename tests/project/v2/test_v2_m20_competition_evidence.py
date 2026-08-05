#!/usr/bin/env python3
"""Mutation tests for complete native M20 competition evidence."""

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
import validate_m20_competition_evidence as validator


def _report(
    case: Any,
    replicate: str,
    metrics: dict[str, Any],
    evidence: dict[str, Any],
    source: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    run_id = f"{case.case_id}-{replicate}"
    events = [{"kind": "rl_started"}, {"kind": "rl_service_started"}]
    events.extend({"kind": "opponent_started"} for _ in case.opponents)
    if case.probe == "fault":
        events.append({"kind": "opponent_failure_contained"})
    if case.probe == "interaction":
        events.extend({"kind": kind} for kind in ("subsidy_awarded", "company_acquired", "ownership_collision_rejected"))
    opponents = []
    for opponent, state, difference in zip(
        case.opponents,
        metrics["opponent_states"],
        metrics["company_value_differences"],
        strict=True,
    ):
        opponents.append({
            "company_value_difference": difference,
            "name": opponent.name,
            "public_state": dict(state),
        })
    interaction = None
    if case.probe == "interaction":
        interaction = {
            "collision_disposition": {
                "crashed_vehicles_scored": True,
                "ownership_collision_rejected": True,
                "physical_plane_crashes_disabled": True,
            },
            "subsidy_awarded": True,
            "target_removed": True,
        }
    return {
        "engine_source_tree": source["source"]["tree"],
        "executable_sha256": source["executable"]["sha256"],
        "identity": evidence["identities"],
        "request": {
            "calendar_days": contract["development_qualification"]["calendar_days"],
            "map_seed": case.map_seed,
            "opponents": [opponent.manifest() for opponent in case.opponents],
            "probe": case.probe,
            "rl_slot": case.rl_slot,
            "rl_start_delay_days": case.rl_delay,
            "run_id": run_id,
            "simulation_seed": case.simulation_seed,
            "split": "development",
        },
        "result": {
            "events": events,
            "fault_contained": metrics["fault_contained"],
            "interaction": interaction,
            "policy_input": {
                "public_companies": [],
                "public_events": [],
                "public_map": {},
                "schema_version": "fixture",
                "self_company_id": 0,
            },
            "policy_input_fields": contract["public_observation"]["allowed_policy_fields"],
            "privileged_inputs": [],
            "save_bytes": 64,
            "save_load_public_exact": True,
            "score": {
                "opponents": opponents,
                "rl": {**metrics["rl"], "aircraft": 1, "crashed_vehicles": 0},
            },
        },
        "run_id": run_id,
        "schema_version": "openttd-rl-v2-m20-competition-report-1",
        "status": "PASS",
    }


def make_live_evidence_fixture(
    directory: pathlib.Path,
    evidence: dict[str, Any],
    contract: dict[str, Any],
    source: dict[str, Any],
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path]:
    value = copy.deepcopy(evidence)
    artifact_set = directory / "v2-m20-competition-matrix-f"
    artifact_set.mkdir(parents=True)
    cases = validator.matrix.cases(contract)
    for record, case in zip(value["cases"], cases, strict=True):
        for index, replicate in enumerate(record["replicates"]):
            report = _report(case, replicate["name"], record["replicate_metrics"][index], value, source, contract)
            path = artifact_set / replicate["report_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
            replicate["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            replicate["normalized_sha256"] = hashlib.sha256(validator.matrix.normalized(report)).hexdigest()
    config_path = directory / "evidence.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, artifact_set


class M20CompetitionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.contract = validator.load(cls.root / validator.matrix.CONTRACT)
        cls.source = validator.load(cls.root / validator.matrix.SOURCE)
        cls.schema = cls.root / validator.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M20EvidenceError, pattern) if pattern else self.assertRaises((validator.M20EvidenceError, ValueError))
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
        self.assertEqual((summary["cases"], summary["runs"], summary["replay_exact"]), (32, 64, 32))

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
            (replicate["report_path"], replicate["report_sha256"])
            for record in self.config["cases"]
            for replicate in record["replicates"]
        ]
        self.assertEqual(len(requirements), 64)
        self.assertEqual([(item.relative_path, item.expected_sha256) for item in requirements], expected)
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m20-competition-matrix-f"})
        self.assertEqual({item.consumer for item in requirements}, {"m20-competition-evidence"})

    def test_relocated_live_reports_pass(self) -> None:
        retained = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            summary = validator.validate(self.root, config_path, self.schema,
                                         artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual(self.config, retained)

    def test_live_tamper_fails_preflight_before_semantic_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            report = artifact_set / self.config["cases"][0]["replicates"][0]["report_path"]
            report.write_bytes(report.read_bytes() + b"tamper\n")
            with mock.patch.object(validator.matrix, "validate_common", side_effect=AssertionError("preflight did not run first")) as helper:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    validator.validate(self.root, config_path, self.schema,
                                       artifact_context=ArtifactContext.live(base))
            helper.assert_not_called()

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_fairness_leg_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["leg"] = "D"
        self.mutation_fails(value, "metadata")

    def test_report_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            value["cases"][0]["replicates"][0]["report_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_replay_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            value["cases"][0]["replicates"][1]["normalized_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20EvidenceError, "normalized report"):
                validator.validate(self.root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_metric_projection_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            value["cases"][0]["replicate_metrics"][0]["rl"]["delivered_cargo_units"] = 0
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20EvidenceError, "metric projection"):
                validator.validate(self.root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_scoring_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["scoring"]["overall_mean_company_value_difference"] += 1
        self.mutation_fails(value, "scoring")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
