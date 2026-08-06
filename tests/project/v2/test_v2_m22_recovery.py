#!/usr/bin/env python3
"""Unit and mutation tests for M22 fresh-process recovery evidence tooling."""

from __future__ import annotations

import json
import copy
import hashlib
import inspect
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


CHECKPOINT_SCHEMA = "v2-m22-generalist-checkpoint-v1"
CHECKPOINT_BOUNDARY = "after-completed-ppo-update-and-retention-check-before-next-rollout"


def fixture_checkpoint_id(fields: dict[str, str]) -> str:
    identity = "\n".join((
        fields["schema"], fields["contract"], fields["corpus"], fields["architecture"],
        fields["run_seed"], fields["model_sha256"], fields["optimizer_sha256"],
        fields["runtime_sha256"], fields["trainer_state_sha256"],
        fields["selection_sha256"], fields["boundary"],
    )) + "\n"
    return hashlib.sha256(identity.encode("ascii")).hexdigest()


def write_checkpoint_fixture(
    parent: pathlib.Path,
    architecture: str,
    seed: int,
    update: int,
    contract_sha256: str,
    corpus_sha256: str,
) -> tuple[str, list[dict[str, object]]]:
    payloads = {
        "model.pt": f"fixture model {architecture} {seed} {update}\n".encode(),
        "optimizer.pt": f"fixture optimizer {architecture} {seed} {update}\n".encode(),
        "runtime.pt": f"fixture runtime {architecture} {seed} {update}\n".encode(),
        "selection.json": f'{{"architecture":"{architecture}","seed":{seed},"update":{update}}}\n'.encode(),
        "trainer-state.bin": f"fixture trainer state {architecture} {seed} {update}\n".encode(),
    }
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    fields = {
        "schema": CHECKPOINT_SCHEMA,
        "contract": contract_sha256,
        "corpus": corpus_sha256,
        "architecture": architecture,
        "run_seed": str(seed),
        "checkpoint_id": "",
        "model_sha256": digests["model.pt"],
        "optimizer_sha256": digests["optimizer.pt"],
        "runtime_sha256": digests["runtime.pt"],
        "trainer_state_sha256": digests["trainer-state.bin"],
        "selection_sha256": digests["selection.json"],
        "boundary": CHECKPOINT_BOUNDARY,
    }
    checkpoint_id = fixture_checkpoint_id(fields)
    fields["checkpoint_id"] = checkpoint_id
    directory = parent / checkpoint_id
    directory.mkdir(parents=True)
    for name, data in payloads.items():
        (directory / name).write_bytes(data)
    manifest = "".join(f"{name}={value}\n" for name, value in fields.items()).encode("ascii")
    (directory / "m22.manifest").write_bytes(manifest)
    (directory / "COMMITTED").write_text(checkpoint_id + "\n", encoding="ascii")
    files = [
        {
            "bytes": (directory / name).stat().st_size,
            "name": name,
            "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
        }
        for name in runner.INVENTORY
    ]
    return checkpoint_id, files


def replace_manifest_field(path: pathlib.Path, name: str, value: str) -> None:
    fields = [line.split("=", 1) for line in path.read_text(encoding="ascii").splitlines()]
    replaced = False
    for field in fields:
        if field[0] == name:
            field[1] = value
            replaced = True
    if not replaced:
        raise AssertionError(f"fixture manifest has no field {name}")
    path.write_text("".join(f"{key}={field_value}\n" for key, field_value in fields), encoding="ascii")


def refresh_file_record(checkpoint: dict[str, object], path: pathlib.Path) -> None:
    record = next(item for item in checkpoint["files"] if item["name"] == path.name)
    record["bytes"] = path.stat().st_size
    record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


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
                    old_path = pathlib.PurePosixPath(checkpoint["path"])
                    checkpoint_id, files = write_checkpoint_fixture(
                        artifact_root.joinpath(*old_path.parent.parts),
                        run["architecture"],
                        value["configuration"]["run_seed"],
                        checkpoint["update"],
                        value["identity"]["learning_contract_sha256"],
                        value["identity"]["native_corpus_sha256"],
                    )
                    checkpoint["id"] = checkpoint_id
                    checkpoint["path"] = (old_path.parent / checkpoint_id).as_posix()
                    checkpoint["files"] = files
            run["equivalence"]["fork_checkpoint_id"] = runner.checkpoint(run["uninterrupted"], 16)["id"]
            run["equivalence"]["final_checkpoint_id"] = runner.checkpoint(run["uninterrupted"], 24)["id"]
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

    def test_checkpoint_id_matches_independent_known_vector(self) -> None:
        fields = {
            "schema": CHECKPOINT_SCHEMA,
            "contract": "f3ae8f89dfb6edf19b910c55f55845279b77ddd7be5adbd1db244984f968b07b",
            "corpus": "0af952bb840bca2a80a577e2a2446845f2db749d7efbaeb06af4b94418ff6725",
            "architecture": "monolithic-generalist-v1",
            "run_seed": "1910917137",
            "checkpoint_id": "b3287db94dac71a60c49450a08329b1a1bb6d39aa9c863db54ccc3d997e31191",
            "model_sha256": "e0554296df9d00a53f6b2143bc14b90ddf028cacb4d1f9ccf981f9cf589a112f",
            "optimizer_sha256": "b987dfffc07ebfdb016b88ff9a44394d48c8cf761361681312263ea20ff8b28f",
            "runtime_sha256": "dfb662847c93827e445ff22de3919ffd1f13e68bf2c04290c38238e0ba742f3e",
            "trainer_state_sha256": "69c7d03873ffbcd1dd44e42b96e6e6b5e726936825d303bc0b6db6e16b54fae5",
            "selection_sha256": "d782ea7a2015796f4c7b543d06f8fc0120791da423402dc8b2dec162b2c6e581",
            "boundary": CHECKPOINT_BOUNDARY,
        }
        self.assertEqual(validator._checkpoint_id(fields), fields["checkpoint_id"])

    def test_live_checkpoint_manifest_binds_every_field_and_payload(self) -> None:
        mutations = {
            "schema": "wrong-checkpoint-schema",
            "contract": "0" * 64,
            "corpus": "0" * 64,
            "architecture": "specialist-router-v1",
            "run_seed": "1910917138",
            "checkpoint_id": "0" * 64,
            "model_sha256": "0" * 64,
            "optimizer_sha256": "0" * 64,
            "runtime_sha256": "0" * 64,
            "trainer_state_sha256": "0" * 64,
            "selection_sha256": "0" * 64,
            "boundary": "wrong-boundary",
        }
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            base_value, live_inputs = self.make_live_fixture(live_root)
            paired = [
                runner.checkpoint(base_value["runs"][0]["uninterrupted"], 8),
                runner.checkpoint(base_value["runs"][0]["prefix"], 8),
            ]
            artifact_root = live_root / "recovery"
            paths = [artifact_root / item["path"] / "m22.manifest" for item in paired]
            originals = [path.read_bytes() for path in paths]
            for field, replacement in mutations.items():
                with self.subTest(field=field):
                    value = copy.deepcopy(base_value)
                    mutated = [
                        runner.checkpoint(value["runs"][0]["uninterrupted"], 8),
                        runner.checkpoint(value["runs"][0]["prefix"], 8),
                    ]
                    try:
                        for path, checkpoint in zip(paths, mutated):
                            replace_manifest_field(path, field, replacement)
                            refresh_file_record(checkpoint, path)
                        self.rehash(value)
                        with self.assertRaisesRegex(validator.M22RecoveryValidationError, "checkpoint manifest|checkpoint identity"):
                            validator.validate_value(
                                value,
                                self.root,
                                artifact_context=ArtifactContext.live(live_root),
                                live_inputs=live_inputs,
                            )
                    finally:
                        for path, original in zip(paths, originals):
                            path.write_bytes(original)

            value = copy.deepcopy(base_value)
            mutated = [
                runner.checkpoint(value["runs"][0]["uninterrupted"], 8),
                runner.checkpoint(value["runs"][0]["prefix"], 8),
            ]
            payloads = [artifact_root / item["path"] / "model.pt" for item in mutated]
            original_payloads = [path.read_bytes() for path in payloads]
            try:
                for path, checkpoint in zip(payloads, mutated):
                    path.write_bytes(b"payload changed without a new content address\n")
                    refresh_file_record(checkpoint, path)
                self.rehash(value)
                with self.assertRaisesRegex(validator.M22RecoveryValidationError, "checkpoint payload|checkpoint identity"):
                    validator.validate_value(
                        value,
                        self.root,
                        artifact_context=ArtifactContext.live(live_root),
                        live_inputs=live_inputs,
                    )
            finally:
                for path, original in zip(payloads, original_payloads):
                    path.write_bytes(original)

    def test_live_recovery_closes_checkpoint_directories_before_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            checkpoint = value["runs"][0]["uninterrupted"]["checkpoints"][0]
            directory = live_root / "recovery" / checkpoint["path"]
            (directory / "unexpected.bin").write_bytes(b"extra checkpoint entry\n")
            with (
                self.assertRaisesRegex(validator.M22RecoveryValidationError, "exact inventory"),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_live_recovery_rejects_cross_checkpoint_hardlink_before_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            source_checkpoint = runner.checkpoint(value["runs"][0]["uninterrupted"], 8)
            target_checkpoints = [
                runner.checkpoint(value["runs"][1]["uninterrupted"], 8),
                runner.checkpoint(value["runs"][1]["prefix"], 8),
            ]
            artifact_root = live_root / "recovery"
            source = artifact_root / source_checkpoint["path"] / "model.pt"
            for checkpoint in target_checkpoints:
                target = artifact_root / checkpoint["path"] / "model.pt"
                target.unlink()
                os.link(source, target)
                refresh_file_record(checkpoint, target)
            self.rehash(value)
            with (
                self.assertRaisesRegex(validator.M22RecoveryValidationError, "physical file alias"),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_live_recovery_missing_or_symlink_entry_fails_in_preflight(self) -> None:
        for mutation in ("missing", "symlink"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                live_root = pathlib.Path(raw).resolve()
                value, live_inputs = self.make_live_fixture(live_root)
                checkpoint = value["runs"][0]["uninterrupted"]["checkpoints"][0]
                target = live_root / "recovery" / checkpoint["path"] / "model.pt"
                if mutation == "missing":
                    target.unlink()
                else:
                    real = target.with_name("model-real.pt")
                    target.rename(real)
                    target.symlink_to(real)
                with (
                    self.assertRaises(ArtifactContextError),
                    mock.patch.object(validator, "_validate_live_structure") as structure_guard,
                    mock.patch.object(validator, "validate_artifacts") as artifact_reader,
                ):
                    validator.validate_value(
                        value,
                        self.root,
                        artifact_context=ArtifactContext.live(live_root),
                        live_inputs=live_inputs,
                    )
                structure_guard.assert_not_called()
                artifact_reader.assert_not_called()

    def test_malformed_checkpoint_manifest_raises_recovery_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            paired = [
                runner.checkpoint(value["runs"][0]["uninterrupted"], 8),
                runner.checkpoint(value["runs"][0]["prefix"], 8),
            ]
            for checkpoint in paired:
                path = live_root / "recovery" / checkpoint["path"] / "m22.manifest"
                lines = path.read_text(encoding="ascii").splitlines()
                path.write_text("\n".join(lines[:-1]) + "\n", encoding="ascii")
                refresh_file_record(checkpoint, path)
            self.rehash(value)
            with self.assertRaisesRegex(
                validator.M22RecoveryValidationError,
                "checkpoint manifest field count",
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )

    def test_public_validate_has_no_raw_path_bypass_and_loads_live_manifest(self) -> None:
        parameters = inspect.signature(validator.validate).parameters
        self.assertEqual(list(parameters), ["report_path", "root", "artifact_context"])
        self.assertEqual(parameters["artifact_context"].kind, inspect.Parameter.KEYWORD_ONLY)
        report_path = self.root / validator.RECOVERY_V2
        with self.assertRaises(TypeError):
            validator.validate(report_path, self.root, self.root)
        with self.assertRaises(TypeError):
            validator.validate(report_path, self.root, artifact_root=self.root)
        with mock.patch.object(
            validator,
            "validate_artifacts",
            side_effect=AssertionError("contextless public validation read retained paths"),
        ):
            self.assertEqual(validator.validate(report_path, self.root), {"live": False})

        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            relocated_report = live_root / "recovery.json"
            relocated_report.write_bytes(runner.canonical_bytes(value) + b"\n")
            with mock.patch.object(validator.LiveInputManifest, "load", return_value=live_inputs):
                self.assertEqual(
                    validator.validate(
                        relocated_report,
                        self.root,
                        artifact_context=ArtifactContext.live(live_root),
                    ),
                    {"live": True},
                )

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

    def test_recovery_log_paths_are_safe_unique_and_process_bound_offline(self) -> None:
        mutations = {
            "parent": "../escape.log",
            "absolute": "/tmp/campaign.log",
            "dot": "./campaign.log",
            "empty": "",
            "empty-component": "monolithic-generalist-v1//campaign.log",
            "backslash": "monolithic-generalist-v1\\campaign.log",
            "nul": "monolithic-generalist-v1/campaign\x00.log",
            "duplicate": self.report["runs"][0]["uninterrupted"]["log_path"],
        }
        for label, path in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(self.report)
                target = value["runs"][0]["prefix"] if label == "duplicate" else value["runs"][0]["uninterrupted"]
                target["log_path"] = path
                self.rehash(value)
                with self.assertRaisesRegex(validator.M22RecoveryValidationError, "log path|log_path"):
                    validator.validate_value(value, self.root)

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
