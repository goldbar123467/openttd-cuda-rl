#!/usr/bin/env python3
"""Behavior tests for the tiered V2 verification driver."""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import hashlib
import importlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import MappingProxyType
from unittest import mock

import acquire_ai_package
import artifact_context
import source_context
from artifact_context import (
    LIVE_INPUT_ROLE_SPECS,
    ArtifactRequirement,
    DeferredArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    ToolRequirement,
    ValidationMode,
)
import validate_opponent_package_evidence
import validate_opponent_runtime_evidence
import validate_m18_shipai_evidence
import verify_driver as driver
from tests.project.v2.test_v2_m18_shipai_evidence import (
    make_live_shipai_fixture,
)


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

    def git(self, root: pathlib.Path, *arguments: str) -> str:
        observed = subprocess.run(
            ("git", "-C", str(root), *arguments),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(observed.returncode, 0, observed.stderr)
        return observed.stdout.strip()

    def initialized_submodule(
        self, temporary_root: pathlib.Path,
    ) -> tuple[pathlib.Path, pathlib.Path, str]:
        origin = temporary_root / "source-origin"
        origin.mkdir()
        self.git(origin, "init", "-q")
        self.git(origin, "config", "user.email", "task1@example.invalid")
        self.git(origin, "config", "user.name", "Task 1")
        (origin / "tracked.txt").write_text("pinned\n", encoding="utf-8")
        self.git(origin, "add", "tracked.txt")
        self.git(origin, "commit", "-qm", "pinned source")
        pin = self.git(origin, "rev-parse", "HEAD")

        outer = temporary_root / "outer"
        outer.mkdir()
        self.git(outer, "init", "-q")
        self.git(outer, "config", "user.email", "task1@example.invalid")
        self.git(outer, "config", "user.name", "Task 1")
        source = outer / "openttd-upstream"
        self.git(temporary_root, "clone", "-q", str(origin), str(source))
        self.git(source, "config", "user.email", "task1@example.invalid")
        self.git(source, "config", "user.name", "Task 1")
        self.git(outer, "add", "openttd-upstream")
        self.git(outer, "commit", "-qm", "pin source")
        return outer, source, pin

    def source_commands(self) -> tuple[driver.CommandSpec, ...]:
        return (
            driver.CommandSpec(
                "source-check",
                driver.Tier.CONTRACT,
                driver.CommandCategory.VALIDATOR,
                ("true",),
                requirements=frozenset({driver.Requirement.OPENTTD_SOURCE}),
            ),
        )

    def tools(self, *, git: pathlib.Path | None = None,
              bwrap: pathlib.Path | None = None) -> tuple[ToolRequirement, ...]:
        requirements = [ToolRequirement("python", self.python)]
        requirements.append(ToolRequirement(
            "git", git or pathlib.Path(shutil.which("git") or "/missing/git"),
        ))
        if bwrap is not None:
            requirements.append(ToolRequirement("bwrap", bwrap))
        return tuple(requirements)

    def bound_manifest(self, root: pathlib.Path) -> LiveInputManifest:
        roles = {
            role: root / "roles" / role
            for role in LIVE_INPUT_ROLE_SPECS
        }
        return LiveInputManifest(
            ValidationMode.LIVE,
            root,
            MappingProxyType(roles),
        )

    def configured(
        self,
        tier: driver.Tier,
        *,
        repository_root: pathlib.Path | None = None,
        artifact_root: pathlib.Path | None = None,
        live_inputs: LiveInputManifest | None = None,
        tools: tuple[ToolRequirement, ...] | None = None,
    ) -> driver.VerificationConfig:
        root = repository_root or self.root
        return driver.VerificationConfig(
            repository_root=root,
            tools_python=self.python,
            tier=tier,
            artifact_root=artifact_root,
            object_repository=root / driver.OPENTTD_SUBMODULE,
            live_inputs=live_inputs,
            tools=self.tools() if tools is None else tools,
        )

    def materialized_argv(
        self,
        command_id: str,
        config: driver.VerificationConfig,
    ) -> tuple[str, ...]:
        return driver.materialize_command(self.command(command_id), config).argv

    def test_default_tier_is_full(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root), "--tools-python", str(self.python),
        ])
        self.assertIs(driver.resolve_config(args, {}).tier, driver.Tier.FULL)

    def test_inventory_is_unique_ordered_and_cumulative(self) -> None:
        inventory = driver.build_inventory(self.root, self.python)
        self.assertIsInstance(inventory, tuple)
        self.assertEqual(len(inventory), 58)
        self.assertEqual(len({item.command_id for item in inventory}), 58)
        fast = driver.select_commands(inventory, driver.Tier.FAST)
        contract = driver.select_commands(inventory, driver.Tier.CONTRACT)
        full = driver.select_commands(inventory, driver.Tier.FULL)
        self.assertIsInstance(fast, tuple)
        self.assertEqual([item.command_id for item in fast],
                         ["m22-corpus-binary", "v2-fast-unit-tests"])
        self.assertEqual((len(fast), len(contract), len(full)), (2, 55, 58))
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
                "v2-fast-unit-tests",
                "v2-unit-tests",
                "v2-full-unit-tests",
                "v1-traceability",
            ],
        )

    def test_unit_module_inventory_is_explicit_disjoint_and_complete(self) -> None:
        unit_commands = tuple(
            command for command in self.inventory
            if command.command_id in {
                "v2-fast-unit-tests", "v2-unit-tests", "v2-full-unit-tests",
            }
        )
        self.assertEqual(
            [command.command_id for command in unit_commands],
            ["v2-fast-unit-tests", "v2-unit-tests", "v2-full-unit-tests"],
        )
        assigned = []
        for command in unit_commands:
            self.assertNotIn("discover", command.argv)
            modules = tuple(value for value in command.argv if value.startswith("tests.project.v2.test_v2_"))
            self.assertTrue(modules)
            assigned.extend(modules)
        expected = {
            f"tests.project.v2.{path.stem}"
            for path in (self.root / "tests/project/v2").glob("test_v2_*.py")
        }
        self.assertEqual(set(assigned), expected)
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual(self.command("m23-contract").minimum_tier, driver.Tier.FULL)
        self.assertTrue(all("-v" not in command.argv for command in unit_commands))
        fast = next(command for command in unit_commands if command.minimum_tier is driver.Tier.FAST)
        self.assertEqual(
            {value for value in fast.argv if value.startswith("tests.project.v2.test_v2_")},
            {
                "tests.project.v2.test_v2_artifact_context",
                "tests.project.v2.test_v2_m22_native_corpus_binary",
                "tests.project.v2.test_v2_source_context",
                "tests.project.v2.test_v2_verify_driver",
            },
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
        result = driver.execute_command(
            self.status_command(command, 2), self.configured(driver.Tier.CONTRACT)
        )
        self.assertTrue(result.passed)
        self.assertIsNone(result.failure_kind)

    def test_final_v1_zero_or_different_nonzero_is_failure(self) -> None:
        command = self.command("m22-final-v1-evaluation")
        for status in (0, 3):
            with self.subTest(status=status):
                result = driver.execute_command(
                    self.status_command(command, status), self.configured(driver.Tier.CONTRACT)
                )
                self.assertFalse(result.passed)
                self.assertIs(result.failure_kind, driver.FailureKind.UNEXPECTED_STATUS)
                self.assertEqual(result.actual_status, status)

    def test_followup_v1_exit_two_is_expected_success(self) -> None:
        command = self.command("m22-followup-v1-evaluation")
        self.assertEqual(command.expected_status, 2)
        result = driver.execute_command(
            self.status_command(command, 2), self.configured(driver.Tier.CONTRACT)
        )
        self.assertTrue(result.passed)
        self.assertIsNone(result.failure_kind)

    def test_followup_v1_zero_or_different_nonzero_is_failure(self) -> None:
        command = self.command("m22-followup-v1-evaluation")
        for status in (0, 3):
            with self.subTest(status=status):
                result = driver.execute_command(
                    self.status_command(command, status), self.configured(driver.Tier.CONTRACT)
                )
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

    def test_fast_ignores_configured_artifact_root_and_never_builds_live_context(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root),
            "--tools-python", str(self.python),
            "--tier", "fast",
            "--artifact-root", "/configured/but-ignored",
        ])
        with mock.patch.object(
            driver.LiveInputManifest,
            "load",
            side_effect=AssertionError("fast tier attempted live context construction"),
        ) as load:
            config = driver.resolve_config(
                args,
                {driver.ARTIFACT_ROOT_ENV: "/environment/also-ignored"},
            )
            summary = driver.run_verification(config, ())
        self.assertIsNone(config.artifact_root)
        self.assertEqual(summary.preflight_issues, ())
        load.assert_not_called()

    def test_contract_ignores_configured_artifact_root_and_runs_artifact_validators_offline(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root),
            "--tools-python", str(self.python),
            "--tier", "contract",
            "--artifact-root", "/configured/but-ignored",
        ])
        config = driver.resolve_config(
            args,
            {driver.ARTIFACT_ROOT_ENV: "/environment/also-ignored"},
        )
        materialized = driver.materialize_command(
            self.command("m15-action-evidence"), config,
        )
        self.assertIsNone(config.artifact_root)
        self.assertNotIn("--artifact-root", materialized.argv)
        self.assertEqual(
            dict(materialized.environment)["OPENTTD_RL_VALIDATION_MODE"],
            "offline",
        )
        self.assertNotIn(driver.ARTIFACT_ROOT_ENV, dict(materialized.environment))

    def test_contract_passes_live_source_context_only_to_research_and_setting_inventory(self) -> None:
        config = self.configured(driver.Tier.CONTRACT)
        bound = []
        for command in driver.select_commands(self.inventory, driver.Tier.CONTRACT):
            argv = driver.materialize_command(command, config).argv
            if "--object-repo" in argv:
                bound.append(command.command_id)
                self.assertEqual(
                    argv[argv.index("--object-repo") + 1],
                    str(config.object_repository),
                )
        self.assertEqual(bound, ["research-baseline", "setting-inventory"])

    def test_contract_materialization_does_not_resolve_or_bind_bwrap(self) -> None:
        config = self.configured(
            driver.Tier.CONTRACT,
            tools=self.tools(bwrap=pathlib.Path("/missing/contract-bwrap")),
        )
        with mock.patch.object(
            driver.VerificationConfig,
            "tool_path",
            side_effect=AssertionError("contract resolved a full-only tool"),
        ):
            argv = driver.materialize_command(
                self.command("m22-followup-v2-evaluation"), config,
            ).argv
        self.assertNotIn("--bwrap", argv)

    def test_full_materializes_consumer_specific_m22_binary_roles(self) -> None:
        artifact_root = pathlib.Path("/artifact-base")
        manifest = self.bound_manifest(artifact_root)
        bwrap = pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")
        config = self.configured(
            driver.Tier.FULL,
            artifact_root=artifact_root,
            live_inputs=manifest,
            tools=self.tools(bwrap=bwrap),
        )
        expected = {
            "m22-recovery-v1-evidence": {
                "--artifact-root": "recovery-v1-artifacts",
                "--executable": "recovery-v1-executable",
                "--corpus": "recovery-v1-corpus",
            },
            "m22-recovery-v2-evidence": {
                "--artifact-root": "recovery-v2-artifacts",
                "--executable": "v2-campaign-executable",
                "--corpus": "v2-corpus-binary",
            },
            "m22-training-evidence": {
                "--artifact-root": "training-artifacts",
                "--executable": "v2-campaign-executable",
                "--corpus": "v2-corpus-binary",
            },
            "m22-qualification-evidence": {
                "--artifact-root": "qualification-artifacts",
                "--training-artifact-root": "training-artifacts",
                "--executable": "qualification-executable",
                "--corpus": "v2-corpus-binary",
            },
        }
        for command_id, options in expected.items():
            with self.subTest(command_id=command_id):
                argv = self.materialized_argv(command_id, config)
                for option, role in options.items():
                    self.assertEqual(
                        argv[argv.index(option) + 1],
                        str(artifact_root / "roles" / role),
                    )

    def test_full_routes_m14_executable_to_every_recorded_consumer(self) -> None:
        artifact_root = pathlib.Path("/artifact-base")
        config = self.configured(
            driver.Tier.FULL,
            artifact_root=artifact_root,
            live_inputs=self.bound_manifest(artifact_root),
            tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
        )
        consumers = (
            "opponent-package-evidence",
            "opponent-runtime-evidence",
            "m15-map-matrix",
            "m18-shipai-evidence",
        )
        expected = str(artifact_root / "roles/m14-openttd-executable")
        for command_id in consumers:
            with self.subTest(command_id=command_id):
                argv = self.materialized_argv(command_id, config)
                self.assertEqual(argv[argv.index("--openttd") + 1], expected)

    def test_full_never_passes_live_base_to_an_m15_generation_cli(self) -> None:
        expected_modules = {
            "m15-action-evidence": "validate_m15_action_evidence.py",
            "m15-observation-evidence": "validate_m15_observation_evidence.py",
            "m15-episode-evidence": "validate_m15_episode_evidence.py",
            "m15-native-reset-matrix": "validate_m15_native_reset_matrix.py",
            "m15-map-matrix": "validate_m15_map_evidence.py",
        }
        generators = {
            "freeze_m15_action_evidence.py",
            "freeze_m15_observation_evidence.py",
            "freeze_m15_episode_evidence.py",
            "run_m15_native_reset_matrix.py",
            "run_m15_map_matrix.py",
        }
        artifact_root = pathlib.Path("/artifact-base")
        config = self.configured(
            driver.Tier.FULL,
            artifact_root=artifact_root,
            live_inputs=self.bound_manifest(artifact_root),
            tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
        )
        for command_id, module in expected_modules.items():
            with self.subTest(command_id=command_id):
                argv = self.materialized_argv(command_id, config)
                self.assertEqual(pathlib.Path(argv[1]).name, module)
                self.assertNotIn(pathlib.Path(argv[1]).name, generators)

    def test_full_uses_explicit_artifact_root_before_environment(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root), "--tools-python", str(self.python),
            "--tier", "full", "--artifact-root", "/explicit/artifacts",
        ])
        config = driver.resolve_config(
            args,
            {driver.ARTIFACT_ROOT_ENV: "/environment/artifacts"},
        )
        self.assertEqual(config.artifact_root, pathlib.Path("/explicit/artifacts"))
        self.assertEqual(config.object_repository, self.root / driver.OPENTTD_SUBMODULE)
        self.assertIn("bwrap", {tool.name for tool in config.tools})

    def test_full_uses_environment_artifact_root_when_cli_is_absent(self) -> None:
        args = driver.parse_args([
            "--root", str(self.root), "--tools-python", str(self.python),
            "--tier", "full",
        ])
        config = driver.resolve_config(
            args,
            {driver.ARTIFACT_ROOT_ENV: "/environment/artifacts"},
        )
        self.assertEqual(config.artifact_root, pathlib.Path("/environment/artifacts"))
        self.assertEqual(config.object_repository, self.root / driver.OPENTTD_SUBMODULE)
        self.assertIn("bwrap", {tool.name for tool in config.tools})

    def test_full_without_artifact_root_fails_preflight_before_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = pathlib.Path(temporary) / "command-ran"
            command = driver.CommandSpec(
                "must-not-run", driver.Tier.FULL, driver.CommandCategory.TEST,
                (str(self.python), "-c", f"import pathlib; pathlib.Path({str(marker)!r}).touch()"),
            )
            config = self.configured(driver.Tier.FULL, artifact_root=None)
            summary = driver.run_verification(config, (command,))
        self.assertEqual(summary.results, ())
        self.assertTrue(any(
            issue.requirement is driver.Requirement.ARTIFACT_ROOT
            for issue in summary.preflight_issues
        ))
        self.assertFalse(marker.exists())

    def test_full_preflight_reports_every_missing_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = pathlib.Path(temporary).resolve()
            config = self.configured(
                driver.Tier.FULL,
                artifact_root=artifact_root,
                tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
            )
            rendered = "\n".join(
                issue.detail for issue in driver.preflight(config, self.inventory)
            )
        for logical_set in (
            "v2-m14-ai-aaahogex-a",
            "v2-m15-action-evidence-a",
            "v2-m22-final-evaluation-b",
            "v2-m22-followup-runtime-a",
            "v2-m23-visible-runtime-baseline-a",
        ):
            self.assertIn(logical_set, rendered)

    def test_full_preflight_reports_source_repository_and_every_named_live_input_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary).resolve()
            artifact_root = base / "artifacts"
            artifact_root.mkdir()
            (artifact_root / "v2-live-inputs.json").write_text(
                json.dumps({
                    "schema_version": "openttd-rl-v2-live-inputs-1",
                    "roles": {},
                }),
                encoding="utf-8",
            )
            config = self.configured(
                driver.Tier.FULL,
                repository_root=base,
                artifact_root=artifact_root,
                tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
            )
            rendered = "\n".join(
                issue.detail for issue in driver.preflight(config, self.inventory)
            )
        self.assertIn("openttd", rendered.lower())
        for role in LIVE_INPUT_ROLE_SPECS:
            self.assertIn(role, rendered)

    def test_full_preflight_reports_missing_nested_files_git_and_bwrap_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary).resolve()
            artifact_root = base / "artifacts"
            (artifact_root / "set-a").mkdir(parents=True)
            command = driver.CommandSpec(
                "nested-live", driver.Tier.FULL, driver.CommandCategory.VALIDATOR,
                (str(self.python), "-c", "raise SystemExit('must not run')"),
                requirements=frozenset({driver.Requirement.OPENTTD_SOURCE}),
                live_inputs=(ArtifactRequirement(
                    "set-a", "nested/checkpoint.bin", "file", "nested-live",
                ),),
                live_input_module="synthetic-live-module",
                argument_bindings=(driver.ArgumentBinding(
                    "--artifact-root", "artifact-root",
                ),),
            )
            config = self.configured(
                driver.Tier.FULL,
                repository_root=base,
                artifact_root=artifact_root,
                tools=self.tools(
                    git=base / "missing-git",
                    bwrap=base / "missing-bwrap",
                ),
            )
            summary = driver.run_verification(config, (command,))
            rendered = "\n".join(issue.detail for issue in summary.preflight_issues)
        self.assertEqual(summary.results, ())
        self.assertIn("nested/checkpoint.bin", rendered)
        self.assertIn("git", rendered.lower())
        self.assertIn("bwrap", rendered.lower())
        self.assertIn("openttd", rendered.lower())

    def test_full_preflight_rejects_bwrap_digest_disagreement_or_mismatch(self) -> None:
        actual_bwrap = pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")
        records = (
            "m22-final-evaluation-evidence.json",
            "m22-followup-evaluation-evidence.json",
            "m22-followup-v2-evaluation-evidence.json",
        )
        for digests in (("0" * 64,) * 3, (driver.BWRAP_SHA256, "1" * 64, driver.BWRAP_SHA256)):
            with self.subTest(digests=digests), tempfile.TemporaryDirectory() as temporary:
                base = pathlib.Path(temporary).resolve()
                config_dir = base / "config/v2"
                config_dir.mkdir(parents=True)
                for name, digest in zip(records, digests, strict=True):
                    (config_dir / name).write_text(
                        json.dumps({"identity": {"bubblewrap_sha256": digest}}),
                        encoding="utf-8",
                    )
                artifact_root = base / "artifacts"
                artifact_root.mkdir()
                command = driver.CommandSpec(
                    "bwrap-consumer", driver.Tier.FULL, driver.CommandCategory.VALIDATOR,
                    (str(self.python), "-c", "pass"),
                    argument_bindings=(driver.ArgumentBinding("--bwrap", "tool", "bwrap"),),
                )
                config = self.configured(
                    driver.Tier.FULL,
                    repository_root=base,
                    artifact_root=artifact_root,
                    tools=self.tools(bwrap=actual_bwrap),
                )
                rendered = "\n".join(
                    issue.detail for issue in driver.preflight(config, (command,))
                )
                self.assertIn("bubblewrap", rendered.lower())
                self.assertTrue("disagree" in rendered.lower() or "mismatch" in rendered.lower())

    def test_full_does_not_convert_missing_live_input_to_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = pathlib.Path(temporary).resolve()
            command = driver.CommandSpec(
                "missing-live", driver.Tier.FULL, driver.CommandCategory.TEST,
                (str(self.python), "-c", "print('skipped: missing live input')"),
                live_inputs=(ArtifactRequirement(
                    "missing-set", "report.json", "file", "missing-live",
                ),),
                live_input_module="synthetic-live-module",
                argument_bindings=(driver.ArgumentBinding(
                    "--artifact-root", "artifact-root",
                ),),
            )
            config = self.configured(
                driver.Tier.FULL,
                artifact_root=artifact_root,
                tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
            )
            summary = driver.run_verification(config, (command,))
        self.assertEqual(summary.results, ())
        self.assertTrue(summary.preflight_issues)
        self.assertFalse(summary.passed)

    def test_materialization_is_pure_across_contract_and_full(self) -> None:
        command = self.command("m15-action-evidence")
        artifact_root = pathlib.Path("/artifact-base")
        contract = self.configured(driver.Tier.CONTRACT)
        full = self.configured(
            driver.Tier.FULL,
            artifact_root=artifact_root,
            live_inputs=self.bound_manifest(artifact_root),
            tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
        )
        before = command
        offline = driver.materialize_command(command, contract)
        live = driver.materialize_command(command, full)
        offline_again = driver.materialize_command(command, contract)
        self.assertEqual(command, before)
        self.assertEqual(offline, offline_again)
        self.assertNotIn("--artifact-root", offline.argv)
        self.assertEqual(live.argv[-2:], ("--artifact-root", str(artifact_root)))

    def test_every_artifact_backed_command_exports_a_pure_registry(self) -> None:
        artifact_backed = []
        for command in self.inventory:
            if command.live_inputs or any(
                binding.source in {"artifact-root", "live-role"}
                for binding in command.argument_bindings
            ):
                artifact_backed.append(command.command_id)
                self.assertIsNotNone(command.live_input_module, command.command_id)
                module = importlib.import_module(command.live_input_module)
                self.assertTrue(callable(getattr(module, "required_live_inputs", None)))
                self.assertEqual(command.live_inputs, tuple(command.live_inputs))
        self.assertIn("m22-final-v1-evaluation", artifact_backed)
        self.assertIn("v2-unit-tests", artifact_backed)

    def test_live_registry_locks_exact_commands_providers_and_provider_calls(self) -> None:
        artifact_backed = tuple(
            command for command in self.inventory
            if command.live_input_module is not None
        )
        self.assertEqual(len(artifact_backed), 39)
        self.assertEqual(len({command.live_input_module for command in artifact_backed}), 38)
        self.assertEqual(
            set(driver.LIVE_COMMAND_REGISTRY_SHA256),
            {command.command_id for command in artifact_backed},
        )
        self.assertEqual(
            set(driver.LIVE_PROVIDER_AST_SHA256),
            {command.live_input_module for command in artifact_backed},
        )
        self.assertEqual(
            [
                (
                    command.command_id,
                    command.live_input_module,
                    command.live_input_arguments,
                    command.include_live_roles,
                )
                for command in artifact_backed[-4:]
            ],
            [
                ("m22-final-v1-evaluation", "validate_m22_final_evaluation", (), False),
                ("m22-followup-v1-evaluation", "validate_m22_followup_evaluation", (), False),
                ("m22-followup-v2-evaluation", "validate_m22_followup_v2_evaluation", (), False),
                ("v2-unit-tests", "verify_driver", (), False),
            ],
        )
        self.assertEqual(driver.validate_live_input_registry(artifact_backed), ())

    def test_registry_rejects_every_snapshot_surface_mutation(self) -> None:
        registered = tuple(
            command for command in self.inventory
            if command.live_input_module is not None
        )

        def replace_registered(mutated: driver.CommandSpec) -> tuple[driver.CommandSpec, ...]:
            return tuple(
                mutated if command.command_id == mutated.command_id else command
                for command in registered
            )

        recovery = self.command("m22-recovery-v1-evidence")
        literal = self.command("m15-action-evidence")
        relocated = self.command("m15-action-source")
        role = next(
            item for item in recovery.live_inputs
            if isinstance(item, RoleRequirement)
        )
        unit = self.command("v2-unit-tests")
        mutations = {
            "literal-artifact-set": dataclasses.replace(
                literal,
                live_inputs=(
                    dataclasses.replace(
                        literal.live_inputs[0], logical_set="mutated-literal-set",
                    ),
                    *literal.live_inputs[1:],
                ),
            ),
            "relocated-source-path": dataclasses.replace(
                relocated,
                live_inputs=(
                    dataclasses.replace(
                        relocated.live_inputs[0], relative_path="mutated-source",
                    ),
                    *relocated.live_inputs[1:],
                ),
            ),
            "record-derived-checkpoint": dataclasses.replace(
                recovery, live_inputs=recovery.live_inputs[1:],
            ),
            "provider-module": dataclasses.replace(
                recovery, live_input_module="validate_m22_training_evidence",
            ),
            "provider-call-arguments": dataclasses.replace(
                recovery, live_input_arguments=(),
            ),
            "role-requirement": dataclasses.replace(
                recovery,
                live_inputs=tuple(
                    dataclasses.replace(item, role="mutated-role")
                    if item is role else item
                    for item in recovery.live_inputs
                ),
            ),
            "role-binding": dataclasses.replace(
                recovery,
                argument_bindings=(*recovery.argument_bindings[:-1], driver.ArgumentBinding(
                    "--corpus", "live-role", "v2-corpus-binary",
                )),
            ),
            "m23-git-read": dataclasses.replace(
                unit, git_apply_inputs=unit.git_apply_inputs[1:],
            ),
        }
        for surface, mutated in mutations.items():
            with self.subTest(surface=surface):
                issues = driver.validate_live_input_registry(replace_registered(mutated))
                self.assertTrue(issues)
                self.assertFalse(any("command inventory drifted" in issue.detail for issue in issues))

        evaluator = self.command("m22-followup-v2-evaluation")
        changed_tool = dataclasses.replace(
            evaluator,
            argument_bindings=tuple(
                driver.ArgumentBinding(binding.option, binding.source, "git")
                if binding.source == "tool" else binding
                for binding in evaluator.argument_bindings
            ),
        )
        tool_issues = driver.validate_live_input_registry(replace_registered(changed_tool))
        self.assertTrue(tool_issues)
        self.assertFalse(any(
            "command inventory drifted" in issue.detail for issue in tool_issues
        ))

    def test_registry_rejects_arbitrary_reads_in_every_local_dependency_layer(self) -> None:
        provider = importlib.import_module("validate_m15_action_evidence")
        registered = tuple(
            command for command in self.inventory
            if command.live_input_module is not None
        )
        cases = (
            ("artifact-context", artifact_context),
            ("source-context", source_context),
            ("transitive-helper", acquire_ai_package),
            ("direct-provider", provider),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for label, module in cases:
                with self.subTest(layer=label):
                    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
                    mutated = source + (
                        "\ndef injected_live_read():\n"
                        "    return pathlib.Path('/tmp/unregistered').read_bytes()\n"
                    )
                    ast.parse(mutated)
                    path = pathlib.Path(temporary) / f"{label}.py"
                    path.write_text(mutated, encoding="utf-8")
                    with mock.patch.object(module, "__file__", str(path)):
                        issues = driver.validate_live_input_registry(registered)
                    self.assertIn(
                        "fingerprint",
                        "\n".join(issue.detail for issue in issues).lower(),
                    )

    def test_consumed_registry_table_edit_cannot_bless_a_transitive_helper_read(
        self,
    ) -> None:
        registered = tuple(
            command for command in self.inventory
            if command.live_input_module is not None
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            helper_source = pathlib.Path(acquire_ai_package.__file__).read_text(
                encoding="utf-8"
            )
            helper_source += (
                "\ndef injected_live_read():\n"
                "    return pathlib.Path('/tmp/unregistered').read_bytes()\n"
            )
            helper_path = directory / "acquire_ai_package.py"
            helper_path.write_text(helper_source, encoding="utf-8")
            with mock.patch.object(
                acquire_ai_package, "__file__", str(helper_path),
            ):
                recomputed = MappingProxyType({
                    module: driver._provider_ast_sha256(module)
                    for module in driver.LIVE_PROVIDER_AST_SHA256
                })
                self.assertNotEqual(
                    recomputed["validate_opponent_package_evidence"],
                    driver.LIVE_PROVIDER_AST_SHA256[
                        "validate_opponent_package_evidence"
                    ],
                )
                with mock.patch.object(
                    driver, "LIVE_PROVIDER_AST_SHA256", recomputed,
                ):
                    issues = driver.validate_live_input_registry(registered)
        self.assertIn(
            "trust anchor",
            "\n".join(issue.detail for issue in issues).lower(),
        )

    def test_recursive_provider_fingerprint_is_cycle_safe(self) -> None:
        provider = importlib.import_module("validate_m15_action_evidence")
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            provider_path = directory / "validate_m15_action_evidence.py"
            provider_path.write_text(
                pathlib.Path(provider.__file__).read_text(encoding="utf-8")
                + "\nimport acquire_ai_package\n",
                encoding="utf-8",
            )
            helper_path = directory / "acquire_ai_package.py"
            helper_path.write_text(
                pathlib.Path(acquire_ai_package.__file__).read_text(encoding="utf-8")
                + "\nimport validate_m15_action_evidence\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                provider, "__file__", str(provider_path),
            ), mock.patch.object(
                acquire_ai_package, "__file__", str(helper_path),
            ):
                digest = driver._provider_ast_sha256(provider.__name__)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_repeated_registry_validation_reuses_content_keyed_dependency_parses(
        self,
    ) -> None:
        registered = tuple(
            command for command in self.inventory
            if command.live_input_module is not None
        )
        driver._FINGERPRINT_SOURCE_CACHE.clear()
        with mock.patch.object(
            driver.ast, "parse", wraps=driver.ast.parse,
        ) as parse:
            self.assertEqual(driver.validate_live_input_registry(registered), ())
            self.assertGreater(parse.call_count, 0)
            parse.reset_mock()
            self.assertEqual(driver.validate_live_input_registry(registered), ())
            self.assertEqual(parse.call_count, 0)

    def test_m14_nested_byte_mutations_stop_driver_before_commands(self) -> None:
        shipai = validate_m18_shipai_evidence.load(
            self.root / validate_m18_shipai_evidence.CONFIG
        )
        package_index = validate_m18_shipai_evidence.load(
            self.root / validate_m18_shipai_evidence.PACKAGE_INDEX
        )
        runtime_index = validate_m18_shipai_evidence.load(
            self.root / validate_m18_shipai_evidence.RUNTIME_INDEX
        )
        ship_evidence = validate_m18_shipai_evidence.load(
            self.root / validate_m18_shipai_evidence.SHIP_EVIDENCE
        )
        mutations = (
            (
                "archive",
                "v2-m14-ai-shipai-a",
                "content_download/ai/53484950-ShipAI-10.tar",
            ),
            (
                "copied-lock",
                "v2-m18-shipai-runtime-b",
                "ai-package-lock.json",
            ),
            (
                "transcript",
                "v2-m18-shipai-runtime-b",
                "openttd-runtime-console.log",
            ),
        )
        for label, logical_set, relative_path in mutations:
            with self.subTest(kind=label), tempfile.TemporaryDirectory() as temporary:
                fixture = make_live_shipai_fixture(
                    self.root,
                    pathlib.Path(temporary),
                    shipai,
                    package_index,
                    runtime_index,
                    ship_evidence,
                )
                requirements = validate_m18_shipai_evidence.required_live_inputs(
                    fixture["project_root"]
                )
                self.assertIn(
                    (logical_set, relative_path),
                    {
                        (item.logical_set, item.relative_path)
                        for item in requirements
                        if isinstance(item, DeferredArtifactRequirement)
                    },
                )
                artifact_root = fixture["artifact_root"]
                path = artifact_root / logical_set / relative_path
                path.write_bytes(f"arbitrary mutated {label}\n".encode())
                marker = artifact_root / "command-ran"
                command = driver.CommandSpec(
                    f"mutated-{label}",
                    driver.Tier.FULL,
                    driver.CommandCategory.TEST,
                    (
                        str(self.python), "-c",
                        f"import pathlib; pathlib.Path({str(marker)!r}).touch()",
                    ),
                    live_inputs=requirements,
                    live_input_module="validate_m18_shipai_evidence",
                    live_input_root=fixture["project_root"],
                )
                config = driver.VerificationConfig(
                    self.root,
                    self.python,
                    driver.Tier.FULL,
                    artifact_root=artifact_root,
                )
                with mock.patch.object(
                    driver, "validate_live_input_registry", return_value=(),
                ):
                    issues = driver.preflight(config, (command,))
                self.assertIn(driver.Requirement.ARTIFACT_INPUT, {
                    issue.requirement for issue in issues
                })
                with mock.patch.object(
                    driver, "validate_live_input_registry", return_value=(),
                ):
                    summary = driver.run_verification(config, (command,))
                self.assertEqual(summary.results, ())
                self.assertFalse(marker.exists())

    def test_m14_expansion_never_reads_a_failed_top_level_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = make_live_shipai_fixture(
                self.root,
                pathlib.Path(temporary),
                validate_m18_shipai_evidence.load(
                    self.root / validate_m18_shipai_evidence.CONFIG
                ),
                validate_m18_shipai_evidence.load(
                    self.root / validate_m18_shipai_evidence.PACKAGE_INDEX
                ),
                validate_m18_shipai_evidence.load(
                    self.root / validate_m18_shipai_evidence.RUNTIME_INDEX
                ),
                validate_m18_shipai_evidence.load(
                    self.root / validate_m18_shipai_evidence.SHIP_EVIDENCE
                ),
            )
            requirements = validate_m18_shipai_evidence.required_live_inputs(
                fixture["project_root"]
            )
            fixture["manifest_path"].write_bytes(b"mutated top authority\n")
            marker = fixture["artifact_root"] / "command-ran"
            command = driver.CommandSpec(
                "mutated-top-authority",
                driver.Tier.FULL,
                driver.CommandCategory.TEST,
                (
                    str(self.python),
                    "-c",
                    f"import pathlib; pathlib.Path({str(marker)!r}).touch()",
                ),
                live_inputs=requirements,
                live_input_module="validate_m18_shipai_evidence",
                live_input_root=fixture["project_root"],
            )
            config = driver.VerificationConfig(
                self.root,
                self.python,
                driver.Tier.FULL,
                artifact_root=fixture["artifact_root"],
            )
            with mock.patch.object(
                driver, "validate_live_input_registry", return_value=(),
            ), mock.patch.object(
                validate_m18_shipai_evidence,
                "expanded_live_inputs",
                side_effect=AssertionError("unauthenticated expansion"),
            ) as expanded:
                summary = driver.run_verification(config, (command,))
        expanded.assert_not_called()
        self.assertEqual(summary.results, ())
        self.assertIn(driver.Requirement.ARTIFACT_INPUT, {
            issue.requirement for issue in summary.preflight_issues
        })
        self.assertFalse(marker.exists())

    def test_expander_failure_does_not_hide_missing_successful_expansion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = pathlib.Path(temporary).resolve()
            marker = artifact_root / "command-ran"
            commands = []
            for suffix in ("a", "b"):
                logical_set = f"set-{suffix}"
                authority_path = artifact_root / logical_set / "authority.json"
                authority_path.parent.mkdir(parents=True)
                authority_path.write_bytes(f"authority-{suffix}\n".encode())
                authority = ArtifactRequirement(
                    logical_set,
                    "authority.json",
                    "file",
                    f"expander-{suffix}",
                    hashlib.sha256(authority_path.read_bytes()).hexdigest(),
                )
                deferred = DeferredArtifactRequirement(
                    logical_set,
                    "nested.bin",
                    "file",
                    f"expander-{suffix}",
                    authority,
                )
                commands.append(driver.CommandSpec(
                    f"expander-{suffix}",
                    driver.Tier.FULL,
                    driver.CommandCategory.TEST,
                    (
                        str(self.python),
                        "-c",
                        f"import pathlib; pathlib.Path({str(marker)!r}).touch()",
                    ),
                    live_inputs=(authority, deferred),
                    live_input_module=f"expander_{suffix}",
                    live_input_root=self.root,
                ))

            def expand(
                module_name: str,
                _context: artifact_context.ArtifactContext,
                _root: pathlib.Path,
                _arguments: tuple[object, ...],
            ) -> tuple[ArtifactRequirement, ...]:
                if module_name == "expander_a":
                    raise ValueError("expander A failed")
                return (ArtifactRequirement(
                    "set-b",
                    "nested.bin",
                    "file",
                    "expander-b",
                    hashlib.sha256(b"expected nested bytes\n").hexdigest(),
                ),)

            config = driver.VerificationConfig(
                self.root,
                self.python,
                driver.Tier.FULL,
                artifact_root=artifact_root,
            )
            with mock.patch.object(
                driver, "validate_live_input_registry", return_value=(),
            ), mock.patch.object(
                driver, "_provider_expanded_live_inputs", side_effect=expand,
            ):
                summary = driver.run_verification(config, tuple(commands))

        rendered = "\n".join(issue.detail for issue in summary.preflight_issues)
        self.assertIn("expander A failed", rendered)
        self.assertIn("set-b/nested.bin", rendered)
        self.assertEqual(summary.results, ())
        self.assertFalse(marker.exists())

    def test_registry_mutation_rejects_an_artifact_binding_without_a_closure(self) -> None:
        command = driver.CommandSpec(
            "unregistered-live-read", driver.Tier.FULL, driver.CommandCategory.VALIDATOR,
            (str(self.python), "-c", "pass"),
            argument_bindings=(driver.ArgumentBinding("--artifact-root", "artifact-root"),),
        )
        issues = driver.validate_live_input_registry((command,))
        self.assertEqual(len(issues), 1)
        self.assertIs(issues[0].requirement, driver.Requirement.LIVE_INPUT_REGISTRY)

    def test_m19_evidence_uses_validation_cli_never_generation_runner(self) -> None:
        command = self.command("m19-air-evidence")
        self.assertEqual(pathlib.Path(command.argv[1]).name, "validate_m19_air_evidence.py")
        self.assertNotIn("run_m19_air_matrix.py", command.argv)

    def test_full_unit_preflight_declares_both_exact_m23_source_directories(self) -> None:
        command = self.command("v2-unit-tests")
        directories = {
            (item.logical_set, item.relative_path)
            for item in command.live_inputs
            if isinstance(item, ArtifactRequirement) and item.kind == "directory"
        }
        self.assertIn(("v2-m22-followup-runtime-a", "source"), directories)
        self.assertIn(("v2-m23-visible-runtime-baseline-a", "."), directories)

    def test_empty_m23_source_directories_fail_git_preflight_before_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = pathlib.Path(temporary).resolve()
            (artifact_root / "v2-m22-followup-runtime-a/source").mkdir(parents=True)
            (artifact_root / "v2-m23-visible-runtime-baseline-a").mkdir()
            marker = artifact_root / "unit-command-ran"
            command = dataclasses.replace(
                self.command("v2-unit-tests"),
                argv=(str(self.python), "-c", f"import pathlib; pathlib.Path({str(marker)!r}).touch()"),
            )
            config = self.configured(driver.Tier.FULL, artifact_root=artifact_root)
            summary = driver.run_verification(config, (command,))
        self.assertEqual(summary.results, ())
        self.assertTrue(summary.preflight_issues)
        self.assertFalse(marker.exists())
        rendered = "\n".join(issue.detail for issue in summary.preflight_issues)
        self.assertIn("Git", rendered)
        self.assertIn("v2-m22-followup-runtime-a/source", rendered)
        self.assertIn("v2-m23-visible-runtime-baseline-a", rendered)

    def test_bare_git_uses_exact_preflighted_git_not_python_directory_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied_tools = pathlib.Path(temporary)
            copied_python = copied_tools / "python"
            copied_git = copied_tools / "git"
            shutil.copy2(self.python, copied_python)
            shutil.copy2("/usr/bin/echo", copied_git)
            exact_git = pathlib.Path(shutil.which("git") or "/missing/git")
            command = driver.CommandSpec(
                "bare-git", driver.Tier.FAST, driver.CommandCategory.TEST,
                ("git", "--version"),
            )
            config = driver.VerificationConfig(
                self.root,
                copied_python,
                driver.Tier.FAST,
                tools=(
                    ToolRequirement("python", copied_python),
                    ToolRequirement("git", exact_git),
                ),
            )
            self.assertEqual(driver.preflight(config, (command,)), ())
            result = driver.execute_command(command, config)
        self.assertTrue(result.passed, result.stderr)
        self.assertRegex(result.stdout, r"^git version ")

    def test_source_preflight_scrubs_hostile_git_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            outer, source, pin = self.initialized_submodule(base)
            hostile = {
                "GIT_DIR": str(source / ".git"),
                "GIT_WORK_TREE": str(source),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "status.showUntrackedFiles",
                "GIT_CONFIG_VALUE_0": "no",
                "GIT_REPLACE_REF_BASE": "refs/hostile/replace/",
            }
            config = self.configured(driver.Tier.CONTRACT, repository_root=outer)
            with mock.patch.object(driver, "OPENTTD_PIN", pin), mock.patch.dict(
                os.environ, hostile, clear=False,
            ):
                self.assertEqual(driver.preflight(config, self.source_commands()), ())

    def test_git_and_bwrap_discovery_preserves_lexical_paths_for_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tools = pathlib.Path(temporary)
            git_link = tools / "git"
            bwrap_link = tools / "bwrap"
            git_link.symlink_to(pathlib.Path(shutil.which("git") or "/missing/git"))
            bwrap_link.symlink_to(pathlib.Path("/usr/bin/echo"))
            args = driver.parse_args([
                "--root", str(self.root), "--tools-python", str(self.python),
                "--tier", "full", "--artifact-root", "/artifacts",
            ])
            config = driver.resolve_config(args, {"PATH": str(tools)})
        self.assertEqual(config.tool_path("git"), git_link)
        self.assertEqual(config.tool_path("bwrap"), bwrap_link)

    def test_v1_materialization_scrubs_all_optional_m07_m08_live_variables(self) -> None:
        forbidden = (
            "M07_TRAINER_EXECUTABLE",
            "M07_LIVE_MANIFEST",
            "M07_RECOVERY_REPORT",
            "M08_CUDA_REPORT",
            "M08_CPU_SMOKE_REPORT",
            "M08_CUDA_SMOKE_REPORT",
            "M08_LIVE_MANIFEST",
        )
        config = self.configured(
            driver.Tier.FULL,
            artifact_root=pathlib.Path("/artifact-base"),
            tools=self.tools(bwrap=pathlib.Path(shutil.which("bwrap") or "/missing/bwrap")),
        )
        seeded = {name: str(self.python) for name in forbidden}
        with mock.patch.dict(os.environ, seeded, clear=False):
            environment = dict(driver.materialize_command(
                self.command("v1-traceability"), config,
            ).environment)
        for name in forbidden:
            self.assertNotIn(name, environment)

    def test_contract_preflight_requires_exact_pinned_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            config = driver.VerificationConfig(root, self.python, driver.Tier.CONTRACT)
            commands = driver.select_commands(self.inventory, driver.Tier.CONTRACT)
            issues = driver.preflight(config, commands)
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.OPENTTD_SOURCE])
            self.assertIn("29f808ef0022064e6d9a83c8476d1e0f4686af86", issues[0].detail)

    def test_source_preflight_with_missing_git_aggregates_the_tool_issue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            source = root / driver.OPENTTD_SUBMODULE
            source.mkdir()
            (source / ".git").write_text("gitdir: /missing/gitdir\n", encoding="utf-8")
            config = self.configured(
                driver.Tier.CONTRACT,
                repository_root=root,
                tools=(
                    ToolRequirement("python", self.python),
                    ToolRequirement("git", root / "missing-git"),
                ),
            )
            issues = driver.preflight(config, self.source_commands())
        self.assertEqual(
            {issue.requirement for issue in issues},
            {driver.Requirement.OPENTTD_SOURCE, driver.Requirement.TOOL},
        )

    def test_contract_preflight_accepts_exact_clean_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer, _, pin = self.initialized_submodule(pathlib.Path(temporary))
            config = driver.VerificationConfig(outer, self.python, driver.Tier.CONTRACT)
            with mock.patch.object(driver, "OPENTTD_PIN", pin):
                self.assertEqual(driver.preflight(config, self.source_commands()), ())

    def test_contract_preflight_rejects_wrong_submodule_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer, source, pin = self.initialized_submodule(pathlib.Path(temporary))
            (source / "tracked.txt").write_text("different commit\n", encoding="utf-8")
            self.git(source, "add", "tracked.txt")
            self.git(source, "commit", "-qm", "wrong source")
            config = driver.VerificationConfig(outer, self.python, driver.Tier.CONTRACT)
            with mock.patch.object(driver, "OPENTTD_PIN", pin):
                issues = driver.preflight(config, self.source_commands())
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.OPENTTD_SOURCE])

    def test_contract_preflight_rejects_tracked_submodule_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer, source, pin = self.initialized_submodule(pathlib.Path(temporary))
            (source / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            config = driver.VerificationConfig(outer, self.python, driver.Tier.CONTRACT)
            with mock.patch.object(driver, "OPENTTD_PIN", pin):
                issues = driver.preflight(config, self.source_commands())
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.OPENTTD_SOURCE])

    def test_contract_preflight_rejects_untracked_submodule_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            outer, source, pin = self.initialized_submodule(pathlib.Path(temporary))
            self.git(source, "config", "status.showUntrackedFiles", "no")
            (source / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            config = driver.VerificationConfig(outer, self.python, driver.Tier.CONTRACT)
            with mock.patch.object(driver, "OPENTTD_PIN", pin):
                issues = driver.preflight(config, self.source_commands())
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.OPENTTD_SOURCE])

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
            with mock.patch.object(driver, "build_inventory", return_value=self.source_commands()), \
                    mock.patch.dict(os.environ, {}, clear=True), \
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

    def test_artifact_symlink_root_is_preserved_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            target = root / "artifacts"
            target.mkdir()
            supplied = root / "artifact-link"
            supplied.symlink_to(target, target_is_directory=True)
            args = driver.parse_args([
                "--root", str(root), "--tools-python", str(self.python),
                "--tier", "full", "--artifact-root", str(supplied),
            ])
            config = driver.resolve_config(args, {})
            command = driver.CommandSpec(
                "artifact-check", driver.Tier.FULL, driver.CommandCategory.TEST, ("true",),
            )
            self.assertEqual(config.artifact_root, supplied)
            issues = driver.preflight(config, (command,))
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.ARTIFACT_ROOT])

    def test_artifact_root_below_symlink_base_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            real_base = root / "real-base"
            artifact_root = real_base / "artifacts"
            artifact_root.mkdir(parents=True)
            linked_base = root / "linked-base"
            linked_base.symlink_to(real_base, target_is_directory=True)
            supplied = linked_base / "artifacts"
            args = driver.parse_args([
                "--root", str(root), "--tools-python", str(self.python),
                "--tier", "full", "--artifact-root", str(supplied),
            ])
            config = driver.resolve_config(args, {})
            command = driver.CommandSpec(
                "artifact-check", driver.Tier.FULL, driver.CommandCategory.TEST, ("true",),
            )
            self.assertEqual(config.artifact_root, supplied)
            issues = driver.preflight(config, (command,))
            self.assertEqual([issue.requirement for issue in issues], [driver.Requirement.ARTIFACT_ROOT])

    def test_spawn_and_timeout_failures_are_classified(self) -> None:
        spawn = driver.CommandSpec(
            "spawn", driver.Tier.FAST, driver.CommandCategory.TEST,
            ("/definitely/missing/v2-verification-command",),
        )
        timeout = driver.CommandSpec(
            "timeout", driver.Tier.FAST, driver.CommandCategory.TEST,
            (str(self.python), "-c", "import time; time.sleep(1)"), timeout_seconds=0.01,
        )
        config = self.configured(driver.Tier.FAST)
        spawn_result = driver.execute_command(spawn, config)
        timeout_result = driver.execute_command(timeout, config)
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
