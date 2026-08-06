#!/usr/bin/env python3
"""Unit and mutation tests for M22 fresh-process recovery evidence tooling."""

from __future__ import annotations

import json
import copy
import hashlib
import os
import pathlib
import subprocess
import tempfile
import unittest
from types import MappingProxyType
from unittest import mock

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    ValidationMode,
)
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

    def make_live_fixture(self, live_root: pathlib.Path) -> tuple[dict[str, object], LiveInputManifest]:
        value = copy.deepcopy(self.report)
        artifact_root = live_root / "recovery"
        artifact_root.mkdir()
        for run in value["runs"]:
            for process in (run["uninterrupted"], run["prefix"], run["resumed"]):
                log = artifact_root / process["log_path"]
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_bytes(f"byte-real {process['log_path']}\n".encode())
                process["stdout_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
                for checkpoint in process["checkpoints"]:
                    directory = artifact_root / checkpoint["path"]
                    directory.mkdir(parents=True, exist_ok=True)
                    files = []
                    for name in runner.INVENTORY:
                        path = directory / name
                        path.write_bytes(f"{checkpoint['id']}:{name}\n".encode())
                        files.append({
                            "bytes": path.stat().st_size,
                            "name": name,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        })
                    checkpoint["files"] = files
        executable = live_root / "campaign"
        executable.write_bytes(b"byte-real relocated campaign executable\n")
        corpus = live_root / "corpus.bin"
        corpus.write_bytes(b"byte-real relocated corpus\n")
        value["identity"]["campaign_executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        value["identity"]["corpus_binary_sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
        self.rehash(value)
        live_inputs = LiveInputManifest(
            ValidationMode.LIVE,
            live_root,
            MappingProxyType({
                "recovery-v2-artifacts": artifact_root,
                "v2-campaign-executable": executable,
                "v2-corpus-binary": corpus,
            }),
        )
        return value, live_inputs

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

    def test_offline_validation_never_reads_recovery_artifacts(self) -> None:
        with mock.patch.object(
            validator,
            "validate_artifacts",
            side_effect=AssertionError("offline recovery traversed retained artifacts"),
        ):
            validator.validate_value(
                self.report,
                self.root,
                artifact_context=ArtifactContext.offline(),
                live_inputs=LiveInputManifest.offline(),
            )

    def test_required_live_inputs_use_exact_v1_and_v2_roles_and_closures(self) -> None:
        for report_path, report, artifact_role, executable_role, corpus_role in (
            (
                self.root / "config/v2/m22-recovery-evidence.json",
                self.historical_report,
                "recovery-v1-artifacts",
                "recovery-v1-executable",
                "recovery-v1-corpus",
            ),
            (
                self.root / "config/v2/m22-recovery-evidence-v2.json",
                self.report,
                "recovery-v2-artifacts",
                "v2-campaign-executable",
                "v2-corpus-binary",
            ),
        ):
            with self.subTest(artifact_role=artifact_role):
                requirements = validator.required_live_inputs(self.root, report_path)
                expected_artifacts = []
                for run in report["runs"]:
                    for process in (run["uninterrupted"], run["prefix"], run["resumed"]):
                        expected_artifacts.append((process["log_path"], process["stdout_sha256"]))
                        for checkpoint in process["checkpoints"]:
                            expected_artifacts.extend(
                                (f"{checkpoint['path']}/{item['name']}", item["sha256"])
                                for item in checkpoint["files"]
                            )
                self.assertEqual(len(requirements), 92)
                self.assertEqual(
                    [(item.relative_path, item.expected_sha256) for item in requirements[:-2]],
                    expected_artifacts,
                )
                self.assertEqual({item.role for item in requirements[:-2]}, {artifact_role})
                self.assertEqual(
                    [(item.role, item.relative_path, item.expected_sha256) for item in requirements[-2:]],
                    [
                        (executable_role, ".", report["identity"]["campaign_executable_sha256"]),
                        (corpus_role, ".", report["identity"]["corpus_binary_sha256"]),
                    ],
                )

    def test_live_recovery_preflights_complete_closure_before_artifact_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            artifact_root = live_root / "recovery"
            artifact_root.mkdir()
            executable = live_root / "campaign"
            corpus = live_root / "corpus.bin"
            executable.write_bytes(b"wrong campaign bytes\n")
            corpus.write_bytes(b"wrong corpus bytes\n")
            live_inputs = LiveInputManifest(
                ValidationMode.LIVE,
                live_root,
                MappingProxyType({
                    "recovery-v2-artifacts": artifact_root,
                    "v2-campaign-executable": executable,
                    "v2-corpus-binary": corpus,
                }),
            )
            with (
                self.assertRaises(ArtifactContextError),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    self.report,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_relocated_live_recovery_logs_checkpoints_and_binaries_pass(self) -> None:
        retained = copy.deepcopy(self.report)
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            validator.validate_value(
                value,
                self.root,
                artifact_context=ArtifactContext.live(live_root),
                live_inputs=live_inputs,
            )
        self.assertEqual(self.report, retained)

    def test_relocated_live_recovery_digest_mutation_fails_before_artifact_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            first_log = live_inputs.resolve(validator._requirements_for_report(value)[0])
            first_log.write_bytes(first_log.read_bytes() + b"tampered\n")
            with (
                self.assertRaises(ArtifactContextError),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_recovery_cli_is_offline_by_default_and_removes_raw_binary_bypasses(self) -> None:
        script = self.root / "scripts/v2/validate_m22_recovery_evidence.py"
        report = self.root / validator.RECOVERY_V2
        completed = subprocess.run(
            ["python3", str(script), "--root", str(self.root), "--report", str(report)],
            cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("live=false", completed.stdout)
        removed = subprocess.run(
            [
                "python3", str(script), "--root", str(self.root), "--report", str(report),
                "--executable", "/tmp/executable", "--corpus", "/tmp/corpus",
            ],
            cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(removed.returncode, 2)
        self.assertIn("unrecognized arguments", removed.stderr)

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

    def test_checkpoint_path_traversal_fails_offline(self) -> None:
        value = copy.deepcopy(self.report)
        checkpoint = value["runs"][0]["uninterrupted"]["checkpoints"][0]
        checkpoint["path"] = "../outside/" + checkpoint["id"]
        self.mutation_fails(value, "checkpoint inventory/path")

    def test_source_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["source"]["files"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "source tree identity")

    def test_historical_source_commit_path_order_digest_and_inventory_mutations_fail(self) -> None:
        mutations = {
            "commit": lambda value: value["source"].__setitem__("repository_commit", "0" * 40),
            "path": lambda value: value["source"]["files"][0].__setitem__("path", "wrong/path"),
            "order": lambda value: value["source"]["files"].__setitem__(slice(0, 2), list(reversed(value["source"]["files"][:2]))),
            "digest": lambda value: value["source"]["files"][0].__setitem__("sha256", "0" * 64),
            "inventory": lambda value: value["source"].__setitem__("tree_sha256", "0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(self.report)
                mutate(value)
                self.mutation_fails(value, "source commit|source tree identity")

    def test_historical_git_reads_ignore_hostile_environment(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"GIT_DIR": "/missing-hostile-git-dir", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"},
            clear=False,
        ):
            validator.validate_value(self.report, self.root)

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
