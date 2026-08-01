#!/usr/bin/env python3
"""Unit and mutation tests for the V1 G01 evidence audit."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import audit_g01


class V1G01AuditTests(unittest.TestCase):
    def test_resource_protocol_ignores_measurements_not_commands(self) -> None:
        base = {
            "report_identity_sha256": "a" * 64,
            "plan": {"id": "fixture"},
            "workloads": [
                {
                    "id": "workload",
                    "command": ["binary", "--flag"],
                    "warmups": [{"wall_seconds": 1}],
                    "samples": [{"wall_seconds": 2}],
                    "aggregate": {"wall_seconds": {"median": 2}},
                    "result": "PASS",
                }
            ],
        }
        changed_measurement = json.loads(json.dumps(base))
        changed_measurement["workloads"][0]["samples"][0]["wall_seconds"] = 9
        self.assertEqual(
            audit_g01.resource_protocol(base),
            audit_g01.resource_protocol(changed_measurement),
        )
        changed_command = json.loads(json.dumps(base))
        changed_command["workloads"][0]["command"].append("--drift")
        self.assertNotEqual(
            audit_g01.resource_protocol(base),
            audit_g01.resource_protocol(changed_command),
        )

    def test_install_validation_rejects_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            installed = root / "stage/opt/openttd-rl-v1-headless/games/openttd"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"actual")
            manifest = {
                "variant": "headless",
                "install_artifacts": [
                    {
                        "path": "games/openttd",
                        "type": "file",
                        "mode": 0o644,
                        "size_bytes": 8,
                        "sha256": "0" * 64,
                    }
                ],
            }
            with self.assertRaisesRegex(audit_g01.G01AuditError, "content drift"):
                audit_g01.validate_install(root, manifest)

    def test_report_output_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "audit.json"
            audit_g01.write_json(path, {"result": "PASS"})
            with self.assertRaisesRegex(audit_g01.G01AuditError, "refusing to overwrite"):
                audit_g01.write_json(path, {"result": "FAIL"})


if __name__ == "__main__":
    unittest.main()
