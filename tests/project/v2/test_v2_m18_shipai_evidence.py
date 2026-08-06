#!/usr/bin/env python3
"""Offline and relocated-live tests for scenario-qualified M18 ShipAI evidence."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import pathlib
import shutil
import tarfile
import tempfile
import unittest
from types import MappingProxyType
from typing import Any
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    RoleRequirement,
    ValidationMode,
    resolve_artifact_root,
)
import validate_m18_shipai_evidence as validator


def _write_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_archive(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    members = {
        "ShipAI/LICENSE": b"GNU General Public License version 2 fixture\n",
        "ShipAI/info.nut": (
            b'class ShipAI extends AIInfo {\n'
            b' function GetName() { return "ShipAI"; }\n'
            b' function GetVersion() { return 10; }\n'
            b' function GetAPIVersion() { return "1.11"; }\n'
            b'}\nRegisterAI(ShipAI());\n'
        ),
        "ShipAI/main.nut": b"class ShipAIController extends AIController {}\n",
    }
    with tarfile.open(path, "w") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.mode = 0o644
            info.mtime = 0
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def make_live_shipai_fixture(
    repository_root: pathlib.Path,
    directory: pathlib.Path,
    config: dict[str, Any],
    package_index: dict[str, Any],
    runtime_index: dict[str, Any],
    ship_evidence: dict[str, Any],
) -> dict[str, Any]:
    project_root = directory / "project"
    for relative in (
        validator.acquire_ai_package.SCHEMA_RELATIVE,
        validator.qualify_ai_runtime.SCHEMA_RELATIVE,
        pathlib.Path("config/v1/openttd-source-profile.json"),
        pathlib.Path("config/v2/research-baseline.json"),
    ):
        target = project_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository_root / relative, target)

    evidence = copy.deepcopy(config)
    package_index_value = copy.deepcopy(package_index)
    runtime_index_value = copy.deepcopy(runtime_index)
    ship_evidence_value = copy.deepcopy(ship_evidence)
    package_record = next(item for item in package_index_value["results"] if item["name"] == "ShipAI")
    artifact_root = directory / "relocated-artifacts"
    artifact_root.mkdir()
    executable = artifact_root / "m14-openttd"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    executable_identity = {"sha256": _sha256(executable), "size": executable.stat().st_size}
    package_index_value["executable"] = executable_identity

    package_set = artifact_root / package_record["artifact_dir"]
    package_set.mkdir()
    package_archive = package_set / "content_download/53484950-ShipAI-v10.tar"
    _write_archive(package_archive)
    catalog = validator.acquire_ai_package.CatalogRecord(
        content_id=1,
        content_type="AI",
        state="selected",
        name="ShipAI",
        server_unique_id="50494853",
        catalog_md5="0" * 32,
    )
    package = validator.acquire_ai_package.audit_archive(package_set, package_archive, catalog)
    source = json.loads((project_root / "config/v1/openttd-source-profile.json").read_text(encoding="utf-8"))["upstream"]
    package_lock = {
        "$schema": "../../docs/project/schema/v2-ai-package-lock.schema.json",
        "schema_version": "openttd-rl-v2-ai-package-lock-1",
        "schema_sha256": _sha256(project_root / validator.acquire_ai_package.SCHEMA_RELATIVE),
        "engine_source": {key: source[key] for key in ("release", "commit", "tree")},
        "executable": {**executable_identity, "reported_version": "15.3-test"},
        "request": {
            "catalog_url": "https://bananas.openttd.org/package/ai/53484950",
            "content_unique_id": "53484950",
            "name": "ShipAI",
            "version": 10,
        },
        "catalog_primary": catalog.manifest_dict(),
        "packages": [package],
    }
    package_lock_path = package_set / package_record["evidence_file"]
    _write_json(package_lock_path, package_lock)
    validator.acquire_ai_package.validate_lock(project_root, package_lock_path, openttd=executable)
    package_record.update({
        "archive_bytes": package["archive_size"],
        "closure_sha256": validator.qualify_ai_runtime.closure_sha256([package]),
        "evidence_sha256": _sha256(package_lock_path),
        "license_files": len(package["licenses"]),
        "package_count": 1,
    })
    evidence["package"]["archive_sha256"] = package["archive_sha256"]

    scenario_path = artifact_root / "v2-m18-shipai-scenario-c/report.json.sav"
    scenario_path.parent.mkdir()
    scenario_path.write_bytes(b"byte-real relocated ShipAI scenario fixture\n")
    evidence["scenario"].update({"bytes": scenario_path.stat().st_size, "sha256": _sha256(scenario_path)})

    runtime_set = artifact_root / "v2-m18-shipai-runtime-b"
    runtime_set.mkdir()
    runtime_archive = runtime_set / "content_download/53484950-ShipAI-v10.tar"
    runtime_archive.parent.mkdir()
    shutil.copyfile(package_archive, runtime_archive)
    copied_lock = copy.deepcopy(package_lock)
    copied_lock_path = runtime_set / "ai-package-lock.json"
    _write_json(copied_lock_path, copied_lock)
    transcript = runtime_set / "openttd-runtime-console.log"
    transcript.write_text("ShipAI runtime transcript fixture\n", encoding="utf-8")
    save = runtime_set / "v2-qualification.sav"
    save.write_bytes(b"ShipAI save fixture\n")
    company = {
        "company_id": 1,
        "loan": 0,
        "money": 100000,
        "trains": 0,
        "road_vehicles": 0,
        "aircraft": 0,
        "ships": 2,
        "value": 100000,
    }
    manifest = {
        "$schema": "../../docs/project/schema/v2-ai-runtime-qualification.schema.json",
        "schema_version": "openttd-rl-v2-ai-runtime-qualification-1",
        "schema_sha256": _sha256(project_root / validator.qualify_ai_runtime.SCHEMA_RELATIVE),
        "engine_source": {key: source[key] for key in ("release", "commit", "tree")},
        "executable": {**executable_identity, "reported_version": "15.3-test"},
        "package_lock": {
            "api_version": package["declared_info"].get("api_version"),
            "catalog_name": "ShipAI",
            "catalog_unique_id": "53484950",
            "catalog_version": 10,
            "closure_sha256": validator.qualify_ai_runtime.closure_sha256([package]),
            "declared_name": package["declared_info"]["name"],
            "declared_version": package["declared_info"]["version"],
            "package_count": 1,
            "sha256": _sha256(copied_lock_path),
        },
        "sandbox": {
            "kind": "test-none",
            "new_session": True,
            "private_network": False,
            "read_only_root": False,
            "resource_limits": validator.qualify_ai_runtime.LIMITS,
        },
        "resources": {
            "console_transcript_sha256": _sha256(transcript),
            "max_rss_kib": 1,
            "process_returncode": 0,
            "wall_seconds": 0.1,
        },
        "observations": {
            "list_line": "ShipAI (v10)",
            "start_date": "1950-01-01",
            "pre_save_date": "1950-02-01",
            "post_load_date": "1950-02-01",
            "company_before_load": company,
            "company_after_load": company,
            "save": {
                "path": save.name,
                "size": save.stat().st_size,
                "sha256": _sha256(save),
            },
        },
        "scenario": {"generation_seed": 1, "map_height": 128, "map_width": 128, "minimum_elapsed_days": 30, "start_year": 1950},
        "checks": {
            "company_started": True,
            "company_survived_load": True,
            "declared_identity_listed": True,
            "minimum_days_elapsed": True,
            "no_script_crash": True,
            "resource_limits_respected": True,
            "save_created": True,
        },
        "outcome": "QUALIFIED_ACTIVE",
        "error_details": [],
    }
    manifest_path = runtime_set / "ai-runtime-qualification.json"
    _write_json(manifest_path, manifest)
    validator.qualify_ai_runtime.validate_manifest(project_root, manifest_path, openttd=executable)
    evidence["qualification_manifest"].update({"bytes": manifest_path.stat().st_size, "sha256": _sha256(manifest_path)})
    ship_evidence_value["baselines"]["qualification_manifest_sha256"] = evidence["qualification_manifest"]["sha256"]

    _write_json(project_root / validator.PACKAGE_INDEX, package_index_value)
    _write_json(project_root / validator.RUNTIME_INDEX, runtime_index_value)
    _write_json(project_root / validator.SHIP_EVIDENCE, ship_evidence_value)
    config_path = project_root / validator.CONFIG
    _write_json(config_path, evidence)

    return {
        "project_root": project_root,
        "config_path": config_path,
        "evidence": evidence,
        "package_index": package_index_value,
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
        "live_inputs": LiveInputManifest(
            ValidationMode.LIVE,
            artifact_root.resolve(),
            MappingProxyType({"m14-openttd-executable": executable.resolve()}),
        ),
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
        cls.runtime_index = validator.load(cls.root / validator.RUNTIME_INDEX)
        cls.ship_evidence = validator.load(cls.root / validator.SHIP_EVIDENCE)

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
        observed = tuple(
            (item.logical_set, item.relative_path, item.kind, item.expected_sha256)
            for item in requirements
        )
        for expected in (
                ("v2-m14-ai-shipai-a", "ai-package-lock.json", "file", self.package_record["evidence_sha256"]),
                ("v2-m18-shipai-scenario-c", "report.json.sav", "file", self.config["scenario"]["sha256"]),
                ("v2-m18-shipai-runtime-b", "ai-runtime-qualification.json", "file", self.config["qualification_manifest"]["sha256"]),
                ("v2-m14-ai-shipai-a", "content_download/ai/53484950-ShipAI-10.tar", "file", self.config["package"]["archive_sha256"]),
                ("v2-m18-shipai-runtime-b", "ai-package-lock.json", "file", None),
                ("v2-m18-shipai-runtime-b", "openttd-runtime-console.log", "file", None),
                ("v2-m18-shipai-runtime-b", "v2-qualification.sav", "file", None),
                ("v2-m18-shipai-runtime-b", "content_download/ai/53484950-ShipAI-10.tar", "file", self.config["package"]["archive_sha256"]),
        ):
            self.assertIn(expected, observed)
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
        retained_config = copy.deepcopy(self.config)
        retained_package_index = copy.deepcopy(self.package_index)
        with tempfile.TemporaryDirectory() as raw:
            fixture = make_live_shipai_fixture(
                self.root,
                pathlib.Path(raw),
                self.config,
                self.package_index,
                self.runtime_index,
                self.ship_evidence,
            )
            context = ArtifactContext.live(fixture["artifact_root"])
            summary = validator.validate(
                fixture["project_root"],
                fixture["config_path"],
                self.schema,
                artifact_context=context,
                live_inputs=fixture["live_inputs"],
            )
        self.assertTrue(summary["live"])
        self.assertEqual(summary["ships"], 2)
        self.assertEqual(self.config, retained_config)
        self.assertEqual(self.package_index, retained_package_index)

    def test_dynamic_package_closure_is_preflighted_before_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = make_live_shipai_fixture(
                self.root,
                pathlib.Path(raw),
                self.config,
                self.package_index,
                self.runtime_index,
                self.ship_evidence,
            )
            fixture["package_archive"].unlink()
            context = ArtifactContext.live(fixture["artifact_root"])
            with mock.patch.object(validator.acquire_ai_package, "validate_lock", side_effect=AssertionError("preflight did not run")) as package_helper, mock.patch.object(
                validator.qualify_ai_runtime, "validate_manifest", side_effect=AssertionError("preflight did not run"),
            ) as runtime_helper:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(
                        fixture["project_root"],
                        fixture["config_path"],
                        self.schema,
                        artifact_context=context,
                        live_inputs=fixture["live_inputs"],
                    )
            package_helper.assert_not_called()
            runtime_helper.assert_not_called()

    def test_malformed_matching_digest_qualification_inputs_fail_before_helpers(self) -> None:
        delete = object()
        cases = (
            ("package_lock missing", ("package_lock",), delete, "package_lock"),
            ("package_lock wrong type", ("package_lock",), [], "package_lock"),
            ("package_lock sha256 missing", ("package_lock", "sha256"), delete, "package_lock.sha256"),
            ("package_lock sha256 wrong type", ("package_lock", "sha256"), 7, "package_lock.sha256"),
            ("package_lock sha256 uppercase", ("package_lock", "sha256"), "A" * 64, "package_lock.sha256"),
            ("resources missing", ("resources",), delete, "resources"),
            ("resources wrong type", ("resources",), [], "resources"),
            ("transcript sha256 missing", ("resources", "console_transcript_sha256"), delete, "resources.console_transcript_sha256"),
            ("transcript sha256 wrong type", ("resources", "console_transcript_sha256"), 7, "resources.console_transcript_sha256"),
            ("transcript sha256 uppercase", ("resources", "console_transcript_sha256"), "A" * 64, "resources.console_transcript_sha256"),
            ("observations missing", ("observations",), delete, "observations"),
            ("observations wrong type", ("observations",), [], "observations"),
            ("save missing", ("observations", "save"), delete, "observations.save"),
            ("save wrong type", ("observations", "save"), [], "observations.save"),
            ("save path missing", ("observations", "save", "path"), delete, "observations.save.path"),
            ("save path wrong type", ("observations", "save", "path"), 7, "observations.save.path"),
            ("save path empty", ("observations", "save", "path"), "", "observations.save.path"),
            ("save path absolute", ("observations", "save", "path"), "/tmp/save.sav", "observations.save.path"),
            ("save path parent", ("observations", "save", "path"), "../save.sav", "observations.save.path"),
            ("save path normalized parent", ("observations", "save", "path"), "nested/../save.sav", "observations.save.path"),
            ("save path repeated separator", ("observations", "save", "path"), "nested//save.sav", "observations.save.path"),
            ("save path dot component", ("observations", "save", "path"), "nested/./save.sav", "observations.save.path"),
            ("save path backslash", ("observations", "save", "path"), "nested\\save.sav", "observations.save.path"),
            ("save path nul", ("observations", "save", "path"), "nested/\0save.sav", "observations.save.path"),
            ("save sha256 missing", ("observations", "save", "sha256"), delete, "observations.save.sha256"),
            ("save sha256 wrong type", ("observations", "save", "sha256"), 7, "observations.save.sha256"),
            ("save sha256 uppercase", ("observations", "save", "sha256"), "A" * 64, "observations.save.sha256"),
        )
        with tempfile.TemporaryDirectory() as raw:
            fixture = make_live_shipai_fixture(
                self.root,
                pathlib.Path(raw),
                self.config,
                self.package_index,
                self.runtime_index,
                self.ship_evidence,
            )
            original_manifest = copy.deepcopy(fixture["manifest"])
            original_evidence = copy.deepcopy(fixture["evidence"])
            original_ship_evidence = validator.load(fixture["project_root"] / validator.SHIP_EVIDENCE)
            context = ArtifactContext.live(fixture["artifact_root"])
            for label, keys, replacement, pattern in cases:
                with self.subTest(label=label):
                    manifest = copy.deepcopy(original_manifest)
                    target = manifest
                    for key in keys[:-1]:
                        target = target[key]
                    if replacement is delete:
                        target.pop(keys[-1], None)
                    else:
                        target[keys[-1]] = replacement
                    _write_json(fixture["manifest_path"], manifest)
                    evidence = copy.deepcopy(original_evidence)
                    evidence["qualification_manifest"].update({
                        "bytes": fixture["manifest_path"].stat().st_size,
                        "sha256": _sha256(fixture["manifest_path"]),
                    })
                    _write_json(fixture["config_path"], evidence)
                    ship_evidence = copy.deepcopy(original_ship_evidence)
                    ship_evidence["baselines"]["qualification_manifest_sha256"] = evidence["qualification_manifest"]["sha256"]
                    _write_json(fixture["project_root"] / validator.SHIP_EVIDENCE, ship_evidence)
                    with mock.patch.object(
                        validator.acquire_ai_package,
                        "validate_lock",
                        side_effect=AssertionError("qualification preflight did not run"),
                    ) as package_helper, mock.patch.object(
                        validator.qualify_ai_runtime,
                        "validate_manifest",
                        side_effect=AssertionError("qualification preflight did not run"),
                    ) as runtime_helper:
                        with self.assertRaisesRegex(validator.M18ShipAIError, pattern):
                            validator.validate(
                                fixture["project_root"],
                                fixture["config_path"],
                                self.schema,
                                artifact_context=context,
                                live_inputs=fixture["live_inputs"],
                            )
                    package_helper.assert_not_called()
                    runtime_helper.assert_not_called()

    def test_live_preflight_requires_same_root_role_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as other_raw:
            fixture = make_live_shipai_fixture(
                self.root,
                pathlib.Path(raw),
                self.config,
                self.package_index,
                self.runtime_index,
                self.ship_evidence,
            )
            context = ArtifactContext.live(fixture["artifact_root"])
            other_root = pathlib.Path(other_raw).resolve()
            other_executable = other_root / "m14-openttd"
            other_executable.write_bytes(b"x")
            live_inputs = LiveInputManifest(
                ValidationMode.LIVE,
                other_root,
                MappingProxyType({"m14-openttd-executable": other_executable}),
            )
            with self.assertRaisesRegex(validator.M18ShipAIError, "one exact artifact root"):
                validator.validate(
                    fixture["project_root"],
                    fixture["config_path"],
                    self.schema,
                    artifact_context=context,
                    live_inputs=live_inputs,
                )

    def test_scenario_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["scenario"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "shipai.json"
            _write_json(path, value)
            with mock.patch.object(validator, "CONFIG", path):
                with self.assertRaisesRegex(validator.M18ShipAIError, "scenario identity"):
                    validator.validate(self.root, schema_path=self.schema, artifact_context=ArtifactContext.offline())

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
