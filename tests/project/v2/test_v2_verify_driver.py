#!/usr/bin/env python3
"""Behavior tests for the tiered V2 verification driver."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import verify_driver as driver


class V2VerifyDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.python = pathlib.Path(sys.executable).resolve()
        cls.inventory = driver.build_inventory(cls.root, cls.python)

    def command(self, command_id: str) -> driver.CommandSpec:
        return next(item for item in self.inventory if item.command_id == command_id)

    def status_command(self, command: driver.CommandSpec, status: int) -> driver.CommandSpec:
        return dataclasses.replace(
            command,
            argv=(str(self.python), "-c", f"import sys; sys.exit({status})"),
            environment=(),
        )

    def test_default_tier_is_full(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root), "--tools-python", str(self.python),
        ])
        self.assertIs(driver.resolve_config(args, {}).tier, driver.Tier.FULL)

    def test_inventory_is_unique_ordered_and_cumulative(self) -> None:
        inventory = driver.build_inventory(self.root, self.python)
        self.assertIsInstance(inventory, tuple)
        self.assertEqual(len(inventory), 56)
        self.assertEqual(len({item.command_id for item in inventory}), 56)
        fast = driver.select_commands(inventory, driver.Tier.FAST)
        contract = driver.select_commands(inventory, driver.Tier.CONTRACT)
        full = driver.select_commands(inventory, driver.Tier.FULL)
        self.assertIsInstance(fast, tuple)
        self.assertEqual([item.command_id for item in fast],
                         ["m22-corpus-binary", "v2-unit-tests"])
        self.assertEqual((len(fast), len(contract), len(full)), (2, 55, 56))
        self.assertEqual(full[-1].command_id, "v1-traceability")
        self.assertEqual(
            [item.command_id for item in full],
            [
                "research-baseline",
                "setting-inventory",
                "opponent-package-evidence",
                "opponent-runtime-evidence",
                "competition-manifest",
                "m15-scalable-contract",
                "m15-policy-contract",
                "m15-policy-evidence",
                "m15-map-matrix",
                "m15-native-source",
                "m15-native-reset-evidence",
                "m15-native-reset-matrix",
                "m15-observation-contract",
                "m15-observation-source",
                "m15-observation-evidence",
                "m15-action-contract",
                "m15-action-source",
                "m15-action-evidence",
                "m15-episode-source",
                "m15-episode-evidence",
                "m15-cross-scale-replay-evidence",
                "m15-competence-source",
                "m15-competence-evidence",
                "m16-cargo-source",
                "m16-cargo-evidence",
                "m17-rail-source",
                "m17-rail-evidence",
                "m18-ship-source",
                "m18-shipai-evidence",
                "m18-ship-evidence",
                "m19-air-source",
                "m19-air-evidence",
                "m20-competition-source",
                "m20-competition-evidence",
                "m21-broad-source",
                "m21-broad-evidence",
                "m22-learning-contract",
                "m22-native-corpus",
                "m22-corpus-binary",
                "m22-recovery-v1-evidence",
                "m22-recovery-v2-evidence",
                "m22-training-evidence",
                "m22-qualification-evidence",
                "m22-final-runtime-source",
                "m22-followup-runtime-source",
                "m22-final-v1-evaluation",
                "m22-followup-v1-manifest-build",
                "m22-followup-v1-manifest",
                "m22-followup-v1-evaluation",
                "m22-followup-v2-manifest-build",
                "m22-followup-v2-manifest",
                "m22-followup-v2-evaluation",
                "m23-contract",
                "v2-traceability",
                "v2-unit-tests",
                "v1-traceability",
            ],
        )

    def test_fast_and_contract_summaries_make_no_gate_or_g23_claim(self) -> None:
        for tier in (driver.Tier.FAST, driver.Tier.CONTRACT):
            with self.subTest(tier=tier):
                config = driver.VerificationConfig(self.root, self.python, tier)
                commands = driver.select_commands(self.inventory, tier)
                results = tuple(
                    driver.CommandResult(command, command.expected_status, "", "")
                    for command in commands
                )
                summary = driver.VerificationSummary(config=config, preflight_issues=(), results=results)
                rendered = "\n".join(driver.render_summary(summary))
                self.assertIn(f"V2_VERIFY_TIER={tier.name.lower()}", rendered)
                for forbidden in ("G23", "RELEASE", "V2_VERIFY_GATE"):
                    self.assertNotIn(forbidden, rendered.upper())

    def test_final_v1_exit_two_is_expected_success(self) -> None:
        command = self.command("m22-final-v1-evaluation")
        self.assertEqual(command.expected_status, 2)
        result = driver.execute_command(self.status_command(command, 2), self.root)
        self.assertTrue(result.passed)
        self.assertIsNone(result.failure_kind)

    def test_final_v1_zero_or_different_nonzero_is_failure(self) -> None:
        command = self.command("m22-final-v1-evaluation")
        for status in (0, 3):
            with self.subTest(status=status):
                result = driver.execute_command(self.status_command(command, status), self.root)
                self.assertFalse(result.passed)
                self.assertIs(result.failure_kind, driver.FailureKind.UNEXPECTED_STATUS)
                self.assertEqual(result.actual_status, status)

    def test_followup_v1_exit_two_is_expected_success(self) -> None:
        command = self.command("m22-followup-v1-evaluation")
        self.assertEqual(command.expected_status, 2)
        result = driver.execute_command(self.status_command(command, 2), self.root)
        self.assertTrue(result.passed)
        self.assertIsNone(result.failure_kind)

    def test_followup_v1_zero_or_different_nonzero_is_failure(self) -> None:
        command = self.command("m22-followup-v1-evaluation")
        for status in (0, 3):
            with self.subTest(status=status):
                result = driver.execute_command(self.status_command(command, status), self.root)
                self.assertFalse(result.passed)
                self.assertIs(result.failure_kind, driver.FailureKind.UNEXPECTED_STATUS)
                self.assertEqual(result.actual_status, status)

    def test_unexpected_status_is_retained_and_later_commands_continue(self) -> None:
        first = driver.CommandSpec(
            "first", driver.Tier.FAST, driver.CommandCategory.TEST,
            (str(self.python), "-c", "import sys; print('first-ran'); sys.exit(7)"),
        )
        second = driver.CommandSpec(
            "second", driver.Tier.FAST, driver.CommandCategory.TEST,
            (str(self.python), "-c", "print('second-ran')"),
        )
        config = driver.VerificationConfig(self.root, self.python, driver.Tier.FAST)
        summary = driver.run_verification(config, (first, second))
        self.assertEqual([result.command.command_id for result in summary.results], ["first", "second"])
        self.assertIn("first-ran", summary.results[0].stdout)
        self.assertIs(summary.results[0].failure_kind, driver.FailureKind.UNEXPECTED_STATUS)
        self.assertIn("second-ran", summary.results[1].stdout)
        self.assertTrue(summary.results[1].passed)
        self.assertFalse(summary.passed)

    def test_fast_preflight_needs_no_artifact_root_or_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            config = driver.VerificationConfig(root, self.python, driver.Tier.FAST)
            commands = driver.select_commands(self.inventory, driver.Tier.FAST)
            self.assertEqual(driver.preflight(config, commands), ())

    def test_contract_preflight_requires_exact_pinned_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            config = driver.VerificationConfig(root, self.python, driver.Tier.CONTRACT)
            commands = driver.select_commands(self.inventory, driver.Tier.CONTRACT)
            issues = driver.preflight(config, commands)
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.OPENTTD_SOURCE])
            self.assertIn("29f808ef0022064e6d9a83c8476d1e0f4686af86", issues[0].detail)

    def test_full_preflight_requires_artifact_root_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            marker = root / "executed"
            command = driver.CommandSpec(
                "must-not-run", driver.Tier.FULL, driver.CommandCategory.TEST,
                (str(self.python), "-c", f"import pathlib; pathlib.Path({str(marker)!r}).touch()"),
            )
            config = driver.VerificationConfig(root, self.python, driver.Tier.FULL)
            summary = driver.run_verification(config, (command,))
            self.assertEqual(summary.results, ())
            self.assertEqual(
                [issue.requirement for issue in summary.preflight_issues],
                [driver.Requirement.ARTIFACT_ROOT],
            )
            self.assertFalse(marker.exists())

    def test_preflight_accumulates_categories_and_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            errors = io.StringIO()
            with mock.patch.dict(os.environ, {}, clear=True), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = driver.main([
                    "--root", temporary,
                    "--tools-python", str(self.python),
                    "--tier", "full",
                ])
            self.assertEqual(status, 2)
            rendered = output.getvalue() + errors.getvalue()
            self.assertIn("openttd-source", rendered)
            self.assertIn("artifact-root", rendered)

    def test_artifact_resolution_prefers_cli_then_environment_then_none(self) -> None:
        base = ["--root", str(self.root), "--tools-python", str(self.python)]
        cli = driver.resolve_config(
            driver.parse_args([*base, "--artifact-root", "/cli-artifacts"]),
            {"OPENTTD_RL_ARTIFACT_ROOT": "/environment-artifacts"},
        )
        environment = driver.resolve_config(
            driver.parse_args(base),
            {"OPENTTD_RL_ARTIFACT_ROOT": "/environment-artifacts"},
        )
        absent = driver.resolve_config(driver.parse_args(base), {})
        self.assertEqual(cli.artifact_root, pathlib.Path("/cli-artifacts"))
        self.assertEqual(environment.artifact_root, pathlib.Path("/environment-artifacts"))
        self.assertIsNone(absent.artifact_root)

    def test_relative_artifact_environment_value_fails_closed(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root), "--tools-python", str(self.python),
        ])
        with self.assertRaisesRegex(ValueError, "artifact root must be an absolute path"):
            driver.resolve_config(args, {"OPENTTD_RL_ARTIFACT_ROOT": "relative/artifacts"})

    def test_spawn_and_timeout_failures_are_classified(self) -> None:
        spawn = driver.CommandSpec(
            "spawn", driver.Tier.FAST, driver.CommandCategory.TEST,
            ("/definitely/missing/v2-verification-command",),
        )
        timeout = driver.CommandSpec(
            "timeout", driver.Tier.FAST, driver.CommandCategory.TEST,
            (str(self.python), "-c", "import time; time.sleep(1)"), timeout_seconds=0.01,
        )
        spawn_result = driver.execute_command(spawn, self.root)
        timeout_result = driver.execute_command(timeout, self.root)
        self.assertIs(spawn_result.failure_kind, driver.FailureKind.SPAWN)
        self.assertIsNone(spawn_result.actual_status)
        self.assertIs(timeout_result.failure_kind, driver.FailureKind.TIMEOUT)
        self.assertIsNone(timeout_result.actual_status)

    def test_shell_parses_options_in_any_order_and_delegates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = pathlib.Path(temporary)
            fake_python = temporary_root / "python"
            fake_python.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
            fake_python.chmod(0o755)
            artifact_root = temporary_root / "artifacts"
            artifact_root.mkdir()
            observed = subprocess.run(
                (
                    str(self.root / "scripts/v2/verify.sh"),
                    "--artifact-root", str(artifact_root),
                    "--tier", "contract",
                    "--tools-python", str(fake_python),
                ),
                cwd=self.root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(observed.returncode, 0, observed.stderr)
            self.assertEqual(
                observed.stdout.splitlines(),
                [
                    str(self.root / "scripts/v2/verify_driver.py"),
                    "--root", str(self.root),
                    "--tier", "contract",
                    "--tools-python", str(fake_python),
                    "--artifact-root", str(artifact_root),
                ],
            )

    def test_shell_help_and_invalid_arguments_have_exact_exit_classes(self) -> None:
        script = str(self.root / "scripts/v2/verify.sh")
        help_result = subprocess.run(
            (script, "--help"), cwd=self.root, text=True, capture_output=True, check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--tier fast|contract|full", help_result.stdout)
        self.assertIn("--artifact-root /absolute/openttd-rl-artifacts", help_result.stdout)

        invalid_arguments = (
            ("--unknown",),
            ("--tier",),
            ("--tier", "fast", "--tier", "contract"),
            ("--tools-python", str(self.python), "--tools-python", str(self.python)),
            ("--artifact-root", "/first", "--artifact-root", "/second"),
            ("--tools-python", "relative/python"),
            ("--tools-python", str(self.root)),
            ("--artifact-root", "relative/artifacts"),
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                observed = subprocess.run(
                    (script, *arguments), cwd=self.root, text=True, capture_output=True, check=False,
                )
                self.assertEqual(observed.returncode, 2, observed.stdout + observed.stderr)


if __name__ == "__main__":
    unittest.main()
