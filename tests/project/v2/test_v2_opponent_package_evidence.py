#!/usr/bin/env python3
"""Mutation tests for the M14 opponent acquisition evidence index."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import pathlib
import re
import shlex
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    LiveInputManifest,
    RoleRequirement,
    resolve_artifact_root,
)
import artifact_context
import validate_opponent_package_evidence


class OpponentPackageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence_path = cls.root / "config/v2/opponent-package-evidence.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-opponent-package-evidence.schema.json"
        cls.evidence = validate_opponent_package_evidence.load_json(cls.evidence_path)

    @staticmethod
    def write_json(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "opponent-package-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> validate_opponent_package_evidence.OpponentEvidenceSummary:
        return validate_opponent_package_evidence.validate(
            self.root,
            self.write_json(directory, value),
            self.schema_path,
        )

    def make_live_fixture(self, directory: pathlib.Path) -> dict[str, object]:
        artifact_root = directory / "relocated-artifacts"
        artifact_root.mkdir()
        executable = artifact_root / "m14-openttd"
        with executable.open("wb") as stream:
            stream.truncate(self.evidence["executable"]["size"])
        evidence = copy.deepcopy(self.evidence)
        records: dict[pathlib.Path, dict[str, object]] = {}
        locked_paths: list[pathlib.Path] = []
        rejection_paths: list[pathlib.Path] = []
        for result in evidence["results"]:
            artifact_set = artifact_root / result["artifact_dir"]
            artifact_set.mkdir()
            evidence_file = artifact_set / result["evidence_file"]
            if result["outcome"] == "LOCKED":
                archive_relative = f"content_download/{result['content_unique_id']}.tar"
                archive = artifact_set / archive_relative
                archive.parent.mkdir()
                archive.write_bytes(f"archive:{result['name']}\n".encode("utf-8"))
                package = {
                    "local_unique_id": result["content_unique_id"],
                    "archive_path": archive_relative,
                    "archive_size": archive.stat().st_size,
                    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "licenses": ["COPYING"],
                }
                record = {"packages": [package]}
                result["package_count"] = 1
                result["archive_bytes"] = package["archive_size"]
                result["license_files"] = 1
                result["closure_sha256"] = (
                    validate_opponent_package_evidence.closure_sha256([package])
                )
                locked_paths.append(evidence_file)
            else:
                transcript = artifact_set / "openttd-content-console.log"
                transcript.write_text(f"rejected:{result['name']}\n", encoding="utf-8")
                transcript_sha256 = hashlib.sha256(transcript.read_bytes()).hexdigest()
                record = {
                    "console_transcript": {
                        "path": transcript.name,
                        "size": transcript.stat().st_size,
                        "sha256": transcript_sha256,
                    },
                }
                result["transcript_sha256"] = transcript_sha256
                rejection_paths.append(evidence_file)
            evidence_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(
                evidence_file.read_bytes()
            ).hexdigest()
            records[evidence_file] = copy.deepcopy(record)
        evidence_path = self.write_json(directory, evidence)

        def fixture_digest(path: pathlib.Path) -> str:
            if path == executable:
                return self.evidence["executable"]["sha256"]
            return hashlib.sha256(path.read_bytes()).hexdigest()

        return {
            "artifact_root": artifact_root,
            "executable": executable,
            "evidence": evidence,
            "evidence_path": evidence_path,
            "records": records,
            "locked_paths": locked_paths,
            "rejection_paths": rejection_paths,
            "fixture_digest": fixture_digest,
        }

    def documented_command_arguments(self, marker: str) -> list[str]:
        document = (
            self.root / "docs/project/M14_OPPONENT_ACQUISITION.md"
        ).read_text(encoding="utf-8")
        match = re.search(
            rf"{re.escape(marker)}.*?```text\n(?P<command>.*?)\n```",
            document,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        command = match.group("command").replace("\\\n", " ")  # type: ignore[union-attr]
        tokens = shlex.split(command)
        self.assertEqual(tokens[0:2], ["PYTHONPATH=scripts/v2", "python3"])
        self.assertEqual(
            tokens[2],
            "scripts/v2/validate_opponent_package_evidence.py",
        )
        return tokens[3:]

    def test_repository_evidence_index_passes(self) -> None:
        summary = validate_opponent_package_evidence.validate(self.root)
        self.assertEqual(summary.opponents, 10)
        self.assertEqual(summary.locked, 8)
        self.assertEqual(summary.rejected, 2)
        self.assertEqual(summary.packages, 18)
        self.assertEqual(summary.archive_bytes, 4_341_760)
        self.assertEqual(summary.license_files, 18)

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(
            validate_opponent_package_evidence.acquire_ai_package,
            "validate_lock",
            side_effect=AssertionError("unexpected live read"),
        ), mock.patch.object(
            validate_opponent_package_evidence,
            "validate_rejection",
            side_effect=AssertionError("unexpected live read"),
        ):
            summary = validate_opponent_package_evidence.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_artifacts)

    def test_required_live_inputs_are_the_exact_ten_package_sets(self) -> None:
        requirements = validate_opponent_package_evidence.required_live_inputs(self.root)
        observed = {
            (item.logical_set, item.relative_path, item.kind, item.expected_sha256)
            for item in requirements
        }
        for result in self.evidence["results"]:
            self.assertIn((
                result["artifact_dir"], result["evidence_file"], "file",
                result["evidence_sha256"],
            ), observed)
            if result["outcome"] == "REJECTED":
                self.assertIn((
                    result["artifact_dir"], "openttd-content-console.log", "file",
                    result["transcript_sha256"],
                ), observed)
        self.assertIn(
            ("v2-m14-ai-shipai-a", "content_download/ai/53484950-ShipAI-10.tar", "file", None),
            observed,
        )
        self.assertGreater(len(requirements), 20)

    def test_required_live_role_is_the_frozen_m14_executable(self) -> None:
        self.assertEqual(
            validate_opponent_package_evidence.required_live_roles(self.root),
            (
                RoleRequirement(
                    "m14-openttd-executable",
                    ".",
                    "file",
                    "m14-opponent-package-evidence",
                    self.evidence["executable"]["sha256"],
                ),
            ),
        )

    def test_relocated_live_package_closure_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = self.make_live_fixture(pathlib.Path(raw))
            context = ArtifactContext.live(fixture["artifact_root"])

            def validate_lock(
                root: pathlib.Path,
                path: pathlib.Path,
                *,
                openttd: pathlib.Path,
            ) -> dict[str, object]:
                self.assertEqual(root, self.root)
                self.assertEqual(openttd, fixture["executable"])
                return validate_opponent_package_evidence.load_json(path)

            def validate_rejection(
                root: pathlib.Path,
                path: pathlib.Path,
                result: dict[str, object],
                executable: dict[str, object],
            ) -> None:
                self.assertEqual(root, self.root)
                self.assertEqual(
                    validate_opponent_package_evidence.load_json(path),
                    fixture["records"][path],
                )
                self.assertEqual(executable, self.evidence["executable"])

            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture["fixture_digest"],
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": fixture["executable"]},
                )
                with mock.patch.object(
                    validate_opponent_package_evidence.acquire_ai_package,
                    "validate_lock",
                    side_effect=validate_lock,
                ) as lock_reader, mock.patch.object(
                    validate_opponent_package_evidence,
                    "validate_rejection",
                    side_effect=validate_rejection,
                ) as rejection_reader:
                    summary = validate_opponent_package_evidence.validate(
                        self.root,
                        fixture["evidence_path"],
                        self.schema_path,
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )
            self.assertTrue(summary.live_artifacts)
            self.assertEqual(
                [call.args[1] for call in lock_reader.call_args_list],
                fixture["locked_paths"],
            )
            self.assertEqual(
                [call.args[1] for call in rejection_reader.call_args_list],
                fixture["rejection_paths"],
            )
            for path, expected in fixture["records"].items():
                self.assertEqual(
                    validate_opponent_package_evidence.load_json(path),
                    expected,
                )

    def test_matching_digest_empty_retained_package_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = self.make_live_fixture(pathlib.Path(raw))
            evidence = fixture["evidence"]
            result = next(item for item in evidence["results"] if item["outcome"] == "LOCKED")
            path = fixture["artifact_root"] / result["artifact_dir"] / result["evidence_file"]
            path.write_text("{}\n", encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            fixture["evidence_path"].write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            context = ArtifactContext.live(fixture["artifact_root"])
            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture["fixture_digest"],
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": fixture["executable"]},
                )
                with self.assertRaisesRegex(
                    validate_opponent_package_evidence.OpponentEvidenceError,
                    "AAAHogEx retained package evidence structure invalid: packages must be a nonempty list",
                ):
                    validate_opponent_package_evidence.validate(
                        self.root,
                        fixture["evidence_path"],
                        self.schema_path,
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )

    def test_matching_digest_malformed_package_list_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = self.make_live_fixture(pathlib.Path(raw))
            evidence = fixture["evidence"]
            result = next(item for item in evidence["results"] if item["outcome"] == "LOCKED")
            path = fixture["artifact_root"] / result["artifact_dir"] / result["evidence_file"]
            path.write_text('{"packages": {}}\n', encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            fixture["evidence_path"].write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            context = ArtifactContext.live(fixture["artifact_root"])
            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture["fixture_digest"],
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": fixture["executable"]},
                )
                with self.assertRaisesRegex(
                    validate_opponent_package_evidence.OpponentEvidenceError,
                    "AAAHogEx retained package evidence structure invalid: packages must be a nonempty list",
                ):
                    validate_opponent_package_evidence.validate(
                        self.root,
                        fixture["evidence_path"],
                        self.schema_path,
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )

    def test_documented_live_package_command_uses_supported_interface(self) -> None:
        arguments = self.documented_command_arguments("The live re-audit command is:")
        expected_root = pathlib.Path("/absolute/path/to/openttd-rl-artifacts")
        loaded_roots: list[pathlib.Path] = []
        validated_contexts: list[ArtifactContext] = []
        expected_live_inputs = LiveInputManifest.offline()

        def load_manifest(artifact_root: pathlib.Path) -> LiveInputManifest:
            loaded_roots.append(artifact_root)
            return expected_live_inputs

        def validate_documented_command(
            root: pathlib.Path,
            evidence_path: pathlib.Path | None = None,
            schema_path: pathlib.Path | None = None,
            *,
            artifact_context: ArtifactContext | None = None,
            live_inputs: LiveInputManifest | None = None,
        ) -> validate_opponent_package_evidence.OpponentEvidenceSummary:
            self.assertIs(live_inputs, expected_live_inputs)
            self.assertIsNotNone(artifact_context)
            assert artifact_context is not None
            validated_contexts.append(artifact_context)
            return validate_opponent_package_evidence.OpponentEvidenceSummary(
                opponents=10,
                locked=8,
                rejected=2,
                packages=18,
                archive_bytes=4_341_760,
                license_files=18,
                live_artifacts=artifact_context.is_live,
            )

        stderr = io.StringIO()
        with mock.patch.object(
            validate_opponent_package_evidence.LiveInputManifest,
            "load",
            side_effect=load_manifest,
        ), mock.patch.object(
            validate_opponent_package_evidence,
            "validate",
            side_effect=validate_documented_command,
        ), mock.patch("sys.stdout", new=io.StringIO()), mock.patch(
            "sys.stderr",
            new=stderr,
        ):
            exit_code = validate_opponent_package_evidence.main(arguments)
        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertEqual(loaded_roots, [expected_root])
        self.assertEqual(
            validated_contexts,
            [ArtifactContext.live(expected_root)],
        )

        relative_arguments = list(arguments)
        relative_arguments[relative_arguments.index("--artifact-root") + 1] = "relative/artifacts"
        stderr = io.StringIO()
        with mock.patch("sys.stderr", new=stderr):
            exit_code = validate_opponent_package_evidence.main(relative_arguments)
        self.assertEqual(exit_code, 1)
        self.assertIn("artifact root must be an absolute path", stderr.getvalue())

        document = (
            self.root / "docs/project/M14_OPPONENT_ACQUISITION.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f"{expected_root}/v2-live-inputs.json", document)
        self.assertIn("m14-openttd-executable", document)
        self.assertIn("no raw executable-path bypass", " ".join(document.split()))
        with self.assertRaises(SystemExit) as raised, mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            validate_opponent_package_evidence.parse_args([
                "--artifact-base", "/tmp/artifacts", "--openttd", "/tmp/openttd",
            ])
        self.assertEqual(raised.exception.code, 2)

    def test_derived_artifacts_are_preflighted_before_helper_readers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            artifact_root = directory / "artifacts"
            artifact_root.mkdir()
            executable = artifact_root / "m14-openttd"
            with executable.open("wb") as stream:
                stream.truncate(self.evidence["executable"]["size"])

            evidence = copy.deepcopy(self.evidence)
            for result in evidence["results"]:
                artifact_set = artifact_root / result["artifact_dir"]
                artifact_set.mkdir()
                if result["outcome"] == "LOCKED":
                    retained = {
                        "packages": [{
                            "archive_path": "content_download/missing.tar",
                            "archive_sha256": "0" * 64,
                        }],
                    }
                else:
                    retained = {
                        "console_transcript": {
                            "path": "openttd-content-console.log",
                            "size": 1,
                            "sha256": "0" * 64,
                        },
                    }
                evidence_file = artifact_set / result["evidence_file"]
                evidence_file.write_text(
                    json.dumps(retained) + "\n",
                    encoding="utf-8",
                )
                result["evidence_sha256"] = hashlib.sha256(
                    evidence_file.read_bytes()
                ).hexdigest()
            evidence_path = self.write_json(directory, evidence)
            context = ArtifactContext.live(artifact_root)

            def fixture_digest(path: pathlib.Path) -> str:
                if path == executable:
                    return self.evidence["executable"]["sha256"]
                return hashlib.sha256(path.read_bytes()).hexdigest()

            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture_digest,
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": executable},
                )
                with mock.patch.object(
                    validate_opponent_package_evidence.acquire_ai_package,
                    "validate_lock",
                    side_effect=AssertionError("helper ran before derived preflight"),
                ) as lock_reader, mock.patch.object(
                    validate_opponent_package_evidence,
                    "validate_rejection",
                    side_effect=AssertionError("helper ran before derived preflight"),
                ) as rejection_reader:
                    with self.assertRaisesRegex(
                        validate_opponent_package_evidence.OpponentEvidenceError,
                        "content_download/missing.tar",
                    ):
                        validate_opponent_package_evidence.validate(
                            self.root,
                            evidence_path,
                            self.schema_path,
                            artifact_context=context,
                            live_inputs=live_inputs,
                        )
                lock_reader.assert_not_called()
                rejection_reader.assert_not_called()

    def test_live_input_manifest_must_share_the_exact_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            context_root = directory / "context"
            manifest_root = directory / "manifest"
            context_root.mkdir()
            manifest_root.mkdir()
            executable = manifest_root / "m14-openttd"
            executable.write_bytes(b"fixture")
            manifest_context = ArtifactContext.live(manifest_root)
            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                return_value=self.evidence["executable"]["sha256"],
            ):
                live_inputs = LiveInputManifest.bind(
                    manifest_context,
                    {"m14-openttd-executable": executable},
                )
            with self.assertRaisesRegex(
                validate_opponent_package_evidence.OpponentEvidenceError,
                "share one exact artifact root",
            ):
                validate_opponent_package_evidence.validate(
                    self.root,
                    artifact_context=ArtifactContext.live(context_root),
                    live_inputs=live_inputs,
                )

    def test_schema_hash_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "schema SHA-256"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_missing_opponent_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"].pop()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_opponent_package_evidence.OpponentEvidenceError):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_unsorted_results_fail(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0], evidence["results"][1] = evidence["results"][1], evidence["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "not bytewise sorted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_content_identity_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0]["content_unique_id"] = "00000000"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "content ID drifted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_version_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0]["version"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "version drifted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_duplicate_artifact_directory_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][1]["artifact_dir"] = evidence["results"][0]["artifact_dir"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "duplicate artifact directories"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_live_validation_requires_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = ArtifactContext.live(pathlib.Path(raw))
            with self.assertRaisesRegex(
                validate_opponent_package_evidence.OpponentEvidenceError,
                "live-input manifest",
            ):
                validate_opponent_package_evidence.validate(
                    self.root,
                    artifact_context=context,
                    live_inputs=LiveInputManifest.offline(),
                )

    def test_retained_live_evidence_when_configured(self) -> None:
        configured = resolve_artifact_root(None)
        if not configured:
            self.skipTest("live artifact validation is outside offline mode")
        context = ArtifactContext.live(configured)
        summary = validate_opponent_package_evidence.validate(
            self.root,
            artifact_context=context,
            live_inputs=LiveInputManifest.load(configured),
        )
        self.assertTrue(summary.live_artifacts)


if __name__ == "__main__":
    unittest.main()
