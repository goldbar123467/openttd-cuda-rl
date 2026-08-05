#!/usr/bin/env python3
"""Mutation tests for the V2 research and command-coverage baseline."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import jsonschema

import source_context
import validate_research_baseline
from source_context import SourceContext


class V2ResearchBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.baseline_path = cls.root / "config/v2/research-baseline.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-research-baseline.schema.json"
        cls.baseline = validate_research_baseline.load_json(cls.baseline_path)

    @staticmethod
    def write_json(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "research-baseline.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> validate_research_baseline.ValidationSummary:
        return validate_research_baseline.validate(
            self.root,
            self.write_json(directory, value),
            self.schema_path,
        )

    @staticmethod
    def disposition(baseline: dict[str, object], identifier: str) -> dict[str, object]:
        return next(
            item
            for item in baseline["command_dispositions"]  # type: ignore[index]
            if item["id"] == identifier
        )

    @staticmethod
    def git(repository: pathlib.Path, *arguments: str) -> str:
        observed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            text=True,
            capture_output=True,
            check=False,
        )
        if observed.returncode != 0:
            raise AssertionError(observed.stderr)
        return observed.stdout.strip()

    def make_live_project(
        self,
        directory: pathlib.Path,
    ) -> tuple[pathlib.Path, pathlib.Path, str]:
        project = directory / "project"
        repository = directory / "explicit-source"
        repository.mkdir()
        self.git(repository, "init", "-q")
        self.git(repository, "config", "user.email", "task4a@example.invalid")
        self.git(repository, "config", "user.name", "Task 4A")
        commands = [
            command
            for disposition in self.baseline["command_dispositions"]
            for command in disposition["commands"]
        ]
        source = repository / self.baseline["engine"]["command_source"]
        source.parent.mkdir(parents=True)
        source.write_text(
            "enum Commands : uint8_t {\n"
            + "".join(f"    {command},\n" for command in commands)
            + "    CMD_END,\n};\n",
            encoding="utf-8",
        )
        self.git(repository, "add", ".")
        self.git(repository, "commit", "-qm", "pinned OpenTTD fixture")
        commit = self.git(repository, "rev-parse", "HEAD")
        tree = self.git(repository, "rev-parse", f"{commit}^{{tree}}")

        (project / "config/v1").mkdir(parents=True)
        (project / "config/v2").mkdir(parents=True)
        (project / "docs/project/schema").mkdir(parents=True)
        profile = validate_research_baseline.load_json(
            self.root / "config/v1/openttd-source-profile.json"
        )
        profile["upstream"] = {"release": "15.3", "commit": commit, "tree": tree}
        (project / "config/v1/openttd-source-profile.json").write_text(
            json.dumps(profile, indent=2) + "\n",
            encoding="utf-8",
        )
        baseline = copy.deepcopy(self.baseline)
        baseline["engine"]["commit"] = commit
        baseline["engine"]["tree"] = tree
        (project / "config/v2/research-baseline.json").write_text(
            json.dumps(baseline, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copyfile(
            self.schema_path,
            project / "docs/project/schema/v2-research-baseline.schema.json",
        )
        (project / "docs/project/V2_RESEARCH.md").write_text(
            "145 executable commands 4096 KrakenAI2 WmDOT Minimax\n",
            encoding="utf-8",
        )
        (project / "docs/project/V2_PLAN.md").write_text("fixture plan\n", encoding="utf-8")
        return project, repository, commit

    def test_offline_validation_does_not_invoke_git_on_object_repository(self) -> None:
        with mock.patch(
            "source_context.run_git",
            side_effect=AssertionError("unexpected source access"),
        ):
            summary = validate_research_baseline.validate(
                self.root,
                source_context=SourceContext.offline(),
            )
        self.assertFalse(summary.live_source)

    def test_live_validation_uses_explicit_object_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            project, repository, commit = self.make_live_project(directory)
            replacement_source = repository / self.baseline["engine"]["command_source"]
            replacement_source.write_text(
                "enum Commands : uint8_t { CMD_END, };\n",
                encoding="utf-8",
            )
            self.git(repository, "add", ".")
            self.git(repository, "commit", "-qm", "hostile replacement")
            replacement = self.git(repository, "rev-parse", "HEAD")
            self.git(repository, "replace", commit, replacement)
            hostile = directory / "hostile"
            hostile.mkdir()
            self.git(hostile, "init", "-q")
            calls: list[tuple[tuple[str, ...], pathlib.Path | None]] = []
            run_git = source_context.run_git

            def recording_run_git(
                *arguments: str,
                repository: pathlib.Path | str | None = None,
            ) -> subprocess.CompletedProcess[bytes]:
                calls.append((arguments, None if repository is None else pathlib.Path(repository)))
                return run_git(*arguments, repository=repository)

            with mock.patch.object(
                source_context,
                "run_git",
                side_effect=recording_run_git,
            ), mock.patch.dict(
                os.environ,
                {"GIT_DIR": str(hostile / ".git"), "GIT_WORK_TREE": str(hostile)},
                clear=False,
            ):
                context = SourceContext.live(repository, commit)
                summary = validate_research_baseline.validate(
                    project,
                    source_context=context,
                )
            self.assertTrue(summary.live_source)
            self.assertEqual(summary.commands, 145)
            operations = [arguments for arguments, _repository in calls]
            self.assertIn(("cat-file", "-e", f"{commit}^{{commit}}"), operations)
            self.assertIn(("rev-parse", f"{commit}^{{tree}}"), operations)
            self.assertIn(
                ("show", f"{commit}:{self.baseline['engine']['command_source']}"),
                operations,
            )
            self.assertTrue(
                all(invocation_repository == repository for _, invocation_repository in calls)
            )

    def test_missing_live_object_repository_is_a_preflight_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            missing = pathlib.Path(raw) / "missing-object-repository"
            with mock.patch.object(validate_research_baseline, "validate") as validator:
                status = validate_research_baseline.main(
                    ["--root", str(self.root), "--object-repo", str(missing)]
                )
            self.assertEqual(status, 1)
            validator.assert_not_called()

    def test_repository_baseline_passes(self) -> None:
        summary = validate_research_baseline.validate(self.root)
        self.assertEqual(summary.commands, 145)
        self.assertEqual(summary.feature_domains, 18)
        self.assertEqual(summary.opponents, 10)
        self.assertEqual(summary.native_rectangles, 49)

    def test_schema_hash_drift_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "schema SHA-256 mismatch"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_missing_engine_command_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        self.disposition(baseline, "policy-required")["commands"].remove("CMD_BUILD_AIRPORT")  # type: ignore[union-attr]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "missing=.*CMD_BUILD_AIRPORT"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_duplicate_engine_command_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        commands = self.disposition(baseline, "policy-optional")["commands"]
        commands.append("CMD_BUILD_AIRPORT")  # type: ignore[union-attr]
        commands.sort()  # type: ignore[union-attr]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "duplicate inventoried engine command"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_unknown_engine_command_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        commands = self.disposition(baseline, "policy-optional")["commands"]
        commands.append("CMD_INVENTED_V2")  # type: ignore[union-attr]
        commands.sort()  # type: ignore[union-attr]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "unknown=.*CMD_INVENTED_V2"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_unsorted_command_inventory_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        commands = self.disposition(baseline, "policy-required")["commands"]
        commands[0], commands[1] = commands[1], commands[0]  # type: ignore[index]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "not bytewise sorted"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_engine_commit_drift_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["engine"]["commit"] = "0" * 40
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "engine commit drifted"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_native_map_side_omission_fails_schema(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["maps"]["native_side_lengths"].remove(4096)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_research_baseline.V2ResearchError):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_generalization_without_rectangle_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["maps"]["generalization"] = [[64, 64], [128, 128], [256, 256], [1024, 1024]]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "contains no rectangular map"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_dangling_feature_source_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["feature_domains"][0]["source_ids"] = ["invented-source"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "unknown research sources"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_research_row_cannot_claim_pass(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["feature_domains"][0]["status"] = "PASS"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "cannot become PASS"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_opponent_content_id_url_mismatch_fails(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["opponents"][0]["package_url"] = "https://bananas.openttd.org/package/ai/00000000"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "package URL does not match"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_noop_cannot_advertise_transport_mode(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        noop = next(item for item in baseline["opponents"] if item["name"] == "NoOpAI")
        noop["advertised_modes"] = ["none", "road"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_research_baseline.V2ResearchError, "mixes the none mode"):
                self.validate_mutation(pathlib.Path(raw), baseline)

    def test_minimax_match_cannot_be_invented(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        baseline["user_ai_name_resolution"]["exact_catalog_match"] = True
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(
                    validate_research_baseline.load_json(self.schema_path)
                ).validate(baseline)


if __name__ == "__main__":
    unittest.main()
