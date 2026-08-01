#!/usr/bin/env python3
"""Unit and mutation tests for the fail-closed V1 OpenTTD build runner."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import run_openttd_build


class V1OpenTTDBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.lock_path = cls.root / "config/v1/openttd-build-input-lock.json"

    def test_repository_lock_is_the_exact_complete_offline_inventory(self) -> None:
        lock = run_openttd_build.load_lock(self.lock_path)
        self.assertEqual(lock["profile_id"], "ubuntu-24.04-x86_64-openttd-15.3")
        self.assertEqual(len(lock["artifacts"]), 34)
        self.assertEqual(
            sum(artifact["size_bytes"] for artifact in lock["artifacts"]),
            37_421_106,
        )
        self.assertEqual(
            hashlib.sha256(self.lock_path.read_bytes()).hexdigest(),
            "099675da5a508cd5a58405767e7713f5dbbc810b7dae52e6fc2687341bbc6985",
        )
        self.assertIn(
            "openttd-opengfx", {artifact["package"] for artifact in lock["artifacts"]}
        )

    def test_lock_rejects_policy_and_duplicate_package_drift(self) -> None:
        value = json.loads(self.lock_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "lock.json"
            changed = copy.deepcopy(value)
            changed["policy"]["builds_are_offline"] = False
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                run_openttd_build.OpenTTDBuildError, "not fail-closed/offline"
            ):
                run_openttd_build.load_lock(path)

            changed = copy.deepcopy(value)
            changed["artifacts"][1]["package"] = changed["artifacts"][0]["package"]
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                run_openttd_build.OpenTTDBuildError, "must be unique"
            ):
                run_openttd_build.load_lock(path)

    def test_exact_version_guard_fails_explicitly(self) -> None:
        self.assertEqual(
            run_openttd_build.exact_version("GCC", "13.3.0", "13.3.0"),
            "13.3.0",
        )
        with self.assertRaisesRegex(
            run_openttd_build.OpenTTDBuildError,
            "GCC version mismatch: expected=13.3.0 actual=14.1.0",
        ):
            run_openttd_build.exact_version("GCC", "14.1.0", "13.3.0")

    def test_clean_environment_removes_host_build_injection(self) -> None:
        tainted = {
            "CFLAGS": "-funsafe",
            "CXXFLAGS": "-funsafe",
            "LD_PRELOAD": "/tmp/inject.so",
            "PKG_CONFIG_PATH": "/tmp/pkgconfig",
        }
        with mock.patch.dict(os.environ, tainted, clear=False):
            environment = run_openttd_build.clean_environment()
        for name in tainted:
            self.assertNotIn(name, environment)
        self.assertEqual(environment["SOURCE_DATE_EPOCH"], run_openttd_build.SOURCE_DATE_EPOCH)
        self.assertEqual(environment["TZ"], "UTC")

    def test_ctest_inventory_is_sorted_nonempty_and_unique(self) -> None:
        payload = {"tests": [{"name": "second"}, {"name": "first"}]}
        self.assertEqual(
            run_openttd_build.parse_ctest_inventory(json.dumps(payload)),
            ["first", "second"],
        )
        payload["tests"].append({"name": "first"})
        with self.assertRaisesRegex(
            run_openttd_build.OpenTTDBuildError, "duplicate names"
        ):
            run_openttd_build.parse_ctest_inventory(json.dumps(payload))

    def test_junit_requires_the_prerun_inventory_and_all_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "results.xml"
            path.write_text(
                '<testsuite><testcase name="second"/><testcase name="first"/></testsuite>',
                encoding="utf-8",
            )
            self.assertEqual(
                run_openttd_build.parse_junit(path, ["first", "second"]),
                [
                    {"name": "first", "result": "PASS"},
                    {"name": "second", "result": "PASS"},
                ],
            )
            path.write_text(
                '<testsuite><testcase name="first"><failure/></testcase></testsuite>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                run_openttd_build.OpenTTDBuildError, "nonpassing tests"
            ):
                run_openttd_build.parse_junit(path, ["first"])

    def test_ldd_parser_is_path_independent_and_rejects_missing_libraries(self) -> None:
        first = run_openttd_build.parse_ldd(
            "linux-vdso.so.1 (0x1)\nlibc.so.6 => /first/libc.so.6 (0x2)\n"
            "/lib64/ld-linux-x86-64.so.2 (0x3)\n"
        )
        second = run_openttd_build.parse_ldd(
            "linux-vdso.so.1 (0x9)\nlibc.so.6 => /second/libc.so.6 (0x8)\n"
            "/lib64/ld-linux-x86-64.so.2 (0x7)\n"
        )
        self.assertEqual(first, second)
        with self.assertRaisesRegex(
            run_openttd_build.OpenTTDBuildError, "unresolved runtime dependency"
        ):
            run_openttd_build.parse_ldd("libmissing.so => not found\n")

    def test_install_inventory_is_sorted_and_content_addressed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            (root / "subdir").mkdir()
            executable = root / "subdir/tool"
            executable.write_bytes(b"fixture\n")
            executable.chmod(0o755)
            (root / "tool-link").symlink_to("subdir/tool")
            inventory = run_openttd_build.inventory_tree(root)
        self.assertEqual([item["path"] for item in inventory], ["subdir/tool", "tool-link"])
        self.assertEqual(inventory[0]["mode"], 0o755)
        self.assertEqual(
            inventory[0]["sha256"], hashlib.sha256(b"fixture\n").hexdigest()
        )
        self.assertEqual(inventory[1], {"path": "tool-link", "type": "symlink", "target": "subdir/tool"})

    def test_command_root_replacement_is_path_independent(self) -> None:
        first = run_openttd_build.replace_roots(
            {"argv": ["/one/root/source/file.cpp"], "cwd": "/one/root"},
            {"<ROOT>": pathlib.Path("/one/root")},
        )
        second = run_openttd_build.replace_roots(
            {"argv": ["/two/root/source/file.cpp"], "cwd": "/two/root"},
            {"<ROOT>": pathlib.Path("/two/root")},
        )
        self.assertEqual(first, second)

    def test_command_runner_rejects_warnings_and_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            runner = run_openttd_build.CommandRunner(
                pathlib.Path(raw) / "logs", run_openttd_build.clean_environment()
            )
            with self.assertRaisesRegex(
                run_openttd_build.OpenTTDBuildError, "emitted a warning"
            ):
                runner.run(
                    "warning",
                    ["/bin/sh", "-c", "printf 'warning: fixture\\n' >&2"],
                    reject_warnings=True,
                )
            with self.assertRaisesRegex(
                run_openttd_build.OpenTTDBuildError, "failed with exit code 7"
            ):
                runner.run("failure", ["/bin/sh", "-c", "exit 7"])

    def test_json_output_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = pathlib.Path(raw) / "manifest.json"
            run_openttd_build.write_json(output, {"result": "PASS"})
            with self.assertRaisesRegex(
                run_openttd_build.OpenTTDBuildError, "refusing to overwrite output"
            ):
                run_openttd_build.write_json(output, {"result": "FAIL"})


if __name__ == "__main__":
    unittest.main()
