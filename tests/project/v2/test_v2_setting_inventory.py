#!/usr/bin/env python3
"""Mutation tests for the pinned-source setting inventory."""

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

import generate_setting_inventory
import validate_setting_inventory
from source_context import SourceContext


class SettingInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.inventory_path = cls.root / "config/v2/setting-inventory.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-setting-inventory.schema.json"
        cls.object_repository = cls.root / "openttd-upstream"
        cls.inventory = validate_setting_inventory.load_json(cls.inventory_path)

    def validate_mutation(self, value: object, *, live: bool = False) -> validate_setting_inventory.SettingInventorySummary:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "setting-inventory.json"
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            return validate_setting_inventory.validate(
                self.root,
                path,
                self.schema_path,
                source_context=(
                    SourceContext.live(
                        self.object_repository,
                        self.inventory["engine_source"]["commit"],
                    )
                    if live
                    else SourceContext.offline()
                ),
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
    ) -> tuple[pathlib.Path, pathlib.Path, str, pathlib.Path]:
        project = directory / "project"
        repository = directory / "explicit-source"
        repository.mkdir()
        self.git(repository, "init", "-q")
        self.git(repository, "config", "user.email", "task4a@example.invalid")
        self.git(repository, "config", "user.name", "Task 4A")
        counts = {
            item["path"]: item["definition_count"]
            for item in self.inventory["source_files"]
        }
        for path, count in counts.items():
            source = repository / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                "".join(
                    f"[SDT_VAR]\nvar = _settings.value_{ordinal}\nname = \"setting_{ordinal}\"\n\n"
                    for ordinal in range(1, count + 1)
                ),
                encoding="utf-8",
            )
        self.git(repository, "add", ".")
        self.git(repository, "commit", "-qm", "pinned setting fixture")
        commit = self.git(repository, "rev-parse", "HEAD")
        tree = self.git(repository, "rev-parse", f"{commit}^{{tree}}")
        (project / "config/v1").mkdir(parents=True)
        (project / "config/v2").mkdir(parents=True)
        (project / "docs/project/schema").mkdir(parents=True)
        profile = validate_setting_inventory.load_json(
            self.root / "config/v1/openttd-source-profile.json"
        )
        profile["upstream"] = {"release": "15.3", "commit": commit, "tree": tree}
        (project / "config/v1/openttd-source-profile.json").write_text(
            json.dumps(profile, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copyfile(
            self.schema_path,
            project / "docs/project/schema/v2-setting-inventory.schema.json",
        )
        inventory_path = project / "config/v2/setting-inventory.json"
        return project, repository, commit, inventory_path

    def test_offline_validation_does_not_invoke_source_extraction(self) -> None:
        with mock.patch.object(
            generate_setting_inventory,
            "build_inventory",
            side_effect=AssertionError("unexpected source extraction"),
        ):
            summary = validate_setting_inventory.validate(
                self.root,
                source_context=SourceContext.offline(),
            )
        self.assertFalse(summary.live_source)

    def test_live_validation_uses_explicit_object_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            project, repository, commit, inventory_path = self.make_live_project(directory)
            context = SourceContext.live(repository, commit)
            inventory = generate_setting_inventory.build_inventory(
                project,
                context,
                "2026-08-02",
            )
            inventory_path.write_text(
                json.dumps(inventory, indent=2) + "\n",
                encoding="utf-8",
            )
            hostile = directory / "hostile"
            hostile.mkdir()
            self.git(hostile, "init", "-q")
            with mock.patch.dict(
                os.environ,
                {"GIT_DIR": str(hostile / ".git"), "GIT_WORK_TREE": str(hostile)},
                clear=False,
            ):
                summary = validate_setting_inventory.validate(
                    project,
                    source_context=context,
                )
            self.assertEqual((summary.source_files, summary.definitions), (20, 435))
            self.assertTrue(summary.live_source)

    def test_live_generation_rejects_duplicate_setting_basename(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project, repository, _commit, _inventory_path = self.make_live_project(
                pathlib.Path(raw)
            )
            duplicate = (
                repository
                / generate_setting_inventory.SOURCE_ROOT
                / "nested"
                / "company_settings.ini"
            )
            duplicate.parent.mkdir()
            duplicate.write_text(
                "[SDT_VAR]\nvar = _settings.duplicate\nname = \"duplicate\"\n",
                encoding="utf-8",
            )
            self.git(repository, "add", ".")
            self.git(repository, "commit", "-qm", "duplicate setting basename")
            commit = self.git(repository, "rev-parse", "HEAD")
            tree = self.git(repository, "rev-parse", f"{commit}^{{tree}}")
            profile_path = project / "config/v1/openttd-source-profile.json"
            profile = validate_setting_inventory.load_json(profile_path)
            profile["upstream"]["commit"] = commit
            profile["upstream"]["tree"] = tree
            profile_path.write_text(
                json.dumps(profile, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                generate_setting_inventory.SettingInventoryError,
                "source-file policy is incomplete",
            ):
                generate_setting_inventory.build_inventory(
                    project,
                    SourceContext.live(repository, commit),
                )

    def test_repository_inventory_passes_offline(self) -> None:
        static = validate_setting_inventory.validate(self.root)
        self.assertEqual(static.source_files, 20)
        self.assertEqual(static.definitions, 435)
        self.assertEqual(static.unique_keys, 424)
        self.assertEqual(static.duplicates, 11)
        self.assertFalse(static.live_source)

    def test_schema_hash_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "schema SHA-256"):
            self.validate_mutation(inventory)

    def test_engine_source_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["engine_source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "engine source"):
            self.validate_mutation(inventory)

    def test_missing_source_file_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["source_files"].pop()
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "source-file policy"):
            self.validate_mutation(inventory)

    def test_source_policy_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["source_files"][0]["disposition"] = "SCENARIO_PIN"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "disposition policy"):
            self.validate_mutation(inventory)

    def test_omitted_definition_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"].pop(100)
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "IDs"):
            self.validate_mutation(inventory)

    def test_duplicate_definition_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][1]["source_ordinal"] = inventory["definitions"][0]["source_ordinal"]
        with self.assertRaises(validate_setting_inventory.SettingInventoryValidationError):
            self.validate_mutation(inventory)

    def test_scope_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][0]["scope"] = "CLIENT"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "scope drifted"):
            self.validate_mutation(inventory)

    def test_definition_policy_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][0]["disposition"] = "SCENARIO_PIN"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "disposition drifted"):
            self.validate_mutation(inventory)

    def test_summary_count_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["counts"]["definitions"] += 1
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "summary counts"):
            self.validate_mutation(inventory)

    def test_secret_reclassification_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        row = next(item for item in inventory["definitions"] if item["disposition"] == "SECRET_FORBIDDEN")
        row["disposition"] = "HARNESS_PIN"
        row["rationale_code"] = "competition-runtime"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "disposition drifted"):
            self.validate_mutation(inventory)

    def test_source_expression_mutation_fails_live_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project, repository, commit, inventory_path = self.make_live_project(
                pathlib.Path(raw)
            )
            context = SourceContext.live(repository, commit)
            inventory = generate_setting_inventory.build_inventory(project, context)
            inventory["definitions"][0]["default_expression"] = "false"
            inventory_path.write_text(
                json.dumps(inventory, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                validate_setting_inventory.SettingInventoryValidationError,
                "live pinned-source extraction",
            ):
                validate_setting_inventory.validate(
                    project,
                    source_context=context,
                )


if __name__ == "__main__":
    unittest.main()
