#!/usr/bin/env python3
"""Offline and relocated-live tests for scenario-qualified M18 ShipAI evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    RoleRequirement,
    resolve_artifact_root,
)
import artifact_context
import validate_m18_shipai_evidence as validator


def _write_padded_json(path: pathlib.Path, value: object, size: int) -> None:
    encoded = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > size:
        raise AssertionError(f"fixture JSON exceeds retained size: {len(encoded)} > {size}")
    path.write_bytes(encoded + b" " * (size - len(encoded)))


def make_live_shipai_fixture(
    directory: pathlib.Path,
    config: dict[str, Any],
    package_record: dict[str, Any],
    executable_identity: dict[str, Any],
) -> dict[str, Any]:
    artifact_root = directory / "relocated-artifacts"
    artifact_root.mkdir()
    executable = artifact_root / "m14-openttd"
    with executable.open("wb") as stream:
        stream.truncate(executable_identity["size"])

    package_set = artifact_root / package_record["artifact_dir"]
    package_set.mkdir()
    package_archive = package_set / "content_download/53484950-ShipAI-v10.tar"
    package_archive.parent.mkdir()
    with package_archive.open("wb") as stream:
        stream.truncate(package_record["archive_bytes"])
    package_lock = {
        "request": {
            "catalog_url": "https://bananas.openttd.org/package/ai/53484950",
            "content_unique_id": "53484950",
            "name": "ShipAI",
            "version": 10,
        },
        "packages": [{
            "name": "ShipAI",
            "local_unique_id": "53484950",
            "version": 10,
            "archive_path": package_archive.relative_to(package_set).as_posix(),
            "archive_size": package_record["archive_bytes"],
            "archive_sha256": config["package"]["archive_sha256"],
        }],
    }
    package_lock_path = package_set / package_record["evidence_file"]
    package_lock_path.write_text(json.dumps(package_lock) + "\n", encoding="utf-8")

    scenario_path = artifact_root / "v2-m18-shipai-scenario-c/report.json.sav"
    scenario_path.parent.mkdir()
    with scenario_path.open("wb") as stream:
        stream.truncate(config["scenario"]["bytes"])

    runtime_set = artifact_root / "v2-m18-shipai-runtime-b"
    runtime_set.mkdir()
    runtime_archive = runtime_set / "content_download/53484950-ShipAI-v10.tar"
    runtime_archive.parent.mkdir()
    runtime_archive.write_bytes(b"runtime ShipAI archive fixture\n")
    runtime_archive_sha = hashlib.sha256(runtime_archive.read_bytes()).hexdigest()
    copied_lock = {
        "packages": [{
            "archive_path": runtime_archive.relative_to(runtime_set).as_posix(),
            "archive_sha256": runtime_archive_sha,
        }],
    }
    copied_lock_path = runtime_set / "ai-package-lock.json"
    copied_lock_path.write_text(json.dumps(copied_lock) + "\n", encoding="utf-8")
    transcript = runtime_set / "openttd-runtime-console.log"
    transcript.write_text("ShipAI runtime transcript fixture\n", encoding="utf-8")
    save = runtime_set / "v2-qualification.sav"
    save.write_bytes(b"ShipAI save fixture\n")
    company = {
        "trains": 0,
        "road_vehicles": 0,
        "aircraft": 0,
        "ships": 2,
    }
    manifest = {
        "package_lock": {
            "sha256": hashlib.sha256(copied_lock_path.read_bytes()).hexdigest(),
        },
        "resources": {
            "console_transcript_sha256": hashlib.sha256(transcript.read_bytes()).hexdigest(),
        },
        "observations": {
            "company_before_load": company,
            "company_after_load": company,
            "save": {
                "path": save.name,
                "size": save.stat().st_size,
                "sha256": hashlib.sha256(save.read_bytes()).hexdigest(),
            },
        },
        "scenario": {"minimum_elapsed_days": 30},
        "checks": {"fixture": True},
        "outcome": "QUALIFIED_ACTIVE",
    }
    manifest_path = runtime_set / "ai-runtime-qualification.json"
    _write_padded_json(manifest_path, manifest, config["qualification_manifest"]["bytes"])

    expected_digests = {
        executable: executable_identity["sha256"],
        package_lock_path: package_record["evidence_sha256"],
        package_archive: config["package"]["archive_sha256"],
        scenario_path: config["scenario"]["sha256"],
        manifest_path: config["qualification_manifest"]["sha256"],
    }

    def fixture_digest(path: pathlib.Path) -> str:
        if path in expected_digests:
            return expected_digests[path]
        return hashlib.sha256(path.read_bytes()).hexdigest()

    return {
        "artifact_root": artifact_root,
        "executable": executable,
        "package_lock": package_lock,
        "package_lock_path": package_lock_path,
        "package_archive": package_archive,
        "scenario_path": scenario_path,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "runtime_archive": runtime_archive,
        "runtime_transcript": transcript,
        "fixture_digest": fixture_digest,
    }


class M18ShipAIEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.schema = cls.root / validator.SCHEMA
        package_index = validator.load(cls.root / validator.PACKAGE_INDEX)
        cls.package_index = package_index
        cls.package_record = next(item for item in package_index["results"] if item["name"] == "ShipAI")

    def validate_mutation(self, value: object) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "shipai.json"
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            validator.validate(
                self.root,
                path,
                self.schema,
                artifact_context=ArtifactContext.offline(),
            )

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_evidence_passes(self) -> None:
        self.assertEqual(validator.validate(self.root)["ships"], 2)

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_offline_validation_does_not_call_qualification_validator(self) -> None:
        with mock.patch.object(
            validator.qualify_ai_runtime,
            "validate_manifest",
            side_effect=AssertionError("unexpected live read"),
        ) as qualification:
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])
        qualification.assert_not_called()

    def test_retained_live_package_scenario_and_runtime_pass(self) -> None:
        artifact_root = self.live_base()
        summary = validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(artifact_root),
            live_inputs=LiveInputManifest.load(artifact_root),
        )
        self.assertTrue(summary["live"])

    def test_required_live_inputs_are_the_exact_direct_shipai_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind, item.expected_sha256) for item in requirements),
            (
                ("v2-m14-ai-shipai-a", "ai-package-lock.json", "file", self.package_record["evidence_sha256"]),
                ("v2-m18-shipai-scenario-c", "report.json.sav", "file", self.config["scenario"]["sha256"]),
                ("v2-m18-shipai-runtime-b", "ai-runtime-qualification.json", "file", self.config["qualification_manifest"]["sha256"]),
            ),
        )
        self.assertEqual({item.consumer for item in requirements}, {"m18-shipai-evidence"})

    def test_required_live_role_is_the_frozen_m14_executable(self) -> None:
        self.assertEqual(
            validator.required_live_roles(self.root),
            (
                RoleRequirement(
                    "m14-openttd-executable",
                    ".",
                    "file",
                    "m18-shipai-evidence",
                    self.package_index["executable"]["sha256"],
                ),
            ),
        )

    def test_relocated_live_package_scenario_and_runtime_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = make_live_shipai_fixture(
                pathlib.Path(raw),
                self.config,
                self.package_record,
                self.package_index["executable"],
            )
            context = ArtifactContext.live(fixture["artifact_root"])
            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture["fixture_digest"],
            ), mock.patch.object(
                validator,
                "sha256",
                side_effect=fixture["fixture_digest"],
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": fixture["executable"]},
                )

                def validate_lock(root: pathlib.Path, path: pathlib.Path, *, openttd: pathlib.Path) -> dict[str, Any]:
                    self.assertEqual((root, path, openttd), (self.root, fixture["package_lock_path"], fixture["executable"]))
                    return fixture["package_lock"]

                def validate_manifest(root: pathlib.Path, path: pathlib.Path, *, openttd: pathlib.Path) -> dict[str, Any]:
                    self.assertEqual((root, path, openttd), (self.root, fixture["manifest_path"], fixture["executable"]))
                    return fixture["manifest"]

                with mock.patch.object(
                    validator.acquire_ai_package,
                    "validate_lock",
                    side_effect=validate_lock,
                ) as package_helper, mock.patch.object(
                    validator.qualify_ai_runtime,
                    "validate_manifest",
                    side_effect=validate_manifest,
                ) as runtime_helper:
                    summary = validator.validate(
                        self.root,
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )
        self.assertTrue(summary["live"])
        self.assertEqual(summary["ships"], 2)
        package_helper.assert_called_once()
        runtime_helper.assert_called_once()

    def test_dynamic_package_closure_is_preflighted_before_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = make_live_shipai_fixture(pathlib.Path(raw), self.config, self.package_record, self.package_index["executable"])
            fixture["package_archive"].unlink()
            context = ArtifactContext.live(fixture["artifact_root"])
            with mock.patch.object(artifact_context, "_sha256_file", side_effect=fixture["fixture_digest"]), mock.patch.object(
                validator, "sha256", side_effect=fixture["fixture_digest"],
            ):
                live_inputs = LiveInputManifest.bind(context, {"m14-openttd-executable": fixture["executable"]})
                with mock.patch.object(validator.acquire_ai_package, "validate_lock", side_effect=AssertionError("preflight did not run")) as package_helper, mock.patch.object(
                    validator.qualify_ai_runtime, "validate_manifest", side_effect=AssertionError("preflight did not run"),
                ) as runtime_helper:
                    with self.assertRaisesRegex(ArtifactContextError, "missing"):
                        validator.validate(self.root, artifact_context=context, live_inputs=live_inputs)
            package_helper.assert_not_called()
            runtime_helper.assert_not_called()

    def test_live_preflight_requires_same_root_role_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as other_raw:
            fixture = make_live_shipai_fixture(pathlib.Path(raw), self.config, self.package_record, self.package_index["executable"])
            context = ArtifactContext.live(fixture["artifact_root"])
            other_root = pathlib.Path(other_raw).resolve()
            other_executable = other_root / "m14-openttd"
            other_executable.write_bytes(b"x")
            with mock.patch.object(artifact_context, "_sha256_file", return_value=self.package_index["executable"]["sha256"]):
                live_inputs = LiveInputManifest.bind(ArtifactContext.live(other_root), {"m14-openttd-executable": other_executable})
            with self.assertRaisesRegex(validator.M18ShipAIError, "one exact artifact root"):
                validator.validate(self.root, artifact_context=context, live_inputs=live_inputs)

    def test_scenario_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["scenario"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.M18ShipAIError, "scenario identity"):
            self.validate_mutation(value)

    def test_m14_disposition_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["m14"]["evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.M18ShipAIError, "runtime disposition"):
            self.validate_mutation(value)

    def test_package_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["package"]["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.M18ShipAIError, "package projection"):
            self.validate_mutation(value)

    def test_ship_projection_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["observations"]["ships_after_load"] += 1
        with self.assertRaisesRegex(validator.M18ShipAIError, "observation projection"):
            self.validate_mutation(value)


if __name__ == "__main__":
    unittest.main()
