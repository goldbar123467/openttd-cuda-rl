#!/usr/bin/env python3
"""Unit and mutation tests for M22 fresh-process recovery evidence tooling."""

from __future__ import annotations

import json
import copy
import hashlib
import pathlib
import tempfile
import unittest

import jsonschema

import run_m22_recovery as runner
import validate_m22_recovery_evidence as validator


class M22RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.report = runner.load(cls.root / "config/v2/m22-recovery-evidence-v2.json")
        cls.historical_report = runner.load(cls.root / "config/v2/m22-recovery-evidence.json")

    @staticmethod
    def rehash(value: dict[str, object]) -> None:
        value.pop("report_sha256", None)
        value["report_sha256"] = hashlib.sha256(runner.canonical_bytes(value)).hexdigest()

    def mutation_fails(self, value: dict[str, object], pattern: str) -> None:
        self.rehash(value)
        with self.assertRaisesRegex((validator.M22RecoveryValidationError, runner.M22RecoveryError), pattern):
            validator.validate_value(value, self.root)

    @staticmethod
    def update() -> dict[str, object]:
        digest = "1" * 64
        return {
            "approximate_kl": 0.0,
            "clip_fraction": 0.0,
            "correct_program_fraction": 0.5,
            "entropy": 0.1,
            "explained_variance": 0.0,
            "gradient_norm": 0.2,
            "mean_rollout_reward": 1.0,
            "policy_loss": -0.1,
            "retention_ran": False,
            "stage": 0,
            "trace": {field: digest for field in runner.TRACE_FIELDS},
            "transitions": 128,
            "update": 1,
            "value_loss": 0.2,
        }

    def test_recovery_schema_is_strict_and_valid(self) -> None:
        schema = runner.load(self.root / runner.SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["configuration"]["properties"]["fork_update"]["const"], 16)
        self.assertIn("action_counts", schema["$defs"]["update"]["required"])
        self.assertIn("case_program_counts", schema["$defs"]["update"]["required"])

    def test_repository_recovery_evidence_passes(self) -> None:
        validator.validate_value(self.report, self.root)

    def test_historical_recovery_evidence_remains_valid(self) -> None:
        validator.validate_value(self.historical_report, self.root)

    def test_resumed_trace_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][0]["resumed"]["updates"][0]["trace"]["actions_sha256"] = "0" * 64
        self.mutation_fails(value, "update digest")

    def test_process_identity_reuse_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][0]["resumed"]["pid"] = value["runs"][0]["prefix"]["pid"]
        self.mutation_fails(value, "process identity")

    def test_checkpoint_semantic_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][1]["equivalence"]["fork_checkpoint_id"] = "0" * 64
        self.mutation_fails(value, "checkpoint summary identity")

    def test_source_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["source"]["files"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "source tree identity")

    def test_update_parser_accepts_complete_exact_trace(self) -> None:
        value = self.update()
        self.assertEqual(runner.parse_update(json.dumps(value)), value)

    def test_update_parser_rejects_missing_trace_field(self) -> None:
        value = self.update()
        del value["trace"]["actions_sha256"]  # type: ignore[index]
        with self.assertRaisesRegex(runner.M22RecoveryError, "trace field inventory"):
            runner.parse_update(json.dumps(value))

    def test_update_parser_rejects_nonfinite_metric(self) -> None:
        value = self.update(); value["entropy"] = float("nan")
        with self.assertRaisesRegex(runner.M22RecoveryError, "nonfinite"):
            runner.parse_update(json.dumps(value))

    def test_source_allowlist_excludes_final_manifest(self) -> None:
        self.assertNotIn(runner.FINAL_MANIFEST.as_posix(), runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/run_m22_recovery.py", runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/validate_m22_recovery_evidence.py", runner.SOURCE_PATHS)

    def test_sandbox_masks_final_and_unshares_network(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact = pathlib.Path(raw).resolve()
            command = runner.sandbox_command(
                pathlib.Path("/usr/bin/bwrap"), self.root, artifact,
                pathlib.Path("/bin/true"), pathlib.Path("/bin/true"), artifact / "checkpoints",
                runner.ARCHITECTURES[0], 1910917137, 16, None,
            )
        self.assertIn("--unshare-net", command)
        final_index = command.index(str(self.root / runner.FINAL_MANIFEST))
        self.assertEqual(command[final_index - 2:final_index], ["--ro-bind", "/dev/null"])
        child = command[command.index("--") + 1:]
        self.assertNotIn(str(self.root / runner.FINAL_MANIFEST), child)


if __name__ == "__main__":
    unittest.main()
