#!/usr/bin/env python3
"""Mutation tests for the M14 opponent runtime qualification matrix."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import shutil
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
import validate_opponent_runtime_evidence


class OpponentRuntimeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence_path = cls.root / "config/v2/opponent-runtime-evidence.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-opponent-runtime-evidence.schema.json"
        cls.evidence = validate_opponent_runtime_evidence.load_json(cls.evidence_path)

    @staticmethod
    def write_json(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "opponent-runtime-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> validate_opponent_runtime_evidence.RuntimeEvidenceSummary:
        return validate_opponent_runtime_evidence.validate(
            self.root,
            self.write_json(directory, value),
            self.schema_path,
        )

    @staticmethod
    def result(evidence: dict[str, object], name: str) -> dict[str, object]:
        return next(item for item in evidence["results"] if item["name"] == name)  # type: ignore[index]

    def make_live_fixture(self, directory: pathlib.Path) -> dict[str, object]:
        project = directory / "project"
        artifact_root = directory / "relocated-artifacts"
        for relative in ("config/v1", "config/v2", "docs/project/schema"):
            (project / relative).mkdir(parents=True, exist_ok=True)
        for relative in (
            "config/v1/openttd-source-profile.json",
            "config/v2/research-baseline.json",
            "docs/project/schema/v2-opponent-package-evidence.schema.json",
            "docs/project/schema/v2-opponent-runtime-evidence.schema.json",
        ):
            shutil.copyfile(self.root / relative, project / relative)
        artifact_root.mkdir()
        executable = artifact_root / "m14-openttd"
        with executable.open("wb") as stream:
            stream.truncate(self.evidence["executable"]["size"])

        package = validate_opponent_runtime_evidence.validate_opponent_package_evidence.load_json(
            self.root / "config/v2/opponent-package-evidence.json"
        )
        package_records: dict[pathlib.Path, dict[str, object]] = {}
        package_lock_paths: list[pathlib.Path] = []
        package_rejection_paths: list[pathlib.Path] = []
        for result in package["results"]:
            artifact_set = artifact_root / result["artifact_dir"]
            artifact_set.mkdir(exist_ok=True)
            evidence_file = artifact_set / result["evidence_file"]
            if result["outcome"] == "LOCKED":
                archive_relative = f"content_download/{result['content_unique_id']}.tar"
                archive = artifact_set / archive_relative
                archive.parent.mkdir()
                archive.write_bytes(f"package:{result['name']}\n".encode("utf-8"))
                package_row = {
                    "local_unique_id": result["content_unique_id"],
                    "archive_path": archive_relative,
                    "archive_size": archive.stat().st_size,
                    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    "licenses": ["COPYING"],
                }
                record = {"packages": [package_row]}
                result["package_count"] = 1
                result["archive_bytes"] = package_row["archive_size"]
                result["license_files"] = 1
                result["closure_sha256"] = (
                    validate_opponent_runtime_evidence.validate_opponent_package_evidence.closure_sha256(
                        [package_row]
                    )
                )
                package_lock_paths.append(evidence_file)
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
                package_rejection_paths.append(evidence_file)
            evidence_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(
                evidence_file.read_bytes()
            ).hexdigest()
            package_records[evidence_file] = copy.deepcopy(record)
        package_path = project / "config/v2/opponent-package-evidence.json"
        package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

        runtime = copy.deepcopy(self.evidence)
        runtime["package_evidence_sha256"] = hashlib.sha256(
            package_path.read_bytes()
        ).hexdigest()
        package_by_name = {item["name"]: item for item in package["results"]}
        runtime_records: dict[pathlib.Path, dict[str, object]] = {}
        runtime_paths: list[pathlib.Path] = []
        for result in runtime["results"]:
            if result["phase"] == "PACKAGE":
                result["evidence_sha256"] = package_by_name[result["name"]][
                    "evidence_sha256"
                ]
                continue
            artifact_set = artifact_root / result["artifact_dir"]
            artifact_set.mkdir()
            copied_archive = artifact_set / "content_download/runtime-package.tar"
            copied_archive.parent.mkdir()
            copied_archive.write_bytes(f"runtime-package:{result['name']}\n".encode("utf-8"))
            copied_lock_record = {
                "packages": [{
                    "archive_path": "content_download/runtime-package.tar",
                    "archive_sha256": hashlib.sha256(
                        copied_archive.read_bytes()
                    ).hexdigest(),
                }],
            }
            copied_lock = artifact_set / "ai-package-lock.json"
            copied_lock.write_text(
                json.dumps(copied_lock_record) + "\n",
                encoding="utf-8",
            )
            transcript = artifact_set / "openttd-runtime-console.log"
            if result["reason_code"] == "declared-identity-not-listed":
                transcript.write_text("Compile error\n", encoding="utf-8")
            elif result["reason_code"] == "script-crash-missing-library":
                transcript.write_text("couldn't find library\n", encoding="utf-8")
            else:
                transcript.write_text(f"runtime:{result['name']}\n", encoding="utf-8")
            save = None
            if result["save_sha256"] is not None:
                save_path = artifact_set / "runtime.sav"
                save_path.write_bytes(f"save:{result['name']}\n".encode("utf-8"))
                result["save_sha256"] = hashlib.sha256(save_path.read_bytes()).hexdigest()
                save = {
                    "path": save_path.name,
                    "size": save_path.stat().st_size,
                    "sha256": result["save_sha256"],
                }
            start_date = None
            post_load_date = None
            if result["elapsed_days"] is not None:
                start = dt.date(2000, 1, 1)
                start_date = start.isoformat()
                post_load_date = (
                    start + dt.timedelta(days=result["elapsed_days"])
                ).isoformat()
            vehicles = result["vehicles"]
            company = None if vehicles is None else {
                "trains": vehicles["train"],
                "road_vehicles": vehicles["road"],
                "aircraft": vehicles["air"],
                "ships": vehicles["ship"],
            }
            checks = {
                "declared_identity_listed": result["reason_code"] != "declared-identity-not-listed",
                "no_script_crash": result["reason_code"] != "script-crash-missing-library",
            }
            record = {
                "package_lock": {
                    "sha256": hashlib.sha256(copied_lock.read_bytes()).hexdigest(),
                    "catalog_name": result["name"],
                    "catalog_unique_id": result["content_unique_id"],
                },
                "resources": {
                    "console_transcript_sha256": hashlib.sha256(
                        transcript.read_bytes()
                    ).hexdigest(),
                    "max_rss_kib": result["max_rss_kib"],
                },
                "observations": {
                    "start_date": start_date,
                    "post_load_date": post_load_date,
                    "company_after_load": company,
                    "save": save,
                },
                "checks": checks,
                "outcome": result["outcome"],
            }
            evidence_file = artifact_set / result["evidence_file"]
            evidence_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(
                evidence_file.read_bytes()
            ).hexdigest()
            runtime_records[evidence_file] = copy.deepcopy(record)
            runtime_paths.append(evidence_file)
        runtime_path = project / "config/v2/opponent-runtime-evidence.json"
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")

        def fixture_digest(path: pathlib.Path) -> str:
            if path == executable:
                return self.evidence["executable"]["sha256"]
            return hashlib.sha256(path.read_bytes()).hexdigest()

        return {
            "project": project,
            "artifact_root": artifact_root,
            "executable": executable,
            "package": package,
            "package_path": package_path,
            "package_records": package_records,
            "package_lock_paths": package_lock_paths,
            "package_rejection_paths": package_rejection_paths,
            "runtime": runtime,
            "runtime_path": runtime_path,
            "runtime_records": runtime_records,
            "runtime_paths": runtime_paths,
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
            "scripts/v2/validate_opponent_runtime_evidence.py",
        )
        return tokens[3:]

    def test_repository_runtime_matrix_passes(self) -> None:
        summary = validate_opponent_runtime_evidence.validate(self.root)
        self.assertEqual(summary.opponents, 10)
        self.assertEqual(summary.package_rejected, 2)
        self.assertEqual(summary.runtime_rejected, 2)
        self.assertEqual(summary.tournament, 2)
        self.assertEqual(summary.control, 1)
        self.assertEqual(summary.scenario_required, 3)

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(
            validate_opponent_runtime_evidence.qualify_ai_runtime,
            "validate_manifest",
            side_effect=AssertionError("unexpected live read"),
        ), mock.patch.object(
            validate_opponent_runtime_evidence.validate_opponent_package_evidence,
            "validate",
            side_effect=AssertionError("unexpected live read"),
        ):
            summary = validate_opponent_runtime_evidence.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_artifacts)

    def test_required_live_inputs_are_the_exact_package_and_runtime_sets(self) -> None:
        requirements = validate_opponent_runtime_evidence.required_live_inputs(self.root)
        package = validate_opponent_runtime_evidence.validate_opponent_package_evidence.load_json(
            self.root / "config/v2/opponent-package-evidence.json"
        )
        expected = [
            (
                result["artifact_dir"],
                result["evidence_file"],
                result["evidence_sha256"],
            )
            for result in package["results"]
        ] + [
            (
                result["artifact_dir"],
                result["evidence_file"],
                result["evidence_sha256"],
            )
            for result in self.evidence["results"]
            if result["phase"] != "PACKAGE"
        ]
        self.assertEqual(len(requirements), 18)
        self.assertEqual(len({item.logical_set for item in requirements}), 18)
        self.assertEqual(
            [
                (
                    requirement.logical_set,
                    requirement.relative_path,
                    requirement.expected_sha256,
                )
                for requirement in requirements
            ],
            expected,
        )
        custom = copy.deepcopy(self.evidence)
        custom_requirements = (
            *validate_opponent_runtime_evidence.validate_opponent_package_evidence.required_live_inputs(
                self.root
            ),
            *validate_opponent_runtime_evidence._requirements(custom),
        )
        self.assertEqual(len(custom_requirements), 18)
        self.assertEqual(len({item.logical_set for item in custom_requirements}), 18)

    def test_required_live_role_is_the_frozen_m14_executable(self) -> None:
        self.assertEqual(
            validate_opponent_runtime_evidence.required_live_roles(self.root),
            (
                RoleRequirement(
                    "m14-openttd-executable",
                    ".",
                    "file",
                    "m14-opponent-runtime-evidence",
                    self.evidence["executable"]["sha256"],
                ),
            ),
        )

    def test_runtime_artifact_directories_are_disjoint_from_package_authority(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        package = validate_opponent_runtime_evidence.validate_opponent_package_evidence.load_json(
            self.root / "config/v2/opponent-package-evidence.json"
        )
        self.result(evidence, "AAAHogEx")["artifact_dir"] = next(
            item["artifact_dir"] for item in package["results"] if item["name"] == "AAAHogEx"
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                "runtime/package artifact directories overlap: .*v2-m14-ai-aaahogex-a",
            ):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_relocated_live_runtime_and_package_closures_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = self.make_live_fixture(pathlib.Path(raw))
            context = ArtifactContext.live(fixture["artifact_root"])

            def validate_lock(
                root: pathlib.Path,
                path: pathlib.Path,
                *,
                openttd: pathlib.Path,
            ) -> dict[str, object]:
                self.assertEqual(root, fixture["project"])
                self.assertEqual(openttd, fixture["executable"])
                return validate_opponent_runtime_evidence.load_json(path)

            def validate_rejection(
                root: pathlib.Path,
                path: pathlib.Path,
                result: dict[str, object],
                executable: dict[str, object],
            ) -> None:
                self.assertEqual(root, fixture["project"])
                self.assertEqual(
                    validate_opponent_runtime_evidence.load_json(path),
                    fixture["package_records"][path],
                )

            def validate_manifest(
                root: pathlib.Path,
                path: pathlib.Path,
                *,
                openttd: pathlib.Path,
            ) -> dict[str, object]:
                self.assertEqual(root, fixture["project"])
                self.assertEqual(openttd, fixture["executable"])
                return validate_opponent_runtime_evidence.load_json(path)

            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture["fixture_digest"],
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": fixture["executable"]},
                )
                package_module = (
                    validate_opponent_runtime_evidence.validate_opponent_package_evidence
                )
                with mock.patch.object(
                    package_module.acquire_ai_package,
                    "validate_lock",
                    side_effect=validate_lock,
                ) as lock_reader, mock.patch.object(
                    package_module,
                    "validate_rejection",
                    side_effect=validate_rejection,
                ) as rejection_reader, mock.patch.object(
                    validate_opponent_runtime_evidence.qualify_ai_runtime,
                    "validate_manifest",
                    side_effect=validate_manifest,
                ) as manifest_reader:
                    summary = validate_opponent_runtime_evidence.validate(
                        fixture["project"],
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )
            self.assertTrue(summary.live_artifacts)
            self.assertEqual(
                [call.args[1] for call in lock_reader.call_args_list],
                fixture["package_lock_paths"],
            )
            self.assertEqual(
                [call.args[1] for call in rejection_reader.call_args_list],
                fixture["package_rejection_paths"],
            )
            self.assertEqual(
                [call.args[1] for call in manifest_reader.call_args_list],
                fixture["runtime_paths"],
            )
            for path, expected in {
                **fixture["package_records"],
                **fixture["runtime_records"],
            }.items():
                self.assertEqual(validate_opponent_runtime_evidence.load_json(path), expected)

    def test_matching_digest_empty_retained_runtime_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = self.make_live_fixture(pathlib.Path(raw))
            runtime = fixture["runtime"]
            result = next(item for item in runtime["results"] if item["phase"] == "RUNTIME")
            path = fixture["artifact_root"] / result["artifact_dir"] / result["evidence_file"]
            path.write_text("{}\n", encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            fixture["runtime_path"].write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
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
                    validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                    "AAAHogEx retained runtime evidence structure invalid: package_lock must be an object",
                ):
                    validate_opponent_runtime_evidence.validate(
                        fixture["project"],
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )

    def test_matching_digest_malformed_runtime_object_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = self.make_live_fixture(pathlib.Path(raw))
            runtime = fixture["runtime"]
            result = next(item for item in runtime["results"] if item["phase"] == "RUNTIME")
            path = fixture["artifact_root"] / result["artifact_dir"] / result["evidence_file"]
            malformed = copy.deepcopy(fixture["runtime_records"][path])
            malformed["package_lock"] = []
            path.write_text(json.dumps(malformed) + "\n", encoding="utf-8")
            result["evidence_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            fixture["runtime_path"].write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
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
                    validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                    "AAAHogEx retained runtime evidence structure invalid: package_lock must be an object",
                ):
                    validate_opponent_runtime_evidence.validate(
                        fixture["project"],
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )

    def test_documented_live_runtime_command_uses_supported_interface(self) -> None:
        arguments = self.documented_command_arguments("The full live matrix re-audit is:")
        parsed = validate_opponent_runtime_evidence.parse_args(arguments)
        self.assertEqual(parsed.artifact_root, pathlib.Path("<common-root>"))
        with self.assertRaises(SystemExit) as raised, mock.patch(
            "sys.stderr",
            new=io.StringIO(),
        ):
            validate_opponent_runtime_evidence.parse_args([
                "--artifact-base", "/tmp/artifacts", "--openttd", "/tmp/openttd",
            ])
        self.assertEqual(raised.exception.code, 2)

    def test_runtime_derived_inputs_preflight_before_nested_helper_readers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            project = directory / "project"
            artifact_root = directory / "artifacts"
            for relative in (
                "config/v1",
                "config/v2",
                "docs/project/schema",
            ):
                (project / relative).mkdir(parents=True, exist_ok=True)
            for relative in (
                "config/v1/openttd-source-profile.json",
                "config/v2/research-baseline.json",
                "docs/project/schema/v2-opponent-package-evidence.schema.json",
                "docs/project/schema/v2-opponent-runtime-evidence.schema.json",
            ):
                shutil.copyfile(self.root / relative, project / relative)
            artifact_root.mkdir()
            executable = artifact_root / "m14-openttd"
            with executable.open("wb") as stream:
                stream.truncate(self.evidence["executable"]["size"])

            package = validate_opponent_runtime_evidence.validate_opponent_package_evidence.load_json(
                self.root / "config/v2/opponent-package-evidence.json"
            )
            for result in package["results"]:
                artifact_set = artifact_root / result["artifact_dir"]
                artifact_set.mkdir(exist_ok=True)
                retained = (
                    {
                        "packages": [{
                            "archive_path": "package-helper-must-not-run.tar",
                            "archive_sha256": "0" * 64,
                        }],
                    }
                    if result["outcome"] == "LOCKED"
                    else {
                        "console_transcript": {
                            "path": "package-helper-must-not-run.log",
                            "size": 1,
                            "sha256": "0" * 64,
                        },
                    }
                )
                evidence_file = artifact_set / result["evidence_file"]
                evidence_file.write_text(json.dumps(retained) + "\n", encoding="utf-8")
                result["evidence_sha256"] = hashlib.sha256(
                    evidence_file.read_bytes()
                ).hexdigest()
            package_path = project / "config/v2/opponent-package-evidence.json"
            package_path.write_text(
                json.dumps(package, indent=2) + "\n",
                encoding="utf-8",
            )

            runtime = copy.deepcopy(self.evidence)
            runtime["package_evidence_sha256"] = hashlib.sha256(
                package_path.read_bytes()
            ).hexdigest()
            package_by_name = {item["name"]: item for item in package["results"]}
            for result in runtime["results"]:
                if result["phase"] == "PACKAGE":
                    result["evidence_sha256"] = package_by_name[result["name"]][
                        "evidence_sha256"
                    ]
                    continue
                artifact_set = artifact_root / result["artifact_dir"]
                artifact_set.mkdir()
                retained = {
                    "package_lock": {"sha256": "0" * 64},
                    "resources": {"console_transcript_sha256": "0" * 64},
                    "observations": {"save": None},
                }
                evidence_file = artifact_set / result["evidence_file"]
                evidence_file.write_text(json.dumps(retained) + "\n", encoding="utf-8")
                result["evidence_sha256"] = hashlib.sha256(
                    evidence_file.read_bytes()
                ).hexdigest()
            runtime_path = project / "config/v2/opponent-runtime-evidence.json"
            runtime_path.write_text(
                json.dumps(runtime, indent=2) + "\n",
                encoding="utf-8",
            )
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
                with self.assertRaisesRegex(
                    validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                    "ai-package-lock.json",
                ):
                    validate_opponent_runtime_evidence.validate(
                        project,
                        runtime_path,
                        project / "docs/project/schema/v2-opponent-runtime-evidence.schema.json",
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )

    def test_schema_hash_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "schema SHA-256"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_package_index_digest_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["package_evidence_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "runtime/package evidence"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_missing_opponent_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"].pop()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_unsorted_results_fail(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0], evidence["results"][1] = evidence["results"][1], evidence["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "not bytewise sorted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_content_identity_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0]["content_unique_id"] = "00000000"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "content ID drifted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_active_admission_requires_vehicle_activity(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        self.result(evidence, "KrakenAI2")["vehicles"] = {"train": 0, "road": 0, "air": 0, "ship": 0}
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "lacks 30-day vehicle activity"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_inactive_ai_cannot_enter_tournament(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        self.result(evidence, "ShipAI")["admission"] = "TOURNAMENT"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "inactive admission policy"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_package_rejection_cannot_replace_locked_runtime(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        kraken = self.result(evidence, "KrakenAI2")
        kraken.clear()
        kraken.update(
            {
                "name": "KrakenAI2",
                "content_unique_id": "4b524132",
                "phase": "PACKAGE",
                "outcome": "PACKAGE_REJECTED",
                "admission": "EXCLUDED",
                "artifact_dir": "invented-package-rejection",
                "evidence_file": "ai-package-rejection.json",
                "evidence_sha256": "0" * 64,
                "reason_code": "catalog-listed-unselectable",
            }
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "rejects a locked package"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_duplicate_artifact_directory_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][1]["artifact_dir"] = evidence["results"][0]["artifact_dir"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "duplicate artifact directories"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_live_validation_requires_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = ArtifactContext.live(pathlib.Path(raw))
            with self.assertRaisesRegex(
                validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                "live-input manifest",
            ):
                validate_opponent_runtime_evidence.validate(
                    self.root,
                    artifact_context=context,
                    live_inputs=LiveInputManifest.offline(),
                )

    def test_retained_live_evidence_when_configured(self) -> None:
        configured = resolve_artifact_root(None)
        if not configured:
            self.skipTest("live artifact validation is outside offline mode")
        context = ArtifactContext.live(configured)
        summary = validate_opponent_runtime_evidence.validate(
            self.root,
            artifact_context=context,
            live_inputs=LiveInputManifest.load(configured),
        )
        self.assertTrue(summary.live_artifacts)


if __name__ == "__main__":
    unittest.main()
