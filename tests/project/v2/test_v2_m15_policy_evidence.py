#!/usr/bin/env python3
"""Mutation tests for retained M15 scalable policy evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    resolve_artifact_root,
)
import validate_m15_policy_evidence


class M15PolicyEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_policy_evidence.load_json(cls.root / validate_m15_policy_evidence.CONFIG)
        cls.schema = cls.root / validate_m15_policy_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "policy-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            error = (
                self.assertRaisesRegex(validate_m15_policy_evidence.M15PolicyEvidenceError, pattern)
                if pattern
                else self.assertRaises(validate_m15_policy_evidence.M15PolicyEvidenceError)
            )
            with error:
                validate_m15_policy_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=(
                        ArtifactContext.live(self.live_base())
                        if live
                        else ArtifactContext.offline()
                    ),
                )

    def test_repository_evidence_passes(self) -> None:
        summary = validate_m15_policy_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual((summary.files, summary.devices, summary.parameters), (6, 2, 1239406))
        self.assertFalse(summary.live_source)
        self.assertFalse(summary.live_artifact)

    def test_live_source_and_artifact_pass(self) -> None:
        summary = validate_m15_policy_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary.live_source and summary.live_artifact)

    def test_relocated_source_and_build_use_one_artifact_context(self) -> None:
        value = copy.deepcopy(self.config)
        recorded_source = value["source"]["artifact_root"]
        recorded_build = value["build"]["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            artifact_root = base / "v2-m15-policy-a"
            source_root = artifact_root / "source"
            source_root.mkdir(parents=True)
            for item in value["source"]["files"]:
                source = self.root / "training/v2" / item["path"]
                target = source_root / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            subprocess.run(["git", "init", "-q", str(source_root)], check=True)
            subprocess.run(["git", "-C", str(source_root), "config", "user.name", "M15 fixture"], check=True)
            subprocess.run(["git", "-C", str(source_root), "config", "user.email", "m15-fixture@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(source_root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source_root), "commit", "-q", "-m", "fixture"], check=True)
            value["source"]["commit"] = subprocess.check_output(
                ["git", "-C", str(source_root), "rev-parse", "HEAD"],
                text=True,
            ).strip()
            value["source"]["tree"] = subprocess.check_output(
                ["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"],
                text=True,
            ).strip()

            executable = artifact_root / value["build"]["executable"]["path"]
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"x" * 1_000_000)
            value["build"]["executable"]["size"] = executable.stat().st_size
            value["build"]["executable"]["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
            contract_sha = value["identities"]["scalable_contract_sha256"]
            for run in value["runs"]:
                directory = artifact_root / run["artifact_directory"]
                checkpoint = directory / "checkpoints" / run["checkpoint_id"]
                checkpoint.mkdir(parents=True)
                payloads = {
                    "model.pt": b"model payload\n",
                    "optimizer.pt": b"optimizer payload\n",
                    "runtime.pt": b"runtime payload\n",
                    "state.bin": b"OTRLV2S1state payload\n",
                }
                for filename, data in payloads.items():
                    (checkpoint / filename).write_bytes(data)
                manifest = [
                    "schema=v2-m15-scalable-checkpoint-v1",
                    f"contract={contract_sha}",
                    f"checkpoint_id={run['checkpoint_id']}",
                    "boundary=after-completed-ppo-update-before-next-rollout",
                    f"model_sha256={hashlib.sha256(payloads['model.pt']).hexdigest()}",
                    f"optimizer_sha256={hashlib.sha256(payloads['optimizer.pt']).hexdigest()}",
                    f"runtime_sha256={hashlib.sha256(payloads['runtime.pt']).hexdigest()}",
                    f"state_sha256={hashlib.sha256(payloads['state.bin']).hexdigest()}",
                ]
                (checkpoint / "checkpoint.manifest").write_text("\n".join(manifest) + "\n", encoding="utf-8")
                (checkpoint / "COMMITTED").write_text(run["checkpoint_id"] + "\n", encoding="ascii")
                report = {
                    "schema_version": "openttd-rl-v2-m15-policy-report-1",
                    "contract_sha256": contract_sha,
                    **{
                        field: run[field]
                        for field in (
                            "device",
                            "parameter_count",
                            "forward_nanoseconds",
                            "reset_max_abs_error",
                            "checkpoint_max_abs_error",
                            "checkpoint_id",
                        )
                    },
                    "outputs": ["family_logits", "candidate_logits", "value", "next_hidden"],
                    "tests": {
                        "forward": "PASS",
                        "reset": "PASS",
                        "checkpoint": "PASS",
                        "device": "PASS",
                    },
                }
                report_path = directory / "policy-report.json"
                report_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
                run["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()

            requirements = tuple(
                ArtifactRequirement(
                    requirement.logical_set,
                    requirement.relative_path,
                    requirement.kind,
                    requirement.consumer,
                )
                for requirement in validate_m15_policy_evidence.required_live_inputs(self.root)
            )
            config_path = self.write(base, value)
            real_git = validate_m15_policy_evidence.git
            real_checkpoint = validate_m15_policy_evidence.validate_checkpoint
            with (
                mock.patch.object(
                    validate_m15_policy_evidence,
                    "required_live_inputs",
                    return_value=requirements,
                ),
                mock.patch.object(
                    validate_m15_policy_evidence,
                    "git",
                    wraps=real_git,
                ) as git_reader,
                mock.patch.object(
                    validate_m15_policy_evidence,
                    "validate_checkpoint",
                    wraps=real_checkpoint,
                ) as checkpoint_reader,
            ):
                summary = validate_m15_policy_evidence.validate(
                    self.root,
                    config_path,
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )

        self.assertTrue(summary.live_source and summary.live_artifact)
        self.assertEqual(value["source"]["artifact_root"], recorded_source)
        self.assertEqual(value["build"]["artifact_root"], recorded_build)
        self.assertTrue(all(call.args[0] == source_root for call in git_reader.call_args_list))
        self.assertEqual(
            [call.args[0] for call in checkpoint_reader.call_args_list],
            [
                artifact_root / run["artifact_directory"] / "checkpoints" / run["checkpoint_id"]
                for run in value["runs"]
            ],
        )

    def test_live_preflight_fails_before_source_or_build_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            (base / "v2-m15-policy-a").mkdir()
            with mock.patch.object(
                validate_m15_policy_evidence,
                "git",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validate_m15_policy_evidence.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_policy_closure(self) -> None:
        expected = [
            (".", "directory"),
            ("source", "directory"),
            ("source/.git", "directory"),
            *[(f"source/{item['path']}", "file") for item in self.config["source"]["files"]],
            ("build/m15_policy_gate", "file"),
        ]
        for run in self.config["runs"]:
            checkpoint = f"{run['artifact_directory']}/checkpoints/{run['checkpoint_id']}"
            expected.extend([
                (f"{run['artifact_directory']}/policy-report.json", "file"),
                (checkpoint, "directory"),
                (f"{checkpoint}/COMMITTED", "file"),
                (f"{checkpoint}/checkpoint.manifest", "file"),
                (f"{checkpoint}/model.pt", "file"),
                (f"{checkpoint}/optimizer.pt", "file"),
                (f"{checkpoint}/runtime.pt", "file"),
                (f"{checkpoint}/state.bin", "file"),
            ])
        requirements = validate_m15_policy_evidence.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.relative_path, item.kind) for item in requirements),
            tuple(expected),
        )
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m15-policy-a"})
        self.assertEqual({item.consumer for item in requirements}, {"m15-policy-evidence"})
        by_path = {item.relative_path: item for item in requirements}
        self.assertEqual(
            by_path["build/m15_policy_gate"].expected_sha256,
            self.config["build"]["executable"]["sha256"],
        )
        self.assertEqual(
            by_path["cpu/policy-report.json"].expected_sha256,
            self.config["runs"][0]["report_sha256"],
        )

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_source_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["source"]["files"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "repository policy source")

    def test_device_omission_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["runs"].pop()
        self.mutation_fails(value)

    def test_report_digest_drift_fails_live(self) -> None:
        value = copy.deepcopy(self.config)
        value["runs"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "policy report drifted", live=True)

    def test_executable_digest_drift_fails_live(self) -> None:
        value = copy.deepcopy(self.config)
        value["build"]["executable"]["sha256"] = "0" * 64
        self.mutation_fails(value, "executable SHA-256", live=True)


if __name__ == "__main__":
    unittest.main()
