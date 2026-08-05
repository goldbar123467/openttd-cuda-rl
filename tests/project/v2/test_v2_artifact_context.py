#!/usr/bin/env python3
"""Behavior tests for portable V2 artifact and live-input contexts."""

from __future__ import annotations

import argparse
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import artifact_context
from artifact_context import (
    ARTIFACT_ROOT_ENV,
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    ToolRequirement,
    ValidationMode,
    add_artifact_root_argument,
    preflight_tools,
    resolve_artifact_root,
)


FROZEN_FILE_DIGESTS = {
    "recovery-v1-executable": "2f26dc241b029abeb4641f1497e9347a6675a3d607b564855518fb91b391356f",
    "recovery-v1-corpus": "0d5aa3944241b3c00e0b1283de586e00c8fb0a5a51abe385c7e3288785369a0d",
    "v2-campaign-executable": "62ed497cf6f237248a54861269e5b0ad27c8808f8e3d4d7b73d29148e84a5fc2",
    "v2-corpus-binary": "d6cdf022e4382a90da4b89a225eb3e1cf15833a63d9c450712aa4c9dbfbc4021",
    "qualification-executable": "ae5a74d890e980a6c1308cdad31154e902d0c5e40f234f98b7d34e61849f4b52",
    "final-v1-evaluator": "bc87f4608643b4664068381fa5136d464c44bd05dad09a66fa088bfa995b92e6",
    "m14-openttd-executable": "8b27f06113d08fa3a21f81c01721873194f35bf885963be2697cc9da52e1ef9a",
}

DIRECTORY_ROLES = (
    "recovery-v1-artifacts",
    "recovery-v2-artifacts",
    "training-artifacts",
    "qualification-artifacts",
)


class V2ArtifactContextTests(unittest.TestCase):
    def make_live_inputs(
        self,
        root: pathlib.Path,
        *,
        roles: dict[str, str] | None = None,
        raw: str | None = None,
    ) -> pathlib.Path:
        if roles is None:
            roles = {}
            for role in DIRECTORY_ROLES:
                path = root / "inputs" / role
                path.mkdir(parents=True, exist_ok=True)
                roles[role] = path.relative_to(root).as_posix()
            for role in FROZEN_FILE_DIGESTS:
                path = root / "inputs" / role
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"fixture for {role}\n".encode("ascii"))
                roles[role] = path.relative_to(root).as_posix()
        manifest = root / "v2-live-inputs.json"
        manifest.write_text(
            raw if raw is not None else json.dumps({
                "schema_version": "openttd-rl-v2-live-inputs-1",
                "roles": roles,
            }),
            encoding="utf-8",
        )
        return manifest

    def load_valid_manifest(self, root: pathlib.Path) -> LiveInputManifest:
        self.make_live_inputs(root)

        def frozen_digest(path: pathlib.Path) -> str:
            return FROZEN_FILE_DIGESTS[path.name]

        with mock.patch.object(artifact_context, "_sha256_file", side_effect=frozen_digest):
            return LiveInputManifest.load(root)

    def test_explicit_root_wins_over_environment(self) -> None:
        parser = argparse.ArgumentParser()
        add_artifact_root_argument(parser)
        explicit = parser.parse_args(["--artifact-root", "/srv/explicit"]).artifact_root
        self.assertEqual(
            resolve_artifact_root(explicit, {ARTIFACT_ROOT_ENV: "/srv/environment"}),
            pathlib.Path("/srv/explicit"),
        )

    def test_environment_root_is_used_when_explicit_root_is_absent(self) -> None:
        self.assertEqual(
            resolve_artifact_root(None, {ARTIFACT_ROOT_ENV: "/srv/environment"}),
            pathlib.Path("/srv/environment"),
        )

    def test_no_configured_root_returns_none(self) -> None:
        self.assertIsNone(resolve_artifact_root(None, {}))

    def test_relative_explicit_root_is_rejected_without_environment_fallback(self) -> None:
        with self.assertRaisesRegex(ArtifactContextError, "artifact root must be an absolute path"):
            resolve_artifact_root("relative/explicit", {ARTIFACT_ROOT_ENV: "/srv/environment"})

    def test_relative_environment_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(ArtifactContextError, "artifact root must be an absolute path"):
            resolve_artifact_root(None, {ARTIFACT_ROOT_ENV: "relative/environment"})

    def test_offline_context_rejects_artifact_set_access(self) -> None:
        context = ArtifactContext.offline()
        self.assertIs(context.mode, ValidationMode.OFFLINE)
        self.assertFalse(context.is_live)
        with self.assertRaisesRegex(
            ArtifactContextError,
            "^offline validation attempted live artifact access$",
        ):
            context.artifact_set("m22-runtime")
        with self.assertRaisesRegex(
            ArtifactContextError,
            "^offline validation attempted live artifact access$",
        ):
            context.resolve(ArtifactRequirement("m22-runtime", "report.json", "file", "test"))

    def test_offline_context_rejects_relocation(self) -> None:
        with self.assertRaisesRegex(
            ArtifactContextError,
            "^offline validation attempted live artifact access$",
        ):
            ArtifactContext.offline().relocate(
                "/recorded/m22/source",
                recorded_root="/recorded/m22",
            )

    def test_live_context_maps_logical_set_below_current_host_root(self) -> None:
        context = ArtifactContext.live(pathlib.Path("/srv/openttd-rl"))
        self.assertIs(context.mode, ValidationMode.LIVE)
        self.assertTrue(context.is_live)
        self.assertEqual(
            context.artifact_set("v2-m22-followup-runtime-a"),
            pathlib.Path("/srv/openttd-rl/v2-m22-followup-runtime-a"),
        )

    def test_live_context_relocates_nested_recorded_path(self) -> None:
        recorded = "/home/thecl/.codex/artifacts/openttd-rl/v2-m22-followup-runtime-a/source"
        context = ArtifactContext.live(pathlib.Path("/srv/openttd-rl"))
        self.assertEqual(
            context.relocate(
                recorded,
                recorded_root="/home/thecl/.codex/artifacts/openttd-rl/v2-m22-followup-runtime-a",
            ),
            pathlib.Path("/srv/openttd-rl/v2-m22-followup-runtime-a/source"),
        )

    def test_relocation_does_not_mutate_recorded_json_value(self) -> None:
        record = {"path": "/recorded/root/set-a/nested/report.json"}
        original = dict(record)
        relocated = ArtifactContext.live(pathlib.Path("/current")).relocate(
            record["path"], recorded_root="/recorded/root/set-a",
        )
        self.assertEqual(relocated, pathlib.Path("/current/set-a/nested/report.json"))
        self.assertEqual(record, original)

    def test_relocation_rejects_path_outside_recorded_set(self) -> None:
        context = ArtifactContext.live(pathlib.Path("/current"))
        for recorded in ("/recorded/root/set-b/report.json", "/recorded/root/set-a/../escape"):
            with self.subTest(recorded=recorded), self.assertRaisesRegex(
                ArtifactContextError, "recorded path is outside recorded root",
            ):
                context.relocate(recorded, recorded_root="/recorded/root/set-a")

    def test_artifact_set_rejects_multicomponent_or_parent_name(self) -> None:
        context = ArtifactContext.live(pathlib.Path("/srv/openttd-rl"))
        for name in ("", ".", "..", "nested/set", "nested\\set", "../set"):
            with self.subTest(name=name), self.assertRaises(ArtifactContextError):
                context.artifact_set(name)

    def test_preflight_reports_all_missing_sets_in_sorted_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            context = ArtifactContext.live(root)
            requirements = (
                ArtifactRequirement("z-set", "z.json", "file", "z-consumer"),
                ArtifactRequirement("a-set", "a.json", "file", "a-consumer"),
                ArtifactRequirement("z-set", "z.json", "file", "z-consumer"),
            )
            with self.assertRaises(ArtifactContextError) as raised:
                context.preflight(requirements)
            lines = str(raised.exception).splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("a-set", lines[0])
            self.assertIn("z-set", lines[1])

    def test_preflight_reports_all_missing_nested_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "set-a").mkdir()
            requirements = (
                ArtifactRequirement("set-a", "checkpoints/final.bin", "file", "trainer"),
                ArtifactRequirement("set-a", "logs/final", "directory", "qualifier"),
            )
            with self.assertRaises(ArtifactContextError) as raised:
                ArtifactContext.live(root).preflight(requirements)
            rendered = str(raised.exception)
            self.assertIn("checkpoints/final.bin", rendered)
            self.assertIn("logs/final", rendered)

    def test_requirement_rejects_absolute_parent_or_empty_relative_path(self) -> None:
        constructors = (ArtifactRequirement, RoleRequirement)
        for constructor in constructors:
            for relative in ("", "/absolute", "../parent", "nested/../../parent"):
                with self.subTest(constructor=constructor.__name__, relative=relative), \
                        self.assertRaises(ArtifactContextError):
                    constructor("safe-name", relative, "file", "consumer")

    def test_requirement_rejects_ambiguous_lexical_relative_paths(self) -> None:
        ambiguous = (
            "./inputs/x",
            "inputs//x",
            "inputs/./x",
            "inputs/x/",
            "inputs\\x",
        )
        for constructor in (ArtifactRequirement, RoleRequirement):
            for relative in ambiguous:
                with self.subTest(constructor=constructor.__name__, relative=relative), \
                        self.assertRaises(ArtifactContextError):
                    constructor("safe-name", relative, "file", "consumer")

    def test_exact_dot_resolves_file_role_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            manifest = self.load_valid_manifest(root)
            requirement = RoleRequirement(
                "recovery-v1-executable", ".", "file", "recovery",
            )
            manifest.preflight((requirement,))
            self.assertEqual(
                manifest.resolve(requirement),
                root / "inputs/recovery-v1-executable",
            )

    def test_exact_dot_resolves_directory_role_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            manifest = self.load_valid_manifest(root)
            requirement = RoleRequirement(
                "training-artifacts", ".", "directory", "trainer",
            )
            manifest.preflight((requirement,))
            self.assertEqual(
                manifest.resolve(requirement),
                root / "inputs/training-artifacts",
            )

    def test_exact_dot_resolves_artifact_set_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            artifact_set = root / "set-a"
            artifact_set.mkdir()
            context = ArtifactContext.live(root)
            requirement = ArtifactRequirement(
                "set-a", ".", "directory", "consumer",
            )
            context.preflight((requirement,))
            self.assertEqual(context.resolve(requirement), artifact_set)

    def test_role_requirement_preflights_nested_checkpoint_and_log_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            manifest = self.load_valid_manifest(root)
            checkpoint = root / "inputs/training-artifacts/checkpoints/final.bin"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"pinned checkpoint\n")
            logs = root / "inputs/training-artifacts/logs/final"
            logs.mkdir(parents=True)
            requirements = (
                RoleRequirement(
                    "training-artifacts",
                    "checkpoints/final.bin",
                    "file",
                    "trainer",
                    "c2424e650d560d82eb8e9de16b879a26bdf7d2df4ca676a46849a49504ff8095",
                ),
                RoleRequirement("training-artifacts", "logs/final", "directory", "trainer"),
            )
            manifest.preflight(requirements)
            self.assertEqual(manifest.resolve(requirements[0]), checkpoint)
            self.assertEqual(manifest.resolve(requirements[1]), logs)

    def test_tool_requirement_checks_presence_kind_and_optional_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            good = root / "good-tool"
            good.write_bytes(b"#!/bin/sh\nexit 0\n")
            good.chmod(0o755)
            wrong_digest = root / "wrong-digest"
            wrong_digest.write_bytes(b"#!/bin/sh\nexit 1\n")
            wrong_digest.chmod(0o755)
            directory = root / "directory"
            directory.mkdir()
            no_execute = root / "no-execute"
            no_execute.write_text("not executable\n", encoding="utf-8")
            requirements = (
                ToolRequirement(
                    "good", good,
                    "306c6ca7407560340797866e077e053627ad409277d1b9da58106fce4cf717cb",
                ),
            )
            preflight_tools(requirements)
            with self.assertRaises(ArtifactContextError) as raised:
                preflight_tools((
                    ToolRequirement("missing", root / "missing"),
                    ToolRequirement("directory", directory),
                    ToolRequirement("no-execute", no_execute),
                    ToolRequirement("wrong-digest", wrong_digest, "0" * 64),
                    ToolRequirement("relative", pathlib.Path("relative-tool")),
                ))
            rendered = str(raised.exception)
            for name in ("missing", "directory", "no-execute", "wrong-digest", "relative"):
                self.assertIn(name, rendered)

    def test_preflight_rejects_symlinked_base_or_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = pathlib.Path(temporary)
            real_base = temporary_root / "real-base"
            (real_base / "artifact-root/set-a/nested").mkdir(parents=True)
            linked_base = temporary_root / "linked-base"
            linked_base.symlink_to(real_base, target_is_directory=True)
            linked_root = linked_base / "artifact-root"
            requirement = ArtifactRequirement("set-a", "nested", "directory", "consumer")
            with self.assertRaisesRegex(ArtifactContextError, "symlink"):
                ArtifactContext.live(linked_root).preflight((requirement,))

            plain_root = temporary_root / "plain-root"
            plain_root.mkdir()
            (plain_root / "real-set/nested").mkdir(parents=True)
            (plain_root / "set-a").symlink_to(plain_root / "real-set", target_is_directory=True)
            with self.assertRaisesRegex(ArtifactContextError, "symlink"):
                ArtifactContext.live(plain_root).preflight((requirement,))

    def test_live_input_manifest_rejects_unknown_duplicate_relative_or_escaping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            roles = {role: f"inputs/{role}" for role in (*DIRECTORY_ROLES, *FROZEN_FILE_DIGESTS)}
            roles["unknown-role"] = "inputs/unknown"
            roles["training-artifacts"] = "../outside"
            roles["qualification-artifacts"] = str(root.parent / "outside")
            self.make_live_inputs(root, roles=roles)
            with self.assertRaises(ArtifactContextError) as raised:
                LiveInputManifest.load(root)
            rendered = str(raised.exception)
            self.assertIn("unknown-role", rendered)
            self.assertIn("../outside", rendered)
            self.assertIn(str(root.parent / "outside"), rendered)

            duplicate = (
                '{"schema_version":"openttd-rl-v2-live-inputs-1","roles":{'
                '"recovery-v1-artifacts":"one","recovery-v1-artifacts":"two"}}'
            )
            self.make_live_inputs(root, raw=duplicate)
            with self.assertRaisesRegex(ArtifactContextError, "duplicate JSON key"):
                LiveInputManifest.load(root)

    def test_live_input_manifest_reports_every_missing_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_live_inputs(root, roles={})
            with self.assertRaises(ArtifactContextError) as raised:
                LiveInputManifest.load(root)
            rendered = str(raised.exception)
            expected = sorted((*DIRECTORY_ROLES, *FROZEN_FILE_DIGESTS))
            positions = [rendered.index(role) for role in expected]
            self.assertEqual(positions, sorted(positions))

    def test_live_input_manifest_rejects_ambiguous_lexical_role_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_live_inputs(root)
            original = json.loads(
                (root / "v2-live-inputs.json").read_text(encoding="utf-8")
            )["roles"]
            ambiguous = (
                "./inputs/training-artifacts",
                "inputs//training-artifacts",
                "inputs/./training-artifacts",
                "inputs/training-artifacts/",
                "inputs\\training-artifacts",
                str(root),
                f"//{str(root).lstrip('/')}/inputs/training-artifacts",
                f"{root}//inputs/training-artifacts",
                f"{root}/inputs/./training-artifacts",
                f"{root}/inputs/training-artifacts/",
            )

            def frozen_digest(path: pathlib.Path) -> str:
                return FROZEN_FILE_DIGESTS[path.name]

            for value in ambiguous:
                with self.subTest(value=value):
                    roles = dict(original)
                    roles["training-artifacts"] = value
                    self.make_live_inputs(root, roles=roles)
                    with mock.patch.object(
                        artifact_context, "_sha256_file", side_effect=frozen_digest,
                    ), self.assertRaises(ArtifactContextError):
                        LiveInputManifest.load(root)

    def test_live_input_manifest_exposes_role_names_without_raw_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.load_valid_manifest(pathlib.Path(temporary))
            self.assertEqual(
                manifest.roles,
                frozenset((*DIRECTORY_ROLES, *FROZEN_FILE_DIGESTS)),
            )
            self.assertTrue(all(isinstance(role, str) for role in manifest.roles))

    def test_live_input_manifest_rejects_each_wrong_frozen_executable_or_corpus_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_live_inputs(root)
            with self.assertRaises(ArtifactContextError) as raised:
                LiveInputManifest.load(root)
            rendered = str(raised.exception)
            for role, digest in FROZEN_FILE_DIGESTS.items():
                with self.subTest(role=role):
                    self.assertIn(role, rendered)
                    self.assertIn(digest, rendered)

    def test_recovery_v1_and_v2_roles_cannot_alias_incompatible_binaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            self.make_live_inputs(root)
            payload = json.loads((root / "v2-live-inputs.json").read_text(encoding="utf-8"))
            payload["roles"]["v2-campaign-executable"] = payload["roles"]["recovery-v1-executable"]
            self.make_live_inputs(root, roles=payload["roles"])
            with self.assertRaisesRegex(
                ArtifactContextError,
                "recovery-v1-executable.*v2-campaign-executable|v2-campaign-executable.*recovery-v1-executable",
            ):
                LiveInputManifest.load(root)

    def test_named_live_input_cannot_be_read_in_offline_mode(self) -> None:
        requirement = RoleRequirement("training-artifacts", "model.bin", "file", "trainer")
        manifest = LiveInputManifest.offline()
        with self.assertRaisesRegex(
            ArtifactContextError,
            "^offline validation attempted live artifact access$",
        ):
            manifest.resolve(requirement)
        with self.assertRaisesRegex(
            ArtifactContextError,
            "^offline validation attempted live artifact access$",
        ):
            _ = manifest.roles


if __name__ == "__main__":
    unittest.main()
