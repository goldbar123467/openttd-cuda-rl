#!/usr/bin/env python3
"""Mutation tests for the corrected retained M22 follow-up runtime source."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import jsonschema

from artifact_context import ARTIFACT_ROOT_ENV, ArtifactContext, ArtifactContextError
import prepare_m22_followup_runtime as preparation
from tests.project.v2.test_v2_m22_final_runtime_source import (
    _git,
    _replace_record_file,
    expected_runtime_closure,
    make_live_runtime_fixture,
)
import validate_m22_followup_runtime_source as validator


class M22FollowupRuntimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "runtime-source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def smoke(value: dict[str, object], case_id: str) -> dict[str, object]:
        return next(item for item in value["smokes"] if item["case"]["case_id"] == case_id)

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(
                validator.M22FollowupRuntimeSourceError, pattern
            ) if pattern else self.assertRaises(validator.M22FollowupRuntimeSourceError)
            with context:
                validator.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    artifact_context=ArtifactContext.offline(),
                )

    def test_repository_runtime_source_passes(self) -> None:
        result = validator.validate(self.root)
        self.assertEqual((result["files"], result["smokes"], result["live"]), (9, 14, False))

    def test_live_runtime_source_and_all_artifacts_pass(self) -> None:
        artifact_root = os.environ.get(ARTIFACT_ROOT_ENV)
        if artifact_root is None:
            self.skipTest("live artifact validation is outside offline mode")
        result = validator.validate(self.root, artifact_context=ArtifactContext.live(artifact_root))
        self.assertTrue(result["live"])

    def test_relocated_root_does_not_rewrite_retained_artifact(self) -> None:
        retained = (self.root / validator.CONFIG).read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            validator.validate(
                config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
            )
        self.assertEqual((self.root / validator.CONFIG).read_bytes(), retained)

    def test_offline_validation_never_opens_recorded_runtime_paths(self) -> None:
        recorded_root = self.source["retained_artifact"]
        original_open = pathlib.Path.open
        original_is_file = pathlib.Path.is_file
        original_is_dir = pathlib.Path.is_dir
        original_stat = pathlib.Path.stat

        def reject_open(path: pathlib.Path, *args: object, **kwargs: object):
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path opened offline: {path}")
            return original_open(path, *args, **kwargs)

        def reject_is_file(path: pathlib.Path) -> bool:
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path probed offline: {path}")
            return original_is_file(path)

        def reject_is_dir(path: pathlib.Path) -> bool:
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path probed offline: {path}")
            return original_is_dir(path)

        def reject_stat(path: pathlib.Path, *args: object, **kwargs: object):
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path stated offline: {path}")
            return original_stat(path, *args, **kwargs)

        real_git = validator.git

        def reject_recorded_git(repository: pathlib.Path, *arguments: str) -> str:
            if str(repository).startswith(recorded_root):
                raise AssertionError(f"recorded Git path opened offline: {repository}")
            return real_git(repository, *arguments)

        with mock.patch.object(pathlib.Path, "open", reject_open), \
             mock.patch.object(pathlib.Path, "is_file", reject_is_file), \
             mock.patch.object(pathlib.Path, "is_dir", reject_is_dir), \
             mock.patch.object(pathlib.Path, "stat", reject_stat), \
             mock.patch.object(validator, "git", side_effect=reject_recorded_git):
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_relocated_live_runtime_and_smokes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            summary = validator.validate(
                config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
            )
        self.assertTrue(summary["live"])

    def test_relocated_m21_base_reproduces_source_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, result_source = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            summary = validator.validate(
                config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
            )
            observed_tree = _git(result_source, "rev-parse", "HEAD^{tree}")
        self.assertEqual(summary["source_tree"], observed_tree)

    def test_required_live_inputs_are_the_exact_runtime_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        keys = tuple((item.logical_set, item.relative_path, item.kind) for item in requirements)
        expected = expected_runtime_closure(
            "v2-m22-followup-runtime-a",
            "build-followup",
            (
                "source-g15-toyland-road", "source-g16-toyland-cargo", "source-g17-arctic-rail",
                "source-g18-tropic-water", "source-g19-toyland-air", "source-g20-tropic-aaahogex",
                "source-g21-arctic-content", "source-g21-tropic-gamescript",
                "followup-source-g19-passenger-multimodal", "followup-source-g20-aaahogex-128",
                "followup-source-g20-krakenai2-128", "followup-source-g20-noopai-128",
                "followup-source-g21-authority-economy", "followup-source-g21-events",
            ),
        )
        self.assertEqual(keys, expected)
        self.assertEqual(len(keys), len(set(keys)))

    def test_missing_live_input_fails_before_git_or_semantic_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            (base / "v2-m22-followup-runtime-a/base.cfg").unlink()
            with mock.patch.object(validator, "git", side_effect=AssertionError("Git ran before preflight")), \
                 mock.patch.object(validator, "_validate_live_source", side_effect=AssertionError("source reader ran before preflight")), \
                 mock.patch.object(validator, "_validate_live_files", side_effect=AssertionError("file reader ran before preflight")):
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(
                        config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                    )

    def test_recorded_runtime_path_traversal_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["executable"]["path"] = value["retained_artifact"] + "/../escape"
        self.mutation_fails(value, "normalized POSIX")

    def test_runtime_file_alias_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["logs"]["build"] = copy.deepcopy(value["build"]["logs"]["configure"])
        self.mutation_fails(value, "layout|duplicate")

    def test_custom_config_cannot_substitute_m21_base_identity(self) -> None:
        value = copy.deepcopy(self.source)
        value["base"]["commit"] = "1" * 40
        value["base"]["tree"] = "2" * 40
        self.mutation_fails(value, "base identity")

    def test_wrong_ai_name_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["ai_archives"][1]["name"] = "SubstituteAI"
        self.mutation_fails(value)

    def test_hardlinked_live_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            result = base / "v2-m22-followup-runtime-a"
            first = result / "smokes/source-g15-toyland-road/openttd.log"
            second = result / "smokes/source-g16-toyland-cargo/openttd.log"
            second.unlink()
            os.link(first, second)
            with self.assertRaisesRegex(validator.M22FollowupRuntimeSourceError, "hard link"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_symlinked_live_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            result = base / "v2-m22-followup-runtime-a"
            config = result / "base.cfg"
            target = result / "untracked-target.cfg"
            target.write_bytes(config.read_bytes())
            config.unlink()
            config.symlink_to(target)
            with self.assertRaisesRegex(ArtifactContextError, "symlink"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_historical_repository_commit_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["repository"]["commit"] = "0" * 40
        self.mutation_fails(value, "git cat-file")

    def test_historical_repository_tree_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["repository"]["tree"] = "0" * 40
        self.mutation_fails(value, "historical repository identity")

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["patches"][1]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch record drifted")

    def test_patch_order_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["patches"].reverse()
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_immutable_final_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["boundaries"]["immutable_final_v1"]["evidence_sha256"] = "0" * 64
        self.mutation_fails(value, "immutable final/follow-up boundary")

    def test_followup_manifest_open_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["boundaries"]["followup"]["manifest_opened"] = True
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_smoke_order_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0], value["smokes"][1] = value["smokes"][1], value["smokes"][0]
        self.mutation_fails(value, "inventory/order")

    def test_vacuous_corrected_passenger_metric_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g19-passenger-multimodal")
        smoke["metrics"]["delivered"] = 0
        self.mutation_fails(value, "useful-service smoke is vacuous")

    def test_competition_size_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g20-krakenai2-128")
        smoke["case"]["map_width"] = 64
        self.mutation_fails(value, "public/private projection drifted")

    def test_competition_metric_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g20-noopai-128")
        smoke["metrics"]["delivered"] = 24
        self.mutation_fails(value, "competition smoke is vacuous")

    def test_authority_save_exact_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g21-authority-economy")
        smoke["metrics"]["save_load_exact"] = False
        self.mutation_fails(value, "authority smoke drifted")

    def test_executable_identity_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            value["executable"]["sha256"] = "0" * 64
            for smoke in value["smokes"]:
                smoke["executable_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_smoke_report_digest_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            value["smokes"][0]["report_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_digest_matched_ctest_inventory_with_nonstring_name_is_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            names: list[object] = [f"upstream-{index:03d}" for index in range(98)]
            names[4] = ["unhashable"]
            payload = (json.dumps({"tests": names}) + "\n").encode()
            _replace_record_file(
                base / "v2-m22-followup-runtime-a", value["retained_artifact"],
                value["build"]["test_inventory"], payload,
            )
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22FollowupRuntimeSourceError, "CTest inventory"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_matched_ctest_inventory_missing_tests_is_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            payload = b'{"wrong":[]}\n'
            _replace_record_file(base / "v2-m22-followup-runtime-a", value["retained_artifact"],
                                 value["build"]["test_inventory"], payload)
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22FollowupRuntimeSourceError, "CTest inventory"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_removed_base_source_option_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                validator.main(["--root", str(self.root), "--base" + "-source", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_artifact_root_wins_over_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = pathlib.Path(raw).resolve()
            configured = parent / "configured"
            configured.mkdir()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, configured, self.source,
                patches=preparation.PATCHES, logical_set="v2-m22-followup-runtime-a",
            )
            with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(parent / "wrong")}, clear=False):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = validator.main([
                        "--root", str(config_path.parent), "--config", str(config_path),
                        "--artifact-root", str(configured),
                    ])
        self.assertEqual(status, 0)

    def test_relative_cli_artifact_root_fails_without_environment_fallback(self) -> None:
        with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(self.root)}, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                status = validator.main(["--root", str(self.root), "--artifact-root", "relative/artifacts"])
        self.assertEqual(status, 1)

    def test_ctest_claim_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["upstream_ctest"]["passed"] = 97
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
