#!/usr/bin/env python3
"""Unit and mutation tests for complete V1 dependency provenance."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import generate_dependency_provenance


class V1DependencyProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema_path = cls.root / "docs/project/schema/v1-dependency-provenance-manifest.schema.json"

    @staticmethod
    def package(name: str) -> dict[str, object]:
        return {
            "package": name,
            "source_package": name,
            "version": "1",
            "architecture": "amd64",
            "sha256": "1" * 64,
            "source_url": "https://example.invalid/source",
            "license_declarations": ["MIT"],
            "license_evidence_sha256": "2" * 64,
            "distribution_status": "fixture",
        }

    def manifest(self) -> dict[str, object]:
        packages = [self.package(f"package-{index:02d}") for index in range(33)]
        opengfx = self.package("openttd-opengfx")
        packages.append(opengfx)
        toolchain = [
            {
                "id": f"artifact-{index:02d}",
                "component": "fixture",
                "version": "1",
                "sha256": "3" * 64,
                "source_url": "https://example.invalid/artifact",
                "license": "MIT",
                "license_evidence": "fixture",
                "distribution_status": "fixture",
            }
            for index in range(25)
        ]
        base = {
            "schema_version": "openttd-rl-v1-dependency-provenance-manifest-1",
            "inputs": {
                "dependency_lock_sha256": "4" * 64,
                "build_input_lock_sha256": "5" * 64,
                "headless_build_identity_sha256": "6" * 64,
                "playable_build_identity_sha256": "7" * 64,
            },
            "openttd_source": {
                "id": "openttd",
                "version": "15.3",
                "sha256": "8" * 64,
                "source_url": "https://github.com/OpenTTD/OpenTTD",
                "license": "GPL-2.0-only",
                "distribution_status": "fixture",
            },
            "toolchain_artifacts": toolchain,
            "build_overlay_packages": packages,
            "opengfx": opengfx,
            "runtime_dependencies": [
                {
                    "soname": "libfixture.so.1",
                    "providers": ["headless", "playable"],
                    "origin": "host-runtime",
                    "package": "libfixture1",
                    "source_package": "fixture",
                    "version": "1",
                    "sha256": "9" * 64,
                    "source_url": "https://example.invalid/runtime",
                    "license_declarations": ["MIT"],
                    "license_evidence_sha256": "a" * 64,
                    "distribution_status": "fixture",
                }
            ],
            "result": "PASS",
        }
        manifest = dict(base)
        manifest["provenance_identity_sha256"] = hashlib.sha256(
            generate_dependency_provenance.canonical_bytes(base)
        ).hexdigest()
        return manifest

    def test_complete_fixture_manifest_passes(self) -> None:
        generate_dependency_provenance.validate_manifest(self.manifest(), self.schema_path)

    def test_missing_toolchain_artifact_fails(self) -> None:
        value = self.manifest()
        value["toolchain_artifacts"].pop()  # type: ignore[union-attr]
        with self.assertRaisesRegex(generate_dependency_provenance.ProvenanceError, "too short"):
            generate_dependency_provenance.validate_manifest(value, self.schema_path)

    def test_missing_license_fails(self) -> None:
        value = self.manifest()
        value["build_overlay_packages"][0]["license_declarations"] = []  # type: ignore[index]
        with self.assertRaisesRegex(generate_dependency_provenance.ProvenanceError, "too short"):
            generate_dependency_provenance.validate_manifest(value, self.schema_path)

    def test_opengfx_must_match_locked_package(self) -> None:
        value = self.manifest()
        value["opengfx"] = copy.deepcopy(value["opengfx"])
        value["opengfx"]["version"] = "2"  # type: ignore[index]
        with self.assertRaisesRegex(generate_dependency_provenance.ProvenanceError, "OpenGFX provenance differs"):
            generate_dependency_provenance.validate_manifest(value, self.schema_path)

    def test_license_text_fallback_is_explicit_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "copyright"
            path.write_text("Permission is hereby granted.\n", encoding="utf-8")
            declarations, digest = generate_dependency_provenance.license_record(path)
        self.assertEqual(declarations, ["LicenseRef-Debian-package-copyright-text"])
        self.assertEqual(digest, hashlib.sha256(b"Permission is hereby granted.\n").hexdigest())

    def test_json_output_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "manifest.json"
            generate_dependency_provenance.write_json(path, {"result": "PASS"})
            with self.assertRaisesRegex(generate_dependency_provenance.ProvenanceError, "refusing to overwrite"):
                generate_dependency_provenance.write_json(path, {"result": "FAIL"})


if __name__ == "__main__":
    unittest.main()
