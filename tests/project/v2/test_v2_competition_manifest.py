#!/usr/bin/env python3
"""Mutation tests for the M14 competition preregistration."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext
import validate_competition_manifest


class CompetitionManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.manifest_path = cls.root / "config/v2/m14-competition-manifest.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-competition-manifest.schema.json"
        cls.manifest = validate_competition_manifest.load_json(cls.manifest_path)

    def validate_mutation(self, value: object) -> validate_competition_manifest.CompetitionManifestSummary:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "manifest.json"
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            return validate_competition_manifest.validate(self.root, path, self.schema_path)

    def test_nested_runtime_authority_is_explicitly_offline(self) -> None:
        with mock.patch.object(
            validate_competition_manifest.validate_opponent_runtime_evidence,
            "validate",
        ) as nested:
            validate_competition_manifest.validate(self.root)
        nested.assert_called_once_with(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )

    def test_schema_hash_drift_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "schema SHA-256"):
            self.validate_mutation(manifest)

    def test_runtime_evidence_drift_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["identity"]["runtime_evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "runtime evidence SHA-256"):
            self.validate_mutation(manifest)

    def test_incomplete_audit_pool_fails_schema(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["audit_pool_disposition"].pop()
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "schema failed"):
            self.validate_mutation(manifest)

    def test_admission_drift_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["audit_pool_disposition"][0]["admission"] = "EXCLUDED"
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "admission drifted"):
            self.validate_mutation(manifest)

    def test_scenario_required_ai_cannot_enter_tournament(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        source = next(item for item in manifest["audit_pool_disposition"] if item["name"] == "ShipAI")
        manifest["roster"]["tournament"].append({
            "name": source["name"],
            "content_unique_id": source["content_unique_id"],
            "admission": "TOURNAMENT",
            "package_evidence_sha256": "0" * 64,
            "runtime_evidence_sha256": "0" * 64,
        })
        manifest["roster"]["tournament"] = sorted(manifest["roster"]["tournament"], key=lambda item: item["name"])
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "exact admitted set"):
            self.validate_mutation(manifest)

    def test_floating_package_digest_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["roster"]["tournament"][0]["package_evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "package evidence digest"):
            self.validate_mutation(manifest)

    def test_seed_derivation_mutation_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["seed_protocol"]["sets"]["final"]["seeds"][0] += 1
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "deterministic derivation"):
            self.validate_mutation(manifest)

    def test_underpowered_final_seed_set_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["seed_protocol"]["sets"]["final"]["seeds"] = manifest["seed_protocol"]["sets"]["final"]["seeds"][:4]
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "underpowered"):
            self.validate_mutation(manifest)

    def test_asymmetric_slot_delay_legs_fail(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["fairness"]["paired_legs"][3]["rl_start_delay_days"] = 0
        manifest["fairness"]["paired_legs"][3]["opponent_start_delay_days"] = 365
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "symmetrically cross"):
            self.validate_mutation(manifest)

    def test_same_company_slot_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["fairness"]["paired_legs"][0]["opponent_slot"] = 0
        with self.assertRaises(validate_competition_manifest.CompetitionManifestError):
            self.validate_mutation(manifest)

    def test_missing_run_identity_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["scenario_contract"]["required_run_identity_fields"].remove("policy_package_sha256")
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "identity fields"):
            self.validate_mutation(manifest)

    def test_privileged_policy_visibility_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["policy_visibility"]["deny"].remove("opponent_ai_memory")
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "privileged state"):
            self.validate_mutation(manifest)

    def test_visibility_allow_deny_overlap_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["policy_visibility"]["allow"].append("opponent_ai_memory")
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "overlap"):
            self.validate_mutation(manifest)

    def test_missing_failure_policy_fails_schema(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        del manifest["failure_policy"]["missing_run_policy"]
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "schema failed"):
            self.validate_mutation(manifest)

    def test_run_deletion_policy_fails_schema(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["scoring"]["all_scheduled_runs_included"] = False
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "schema failed"):
            self.validate_mutation(manifest)

    def test_post_result_selection_fails_schema(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["integrity"]["post_result_selection_forbidden"] = False
        with self.assertRaisesRegex(validate_competition_manifest.CompetitionManifestError, "schema failed"):
            self.validate_mutation(manifest)


if __name__ == "__main__":
    unittest.main()
