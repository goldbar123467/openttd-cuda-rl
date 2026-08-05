#!/usr/bin/env python3
"""Mutation tests for complete retained M21 broad-feature evidence."""

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
import validate_m21_broad_evidence as validator


def _probe_result(
    case: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    probe = case["probe"]
    if probe == "calendar":
        snapshots = []
        for index, year in enumerate((1900, 1930, 1950, 1980, 2000, 2050, 2100)):
            snapshots.append({
                "airport_available": index % 2 == 0,
                "engines": {
                    "engine": {"available": index % 2 == 0, "expired": index % 3 == 0},
                },
                "year": year,
            })
        return {
            "cargo_count": 1,
            "save_load_exact": True,
            "snapshots": snapshots,
            "span_years": 200,
        }
    if probe == "authority_economy":
        return {
            "commands": [
                {"command": "CMD_TOWN_RATING", "status": "SUCCESS"},
                {"command": "CMD_TOWN_RATING_INVALID", "status": "REJECTED"},
                {"command": "CMD_DO_TOWN_ACTION_COMPETITOR", "status": "REJECTED"},
            ],
            "economy": {
                "inflation_after": 2,
                "inflation_before": 1,
                "payment_after": 2,
                "payment_before": 1,
                "price_after": 2,
                "price_before": 1,
                "recession_fluct": -1,
                "recovered_fluct": 1,
            },
            "exclusive_rights_expired": True,
            "save_load_exact": True,
            "subsidy": {"awarded_months": 12},
        }
    if probe == "events":
        return {
            "breakdown": {
                "disabled_no_event": True,
                "observed": True,
                "recovery_ticks": 1,
            },
            "disaster": {
                "disabled_no_event": True,
                "lifecycle_ticks": 1,
                "terminated": True,
            },
            "save_load_exact": True,
        }
    if probe == "gamescript":
        return {
            "commands": [{"status": "SUCCESS"} for _ in range(13)],
            "fixture_name": "M21CoverageFixture",
            "observed": {"goal": 1, "story": 1},
            "responses": {"goal_question": True, "story_button": True},
            "save_load_exact": True,
        }
    return {
        "arbitrary_newgrf_universality": False,
        "assets": {"vehicle": 1},
        "capabilities": contract["capabilities"],
        "capability_schema_closed": True,
        "package_count": 10,
    }


def make_live_evidence_fixture(
    directory: pathlib.Path,
    evidence: dict[str, Any],
    contract: dict[str, Any],
    source: dict[str, Any],
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path]:
    value = copy.deepcopy(evidence)
    artifact_set = directory / "v2-m21-broad-f"
    artifact_set.mkdir(parents=True)
    for record, case in zip(value["cases"], contract["cases"], strict=True):
        for replicate in record["replicates"]:
            name = replicate["name"]
            run_id = f"{case['case_id']}-{name}"
            report = {
                "active_content": [
                    {"id": item["id"], "md5": item["md5"]}
                    for item in contract["newgrfs"]
                ] if case["probe"] == "content" else [],
                "engine_source_tree": source["source"]["tree"],
                "executable_sha256": source["executable"]["sha256"],
                "identity": {
                    "content_lock_sha256": value["identities"]["content_lock_sha256"],
                    "contract_sha256": value["contract_sha256"],
                },
                "request": {
                    "landscape": case["landscape"],
                    "probe": case["probe"],
                    "run_id": run_id,
                    "seed": case["seed"],
                },
                "result": _probe_result(case, contract),
                "run_id": run_id,
                "schema_version": "openttd-rl-v2-m21-broad-report-1",
                "status": "PASS",
            }
            report_path = artifact_set / replicate["report_path"]
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
            replicate["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
            replicate["normalized_sha256"] = hashlib.sha256(validator.matrix.normalized(report)).hexdigest()
            if replicate["save"] is not None:
                save_path = pathlib.Path(str(report_path) + ".sav")
                save_path.write_bytes(b"relocated-save-fixture\n")
                replicate["save"] = {
                    "bytes": save_path.stat().st_size,
                    "sha256": hashlib.sha256(save_path.read_bytes()).hexdigest(),
                }
    for negative in value["negative_cases"]:
        log = artifact_set / negative["log_path"]
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"rejected: {negative['diagnostic']}\n", encoding="utf-8")
    config_path = directory / "evidence.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, artifact_set


class M21BroadEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.contract = validator.load(cls.root / validator.matrix.CONTRACT)
        cls.source = validator.load(cls.root / validator.matrix.SOURCE)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M21EvidenceError, pattern) if pattern else self.assertRaises(validator.M21EvidenceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value),
                                   artifact_context=ArtifactContext.offline())

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_evidence_passes(self) -> None:
        result = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual((result["cases"], result["runs"], result["twins"], result["features"], result["commands"]),
                         (16, 32, 16, 18, 145))

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

    def test_required_live_inputs_are_the_exact_report_save_and_log_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        expected: list[tuple[str, str | None]] = []
        for record in self.config["cases"]:
            for replicate in record["replicates"]:
                expected.append((replicate["report_path"], replicate["report_sha256"]))
                if replicate["save"] is not None:
                    expected.append((f"{replicate['report_path']}.sav", replicate["save"]["sha256"]))
        expected.extend((record["log_path"], None) for record in self.config["negative_cases"])
        self.assertEqual(len(requirements), 63)
        self.assertEqual([(item.relative_path, item.expected_sha256) for item in requirements], expected)
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m21-broad-f"})
        self.assertEqual({item.consumer for item in requirements}, {"m21-broad-evidence"})

    def test_relocated_live_reports_saves_and_logs_pass(self) -> None:
        retained = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            summary = validator.validate(self.root, config_path,
                                         artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual(self.config, retained)

    def test_live_report_tamper_fails_before_semantic_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            report = artifact_set / self.config["cases"][0]["replicates"][0]["report_path"]
            report.write_bytes(report.read_bytes() + b"tamper\n")
            with mock.patch.object(validator.matrix, "validate_report", side_effect=AssertionError("preflight did not run first")) as helper:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    validator.validate(self.root, config_path,
                                       artifact_context=ArtifactContext.live(base))
            helper.assert_not_called()

    def test_relocated_live_negative_log_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(
                base,
                self.config,
                self.contract,
                self.source,
            )
            first = self.config["negative_cases"][0]
            (artifact_set / first["log_path"]).write_text("wrong diagnostic\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M21EvidenceError, "negative rejection"):
                validator.validate(
                    self.root,
                    config_path,
                    artifact_context=ArtifactContext.live(base),
                )

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_case_metadata_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["landscape"] = "toyland"
        self.mutation_fails(value, "metadata")

    def test_report_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            value["cases"][0]["replicates"][0]["report_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path,
                                   artifact_context=ArtifactContext.live(base))

    def test_normalized_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            value["cases"][0]["replicates"][1]["normalized_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M21EvidenceError, "normalized report"):
                validator.validate(self.root, config_path,
                                   artifact_context=ArtifactContext.live(base))

    def test_save_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(base, self.config, self.contract, self.source)
            value["cases"][0]["replicates"][0]["save"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path,
                                   artifact_context=ArtifactContext.live(base))

    def test_negative_diagnostic_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["negative_cases"][0]["diagnostic"] = "wrong diagnostic"
        self.mutation_fails(value, "negative rejection")

    def test_contract_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["contract_sha256"] = "0" * 64
        self.mutation_fails(value, "contract identity")

    def test_coverage_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["coverage_sha256"] = "0" * 64
        self.mutation_fails(value, "coverage identity")


if __name__ == "__main__":
    unittest.main()
