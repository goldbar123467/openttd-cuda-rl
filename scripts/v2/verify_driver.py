#!/usr/bin/env python3
"""Run the ordered V2 verification inventory at an explicit cumulative tier."""

from __future__ import annotations

import argparse
import ast
import dataclasses
import enum
import hashlib
import importlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence

from artifact_context import (
    ARTIFACT_ROOT_ENV,
    LIVE_INPUT_ROLE_SPECS,
    LIVE_COMMAND_REGISTRY_SHA256,
    LIVE_PROVIDER_AST_SHA256,
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    ToolRequirement,
    preflight_tools,
    resolve_artifact_root,
)
from source_context import SourceContextError, run_git


OPENTTD_SUBMODULE = pathlib.Path("openttd-upstream")
OPENTTD_PIN = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
BWRAP_SHA256 = "52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712"
BWRAP_RECORDS = (
    pathlib.Path("config/v2/m22-final-evaluation-evidence.json"),
    pathlib.Path("config/v2/m22-followup-evaluation-evidence.json"),
    pathlib.Path("config/v2/m22-followup-v2-evaluation-evidence.json"),
)
VALIDATION_MODE_ENV = "OPENTTD_RL_VALIDATION_MODE"
SCRUBBED_V1_LIVE_ENV = frozenset({
    "M07_TRAINER_EXECUTABLE",
    "M07_LIVE_MANIFEST",
    "M07_RECOVERY_REPORT",
    "M08_CUDA_REPORT",
    "M08_CPU_SMOKE_REPORT",
    "M08_CUDA_SMOKE_REPORT",
    "M08_LIVE_MANIFEST",
})
_COMMIT = re.compile(r"[0-9a-f]{40}")
FAST_UNIT_MODULES = (
    "tests.project.v2.test_v2_artifact_context",
    "tests.project.v2.test_v2_m22_native_corpus_binary",
    "tests.project.v2.test_v2_source_context",
    "tests.project.v2.test_v2_verify_driver",
)
CONTRACT_UNIT_MODULES = (
    "tests.project.v2.test_v2_ai_package_acquisition",
    "tests.project.v2.test_v2_ai_runtime_qualification",
    "tests.project.v2.test_v2_competition_manifest",
    "tests.project.v2.test_v2_m15_action_contract",
    "tests.project.v2.test_v2_m15_action_evidence",
    "tests.project.v2.test_v2_m15_action_source",
    "tests.project.v2.test_v2_m15_competence_evidence",
    "tests.project.v2.test_v2_m15_competence_source",
    "tests.project.v2.test_v2_m15_cross_scale_replay_evidence",
    "tests.project.v2.test_v2_m15_episode_evidence",
    "tests.project.v2.test_v2_m15_episode_source",
    "tests.project.v2.test_v2_m15_map_qualification",
    "tests.project.v2.test_v2_m15_native_reset",
    "tests.project.v2.test_v2_m15_native_reset_matrix",
    "tests.project.v2.test_v2_m15_native_source",
    "tests.project.v2.test_v2_m15_observation_contract",
    "tests.project.v2.test_v2_m15_observation_evidence",
    "tests.project.v2.test_v2_m15_observation_source",
    "tests.project.v2.test_v2_m15_policy_contract",
    "tests.project.v2.test_v2_m15_policy_evidence",
    "tests.project.v2.test_v2_m15_scalable_contract",
    "tests.project.v2.test_v2_m16_cargo_evidence",
    "tests.project.v2.test_v2_m16_cargo_source",
    "tests.project.v2.test_v2_m17_rail_evidence",
    "tests.project.v2.test_v2_m17_rail_source",
    "tests.project.v2.test_v2_m18_ship_evidence",
    "tests.project.v2.test_v2_m18_ship_source",
    "tests.project.v2.test_v2_m18_shipai_evidence",
    "tests.project.v2.test_v2_m19_air_evidence",
    "tests.project.v2.test_v2_m19_air_source",
    "tests.project.v2.test_v2_m20_competition_evidence",
    "tests.project.v2.test_v2_m20_competition_source",
    "tests.project.v2.test_v2_m21_broad_evidence",
    "tests.project.v2.test_v2_m21_broad_source",
    "tests.project.v2.test_v2_m22_evaluator",
    "tests.project.v2.test_v2_m22_final_evaluation_source",
    "tests.project.v2.test_v2_m22_final_runtime_preparation",
    "tests.project.v2.test_v2_m22_final_runtime_source",
    "tests.project.v2.test_v2_m22_followup_evaluation_evidence",
    "tests.project.v2.test_v2_m22_followup_evaluation_source",
    "tests.project.v2.test_v2_m22_followup_manifest",
    "tests.project.v2.test_v2_m22_followup_runtime_preparation",
    "tests.project.v2.test_v2_m22_followup_runtime_source",
    "tests.project.v2.test_v2_m22_followup_v2_evaluation_evidence",
    "tests.project.v2.test_v2_m22_followup_v2_evaluation_source",
    "tests.project.v2.test_v2_m22_followup_v2_manifest",
    "tests.project.v2.test_v2_m22_learning_contract",
    "tests.project.v2.test_v2_m22_native_corpus",
    "tests.project.v2.test_v2_m22_qualification",
    "tests.project.v2.test_v2_m22_recovery",
    "tests.project.v2.test_v2_m22_training",
    "tests.project.v2.test_v2_m23_deployment_source",
    "tests.project.v2.test_v2_m23_ingame_source",
    "tests.project.v2.test_v2_m23_packages",
    "tests.project.v2.test_v2_m23_visible_source",
    "tests.project.v2.test_v2_opponent_package_evidence",
    "tests.project.v2.test_v2_opponent_runtime_evidence",
    "tests.project.v2.test_v2_research_baseline",
    "tests.project.v2.test_v2_setting_inventory",
    "tests.project.v2.test_v2_traceability",
)
FULL_UNIT_MODULES = (
    "tests.project.v2.test_v2_m23_release_contract",
)


class Tier(enum.IntEnum):
    FAST = 0
    CONTRACT = 1
    FULL = 2


class CommandCategory(enum.Enum):
    TEST = "test"
    VALIDATOR = "validator"
    BUILDER = "builder"
    REGRESSION = "regression"


class Requirement(enum.Enum):
    OPENTTD_SOURCE = "openttd-source"
    ARTIFACT_ROOT = "artifact-root"
    ARTIFACT_INPUT = "artifact-input"
    LIVE_INPUT_ROLE = "live-input-role"
    TOOL = "tool"
    GIT_INPUT = "git-input"
    LIVE_INPUT_REGISTRY = "live-input-registry"


class FailureKind(enum.Enum):
    UNEXPECTED_STATUS = "unexpected-status"
    SPAWN = "spawn"
    TIMEOUT = "timeout"


@dataclasses.dataclass(frozen=True)
class ArgumentBinding:
    option: str
    source: str
    key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.option, str) or not self.option.startswith("--"):
            raise ValueError("argument binding option must be a long CLI option")
        if self.source not in {
            "artifact-root", "object-repository", "live-role", "tool",
        }:
            raise ValueError(f"unknown argument binding source: {self.source!r}")
        needs_key = self.source in {"live-role", "tool"}
        if needs_key != (self.key is not None):
            raise ValueError(f"argument binding {self.source!r} key declaration is invalid")


LiveRequirement = ArtifactRequirement | RoleRequirement


@dataclasses.dataclass(frozen=True, slots=True)
class GitApplyRequirement:
    logical_set: str
    relative_path: str
    patch_relative_path: str
    consumer: str
    expected_head: str | None = None

    def __post_init__(self) -> None:
        ArtifactRequirement(
            self.logical_set, self.relative_path, "directory", self.consumer,
        )
        ArtifactRequirement(
            "repository-input", self.patch_relative_path, "file", self.consumer,
        )
        if self.expected_head is not None and _COMMIT.fullmatch(self.expected_head) is None:
            raise ValueError("Git apply expected HEAD must be 40 lowercase hexadecimal characters")


@dataclasses.dataclass(frozen=True)
class CommandSpec:
    command_id: str
    minimum_tier: Tier
    category: CommandCategory
    argv: tuple[str, ...]
    expected_status: int = 0
    environment: tuple[tuple[str, str], ...] = ()
    requirements: frozenset[Requirement] = frozenset()
    timeout_seconds: float | None = None
    live_inputs: tuple[LiveRequirement, ...] = ()
    live_input_module: str | None = None
    live_input_root: pathlib.Path | None = None
    live_input_arguments: tuple[object, ...] = ()
    include_live_roles: bool = False
    git_apply_inputs: tuple[GitApplyRequirement, ...] = ()
    registry_sha256: str | None = None
    argument_bindings: tuple[ArgumentBinding, ...] = ()
    cumulative_tests: bool = False


@dataclasses.dataclass(frozen=True)
class VerificationConfig:
    repository_root: pathlib.Path
    tools_python: pathlib.Path
    tier: Tier = Tier.FULL
    artifact_root: pathlib.Path | None = None
    object_repository: pathlib.Path | None = None
    live_inputs: LiveInputManifest | None = None
    tools: tuple[ToolRequirement, ...] = ()

    def tool_path(self, name: str) -> pathlib.Path:
        matches = [requirement.path for requirement in self.tools if requirement.name == name]
        if len(matches) != 1:
            raise ValueError(f"verification tool is not configured exactly once: {name}")
        return matches[0]


@dataclasses.dataclass(frozen=True)
class PreflightIssue:
    requirement: Requirement
    detail: str


@dataclasses.dataclass(frozen=True)
class CommandResult:
    command: CommandSpec
    actual_status: int | None
    stdout: str
    stderr: str
    failure_kind: FailureKind | None = None
    detail: str | None = None

    @property
    def passed(self) -> bool:
        return self.failure_kind is None and self.actual_status == self.command.expected_status


@dataclasses.dataclass(frozen=True)
class VerificationSummary:
    config: VerificationConfig
    preflight_issues: tuple[PreflightIssue, ...]
    results: tuple[CommandResult, ...]

    @property
    def passed(self) -> bool:
        return not self.preflight_issues and all(result.passed for result in self.results)


def parse_tier(value: str) -> Tier:
    tiers = {"fast": Tier.FAST, "contract": Tier.CONTRACT, "full": Tier.FULL}
    try:
        return tiers[value]
    except KeyError as exc:
        raise argparse.ArgumentTypeError("tier must be one of: fast, contract, full") from exc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--tools-python", type=pathlib.Path, required=True)
    parser.add_argument("--tier", type=parse_tier, default=Tier.FULL)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    return parser.parse_args(argv)


def _canonical_python_path(value: pathlib.Path | str) -> pathlib.Path:
    """Canonicalize Python once; Python is always invoked by this exact argv path.

    Git and Bubblewrap deliberately retain their lexical paths so tool preflight
    can reject symlink traversal. Python has a separate policy because its
    canonical path is the immutable interpreter argv for every Python command.
    """

    supplied = pathlib.Path(value)
    if not supplied.is_absolute() or not supplied.is_file() or not os.access(supplied, os.X_OK):
        raise ValueError("tools Python must be an executable absolute path")
    canonical = supplied.resolve()
    if not canonical.is_file() or not os.access(canonical, os.X_OK):
        raise ValueError("canonical tools Python must be an executable file")
    return canonical


def resolve_config(
    args: argparse.Namespace,
    environ: Mapping[str, str] = os.environ,
) -> VerificationConfig:
    tools_python = _canonical_python_path(args.tools_python)

    artifact_root = None
    if args.tier is Tier.FULL:
        try:
            artifact_root = resolve_artifact_root(args.artifact_root, environ)
        except ArtifactContextError as exc:
            raise ValueError(str(exc)) from exc

    root = pathlib.Path(args.root).resolve()
    tool_names = ["python"]
    tools = [ToolRequirement("python", tools_python)]
    if args.tier >= Tier.CONTRACT:
        tool_names.append("git")
    if args.tier is Tier.FULL:
        tool_names.append("bwrap")
    for name in tool_names[1:]:
        found = shutil.which(name, path=environ.get("PATH"))
        path = pathlib.Path(found) if found else pathlib.Path(f"/missing/{name}")
        tools.append(ToolRequirement(name, path))

    return VerificationConfig(
        repository_root=root,
        tools_python=tools_python,
        tier=args.tier,
        artifact_root=artifact_root,
        object_repository=root / OPENTTD_SUBMODULE,
        tools=tuple(tools),
    )


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    """Return the exact retained source directories read only by full unit tests."""

    pathlib.Path(root).resolve()
    return (
        ArtifactRequirement(
            "v2-m22-followup-runtime-a", "source", "directory",
            "m23-source-integrated-patch-test",
        ),
        ArtifactRequirement(
            "v2-m23-visible-runtime-baseline-a", ".", "directory",
            "m23-visible-playback-patch-test",
        ),
    )


def required_git_inputs(root: pathlib.Path) -> tuple[GitApplyRequirement, ...]:
    """Return the two exact M23 Git apply boundaries used by cumulative tests."""

    root = pathlib.Path(root).resolve()
    try:
        authority = json.loads(
            (root / "config/v2/m22-followup-runtime-source.json").read_text(
                encoding="utf-8"
            )
        )
        expected_head = authority["repository"]["commit"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"M23 source Git authority is unavailable or malformed: {exc}") from exc
    if not isinstance(expected_head, str) or _COMMIT.fullmatch(expected_head) is None:
        raise ValueError("M23 source Git authority commit is malformed")
    return (
        GitApplyRequirement(
            "v2-m22-followup-runtime-a",
            "source",
            "integration/openttd/patches/15.3/m23/"
            "0001-Add-M23-source-integrated-ONNX-runtime.patch",
            "m23-source-integrated-patch-test",
            expected_head,
        ),
        GitApplyRequirement(
            "v2-m23-visible-runtime-baseline-a",
            ".",
            "integration/openttd/patches/15.3/m23/"
            "0002-Add-M23-visible-normal-game-controller-foundation.patch",
            "m23-visible-playback-patch-test",
        ),
    )


def _provider_live_inputs(
    module_name: str,
    root: pathlib.Path,
    arguments: tuple[object, ...] = (),
    *,
    include_roles: bool = False,
) -> tuple[LiveRequirement, ...]:
    module = importlib.import_module(module_name)
    provider = getattr(module, "required_live_inputs")
    values = tuple(provider(root, *arguments))
    if include_roles:
        values = (*values, *tuple(module.required_live_roles(root)))
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate live-input requirement in {module_name}")
    return values


def _registry_value(value: object, root: pathlib.Path) -> object:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _registry_value(getattr(value, field.name), root)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, pathlib.Path):
        try:
            relative = value.relative_to(root)
        except ValueError:
            return value.as_posix()
        return f"<root>/{relative.as_posix()}" if relative.parts else "<root>"
    if isinstance(value, (tuple, list, frozenset, set)):
        items = [_registry_value(item, root) for item in value]
        if isinstance(value, (frozenset, set)):
            items.sort(key=lambda item: json.dumps(item, sort_keys=True))
        return items
    if isinstance(value, dict):
        return {
            str(key): _registry_value(item, root)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    return value


def _command_registry_sha256(command: CommandSpec) -> str:
    if command.live_input_root is None:
        raise ValueError(f"registered command has no provider root: {command.command_id}")
    root = command.live_input_root
    argv = tuple(command.argv)
    if argv:
        argv = ("<tools-python>", *argv[1:])
    payload = {
        "command_id": command.command_id,
        "minimum_tier": command.minimum_tier,
        "category": command.category,
        "argv": argv,
        "expected_status": command.expected_status,
        "environment": command.environment,
        "requirements": command.requirements,
        "timeout_seconds": command.timeout_seconds,
        "live_inputs": command.live_inputs,
        "live_input_module": command.live_input_module,
        "live_input_root": root,
        "live_input_arguments": command.live_input_arguments,
        "include_live_roles": command.include_live_roles,
        "git_apply_inputs": command.git_apply_inputs,
        "argument_bindings": command.argument_bindings,
        "cumulative_tests": command.cumulative_tests,
    }
    encoded = json.dumps(
        _registry_value(payload, root),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_ast_sha256(module_name: str) -> str:
    module = importlib.import_module(module_name)
    source_path = pathlib.Path(module.__file__ or "")
    try:
        source = source_path.read_text(encoding="utf-8")
        normalized = ast.dump(ast.parse(source), include_attributes=False)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError(f"cannot fingerprint live-input provider {module_name}: {exc}") from exc
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_inventory(
    repository_root: pathlib.Path,
    tools_python: pathlib.Path,
) -> tuple[CommandSpec, ...]:
    root = pathlib.Path(repository_root).resolve()
    python = str(pathlib.Path(tools_python))
    scripts = root / "scripts/v2"
    pythonpath = (("PYTHONPATH", str(scripts)),)
    source_requirement = frozenset({Requirement.OPENTTD_SOURCE})
    source_binding = (ArgumentBinding("--object-repo", "object-repository"),)
    artifact_binding = (ArgumentBinding("--artifact-root", "artifact-root"),)
    m14_bindings = (
        *artifact_binding,
        ArgumentBinding("--openttd", "live-role", "m14-openttd-executable"),
    )
    evaluation_bindings = (
        *artifact_binding,
        ArgumentBinding("--evaluator", "live-role", "final-v1-evaluator"),
        ArgumentBinding("--bwrap", "tool", "bwrap"),
    )

    def command(
        command_id: str,
        script: str,
        *,
        minimum_tier: Tier = Tier.CONTRACT,
        category: CommandCategory = CommandCategory.VALIDATOR,
        arguments: tuple[str, ...] = (),
        requirements: frozenset[Requirement] = frozenset(),
        expected_status: int = 0,
        live_input_module: str | None = None,
        live_input_arguments: tuple[object, ...] = (),
        include_live_roles: bool = False,
        argument_bindings: tuple[ArgumentBinding, ...] = (),
    ) -> CommandSpec:
        live_inputs = () if live_input_module is None else _provider_live_inputs(
            live_input_module,
            root,
            live_input_arguments,
            include_roles=include_live_roles,
        )
        declared_roles = {
            (item.role, item.relative_path)
            for item in live_inputs
            if isinstance(item, RoleRequirement)
        }
        for binding in argument_bindings:
            if binding.source != "live-role" or (binding.key, ".") in declared_roles:
                continue
            assert binding.key is not None
            spec = LIVE_INPUT_ROLE_SPECS[binding.key]
            live_inputs = (*live_inputs, RoleRequirement(
                binding.key,
                ".",
                spec.kind,
                command_id,
                spec.expected_sha256,
            ))
        return CommandSpec(
            command_id=command_id,
            minimum_tier=minimum_tier,
            category=category,
            argv=(python, str(scripts / script), "--root", str(root), *arguments),
            expected_status=expected_status,
            environment=pythonpath,
            requirements=requirements,
            live_inputs=live_inputs,
            live_input_module=live_input_module,
            live_input_root=root if live_input_module is not None else None,
            live_input_arguments=live_input_arguments,
            include_live_roles=include_live_roles,
            argument_bindings=argument_bindings,
        )

    def artifact_command(
        command_id: str,
        script: str,
        *,
        module: str | None = None,
        bindings: tuple[ArgumentBinding, ...] = artifact_binding,
        include_roles: bool = False,
        arguments: tuple[str, ...] = (),
        live_input_arguments: tuple[object, ...] = (),
        expected_status: int = 0,
    ) -> CommandSpec:
        selected = module or pathlib.Path(script).stem
        return command(
            command_id,
            script,
            arguments=arguments,
            expected_status=expected_status,
            live_input_module=selected,
            live_input_arguments=live_input_arguments,
            include_live_roles=include_roles,
            argument_bindings=bindings,
        )

    recovery_v1 = root / "config/v2/m22-recovery-evidence.json"
    recovery_v2 = root / "config/v2/m22-recovery-evidence-v2.json"
    inventory = (
        command(
            "research-baseline", "validate_research_baseline.py",
            requirements=source_requirement, argument_bindings=source_binding,
        ),
        command(
            "setting-inventory", "validate_setting_inventory.py",
            requirements=source_requirement, argument_bindings=source_binding,
        ),
        artifact_command(
            "opponent-package-evidence", "validate_opponent_package_evidence.py",
            bindings=m14_bindings, include_roles=True,
        ),
        artifact_command(
            "opponent-runtime-evidence", "validate_opponent_runtime_evidence.py",
            bindings=m14_bindings, include_roles=True,
        ),
        command("competition-manifest", "validate_competition_manifest.py"),
        command("m15-scalable-contract", "validate_m15_scalable_contract.py"),
        command("m15-policy-contract", "validate_m15_policy_contract.py"),
        artifact_command("m15-policy-evidence", "validate_m15_policy_evidence.py"),
        artifact_command(
            "m15-map-matrix", "validate_m15_map_evidence.py", bindings=m14_bindings,
        ),
        artifact_command("m15-native-source", "validate_m15_native_source.py"),
        artifact_command("m15-native-reset-evidence", "validate_m15_native_reset_evidence.py"),
        artifact_command("m15-native-reset-matrix", "validate_m15_native_reset_matrix.py"),
        command("m15-observation-contract", "validate_m15_observation_contract.py"),
        artifact_command("m15-observation-source", "validate_m15_observation_source.py"),
        artifact_command("m15-observation-evidence", "validate_m15_observation_evidence.py"),
        command("m15-action-contract", "validate_m15_action_contract.py"),
        artifact_command("m15-action-source", "validate_m15_action_source.py"),
        artifact_command("m15-action-evidence", "validate_m15_action_evidence.py"),
        artifact_command("m15-episode-source", "validate_m15_episode_source.py"),
        artifact_command("m15-episode-evidence", "validate_m15_episode_evidence.py"),
        artifact_command(
            "m15-cross-scale-replay-evidence",
            "validate_m15_cross_scale_replay_evidence.py",
        ),
        artifact_command("m15-competence-source", "validate_m15_competence_source.py"),
        artifact_command("m15-competence-evidence", "validate_m15_competence_evidence.py"),
        artifact_command("m16-cargo-source", "validate_m16_cargo_source.py"),
        artifact_command("m16-cargo-evidence", "validate_m16_cargo_evidence.py"),
        artifact_command("m17-rail-source", "validate_m17_rail_source.py"),
        artifact_command("m17-rail-evidence", "validate_m17_rail_evidence.py"),
        artifact_command("m18-ship-source", "validate_m18_ship_source.py"),
        artifact_command(
            "m18-shipai-evidence", "validate_m18_shipai_evidence.py",
            bindings=m14_bindings, include_roles=True,
        ),
        artifact_command("m18-ship-evidence", "validate_m18_ship_evidence.py"),
        artifact_command("m19-air-source", "validate_m19_air_source.py"),
        artifact_command("m19-air-evidence", "validate_m19_air_evidence.py"),
        artifact_command("m20-competition-source", "validate_m20_competition_source.py"),
        artifact_command("m20-competition-evidence", "validate_m20_competition_evidence.py"),
        artifact_command("m21-broad-source", "validate_m21_broad_source.py"),
        artifact_command("m21-broad-evidence", "validate_m21_broad_evidence.py"),
        command("m22-learning-contract", "validate_m22_learning_contract.py"),
        command("m22-native-corpus", "validate_m22_native_corpus.py"),
        CommandSpec(
            command_id="m22-corpus-binary",
            minimum_tier=Tier.FAST,
            category=CommandCategory.TEST,
            argv=(
                python,
                "-c",
                "import pathlib,sys; import encode_m22_native_corpus as e; "
                "root=pathlib.Path(sys.argv[1]); data=e.encode(root); decoded=e.decode(data); "
                "print(f'V2_M22_CORPUS_BINARY=PASS entries={len(decoded.entries)} bytes={len(data)}')",
                str(root),
            ),
            environment=pythonpath,
        ),
        artifact_command(
            "m22-recovery-v1-evidence", "validate_m22_recovery_evidence.py",
            arguments=("--report", str(recovery_v1)),
            live_input_arguments=(recovery_v1,),
            bindings=(
                ArgumentBinding("--artifact-root", "live-role", "recovery-v1-artifacts"),
                ArgumentBinding("--executable", "live-role", "recovery-v1-executable"),
                ArgumentBinding("--corpus", "live-role", "recovery-v1-corpus"),
            ),
        ),
        artifact_command(
            "m22-recovery-v2-evidence", "validate_m22_recovery_evidence.py",
            arguments=("--report", str(recovery_v2)),
            live_input_arguments=(recovery_v2,),
            bindings=(
                ArgumentBinding("--artifact-root", "live-role", "recovery-v2-artifacts"),
                ArgumentBinding("--executable", "live-role", "v2-campaign-executable"),
                ArgumentBinding("--corpus", "live-role", "v2-corpus-binary"),
            ),
        ),
        artifact_command(
            "m22-training-evidence", "validate_m22_training_evidence.py",
            arguments=("--report", str(root / "config/v2/m22-training-evidence.json")),
            bindings=(
                ArgumentBinding("--artifact-root", "live-role", "training-artifacts"),
                ArgumentBinding("--executable", "live-role", "v2-campaign-executable"),
                ArgumentBinding("--corpus", "live-role", "v2-corpus-binary"),
            ),
        ),
        artifact_command(
            "m22-qualification-evidence", "validate_m22_qualification_evidence.py",
            arguments=("--report", str(root / "config/v2/m22-qualification-evidence.json")),
            bindings=(
                ArgumentBinding("--artifact-root", "live-role", "qualification-artifacts"),
                ArgumentBinding("--training-artifact-root", "live-role", "training-artifacts"),
                ArgumentBinding("--executable", "live-role", "qualification-executable"),
                ArgumentBinding("--corpus", "live-role", "v2-corpus-binary"),
            ),
        ),
        artifact_command("m22-final-runtime-source", "validate_m22_final_runtime_source.py"),
        artifact_command("m22-followup-runtime-source", "validate_m22_followup_runtime_source.py"),
        artifact_command(
            "m22-final-v1-evaluation", "validate_m22_final_evaluation.py",
            bindings=evaluation_bindings, expected_status=2,
        ),
        command(
            "m22-followup-v1-manifest-build", "build_m22_followup_manifest.py",
            category=CommandCategory.BUILDER,
        ),
        command("m22-followup-v1-manifest", "validate_m22_followup_manifest.py"),
        artifact_command(
            "m22-followup-v1-evaluation", "validate_m22_followup_evaluation.py",
            bindings=evaluation_bindings, expected_status=2,
        ),
        command(
            "m22-followup-v2-manifest-build", "build_m22_followup_v2_manifest.py",
            category=CommandCategory.BUILDER,
        ),
        command("m22-followup-v2-manifest", "validate_m22_followup_v2_manifest.py"),
        artifact_command(
            "m22-followup-v2-evaluation", "validate_m22_followup_v2_evaluation.py",
            bindings=evaluation_bindings,
        ),
        command(
            "m23-contract", "validate_m23_release_contract.py",
            minimum_tier=Tier.FULL,
        ),
        command("v2-traceability", "validate_traceability.py"),
        CommandSpec(
            command_id="v2-fast-unit-tests",
            minimum_tier=Tier.FAST,
            category=CommandCategory.TEST,
            argv=(
                python,
                "-m",
                "unittest",
                *FAST_UNIT_MODULES,
            ),
            environment=pythonpath,
            cumulative_tests=True,
        ),
        CommandSpec(
            command_id="v2-unit-tests",
            minimum_tier=Tier.CONTRACT,
            category=CommandCategory.TEST,
            argv=(
                python,
                "-m",
                "unittest",
                *CONTRACT_UNIT_MODULES,
            ),
            environment=pythonpath,
            live_inputs=required_live_inputs(root),
            live_input_module="verify_driver",
            live_input_root=root,
            git_apply_inputs=required_git_inputs(root),
            cumulative_tests=True,
        ),
        CommandSpec(
            command_id="v2-full-unit-tests",
            minimum_tier=Tier.FULL,
            category=CommandCategory.TEST,
            argv=(
                python,
                "-m",
                "unittest",
                *FULL_UNIT_MODULES,
            ),
            environment=pythonpath,
            cumulative_tests=True,
        ),
        CommandSpec(
            command_id="v1-traceability",
            minimum_tier=Tier.FULL,
            category=CommandCategory.REGRESSION,
            argv=(str(root / "scripts/v1/traceability.sh"), "--tools-python", python),
            requirements=source_requirement,
        ),
    )
    return tuple(
        dataclasses.replace(command, registry_sha256=_command_registry_sha256(command))
        if command.live_input_module is not None else command
        for command in inventory
    )


def select_commands(
    inventory: Sequence[CommandSpec],
    tier: Tier,
) -> tuple[CommandSpec, ...]:
    return tuple(command for command in inventory if command.minimum_tier <= tier)


def _git(
    git: pathlib.Path,
    repository_root: pathlib.Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    return subprocess.run(
        (str(git), "--no-replace-objects", "-C", str(repository_root), *arguments),
        cwd=repository_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _openttd_source_issue(config: VerificationConfig) -> PreflightIssue | None:
    repository_root = config.repository_root
    source = config.object_repository or repository_root / OPENTTD_SUBMODULE
    try:
        git = config.tool_path("git")
    except ValueError:
        found = shutil.which("git")
        git = pathlib.Path(found) if found else pathlib.Path("/missing/git")
    expected = f"initialized clean OpenTTD submodule at {OPENTTD_PIN}"
    if not source.is_dir() or source.is_symlink() or not (source / ".git").exists():
        return PreflightIssue(Requirement.OPENTTD_SOURCE, f"missing {expected}: {source}")

    try:
        index = _git(
            git, repository_root,
            "ls-files", "--stage", "--", OPENTTD_SUBMODULE.as_posix(),
        )
    except OSError as exc:
        return PreflightIssue(
            Requirement.OPENTTD_SOURCE,
            f"cannot inspect {expected} with {git}: {exc}",
        )
    expected_index = f"160000 {OPENTTD_PIN} 0\t{OPENTTD_SUBMODULE.as_posix()}"
    if index.returncode != 0 or index.stdout.strip() != expected_index:
        return PreflightIssue(Requirement.OPENTTD_SOURCE, f"outer gitlink is not the {expected}")

    try:
        top = _git(git, source, "rev-parse", "--show-toplevel")
        head = _git(git, source, "rev-parse", "HEAD")
        status = _git(git, source, "status", "--porcelain", "--untracked-files=all")
    except OSError as exc:
        return PreflightIssue(
            Requirement.OPENTTD_SOURCE,
            f"cannot inspect {expected} with {git}: {exc}",
        )
    if (
        top.returncode != 0
        or pathlib.Path(top.stdout.strip()).resolve() != source.resolve()
        or head.returncode != 0
        or head.stdout.strip() != OPENTTD_PIN
        or status.returncode != 0
        or status.stdout
    ):
        return PreflightIssue(Requirement.OPENTTD_SOURCE, f"submodule is not the {expected}: {source}")
    return None


def _artifact_root_issue(artifact_root: pathlib.Path | None) -> PreflightIssue | None:
    if artifact_root is None:
        return PreflightIssue(Requirement.ARTIFACT_ROOT, "full verification requires an absolute artifact root")
    has_symlink = any(path.is_symlink() for path in (artifact_root, *artifact_root.parents))
    if not artifact_root.is_absolute() or has_symlink or not artifact_root.is_dir():
        return PreflightIssue(
            Requirement.ARTIFACT_ROOT,
            f"artifact root must be an existing nonsymlink directory: {artifact_root}",
        )
    return None


def validate_live_input_registry(
    commands: Sequence[CommandSpec],
) -> tuple[PreflightIssue, ...]:
    issues: list[PreflightIssue] = []
    registered_ids = {
        command.command_id for command in commands
        if command.live_input_module is not None
    }
    if registered_ids and LIVE_COMMAND_REGISTRY_SHA256:
        missing = sorted(set(LIVE_COMMAND_REGISTRY_SHA256) - registered_ids)
        extra = sorted(registered_ids - set(LIVE_COMMAND_REGISTRY_SHA256))
        if missing or extra:
            issues.append(PreflightIssue(
                Requirement.LIVE_INPUT_REGISTRY,
                f"live-input registry command inventory drifted: missing={missing} extra={extra}",
            ))
    for command in commands:
        has_live_binding = any(
            binding.source in {"artifact-root", "live-role"}
            for binding in command.argument_bindings
        )
        if has_live_binding and (not command.live_inputs or command.live_input_module is None):
            issues.append(PreflightIssue(
                Requirement.LIVE_INPUT_REGISTRY,
                f"artifact-backed command has no complete live-input registry: {command.command_id}",
            ))
            continue
        if command.live_input_module is None:
            continue
        if command.live_input_root is None:
            issues.append(PreflightIssue(
                Requirement.LIVE_INPUT_REGISTRY,
                f"live-input provider root is absent: {command.command_id}",
            ))
            continue
        try:
            observed = list(_provider_live_inputs(
                command.live_input_module,
                command.live_input_root,
                command.live_input_arguments,
                include_roles=command.include_live_roles,
            ))
            declared_roles = {
                (item.role, item.relative_path)
                for item in observed
                if isinstance(item, RoleRequirement)
            }
            for binding in command.argument_bindings:
                if binding.source != "live-role" or (binding.key, ".") in declared_roles:
                    continue
                assert binding.key is not None
                spec = LIVE_INPUT_ROLE_SPECS[binding.key]
                observed.append(RoleRequirement(
                    binding.key,
                    ".",
                    spec.kind,
                    command.command_id,
                    spec.expected_sha256,
                ))
            if tuple(observed) != command.live_inputs:
                issues.append(PreflightIssue(
                    Requirement.LIVE_INPUT_REGISTRY,
                    f"live-input provider snapshot diverged: {command.command_id}",
                ))

            module = importlib.import_module(command.live_input_module)
            git_provider = getattr(module, "required_git_inputs", None)
            observed_git = tuple(git_provider(
                command.live_input_root, *command.live_input_arguments,
            )) if callable(git_provider) else ()
            # When this file is the CLI entrypoint its dataclasses belong to
            # ``__main__`` while the pure provider is imported as
            # ``verify_driver``.  Compare their frozen values, not Python class
            # identity, so the same typed snapshot is stable in both modes.
            if _registry_value(observed_git, command.live_input_root) != _registry_value(
                command.git_apply_inputs, command.live_input_root,
            ):
                issues.append(PreflightIssue(
                    Requirement.LIVE_INPUT_REGISTRY,
                    f"Git live-input provider snapshot diverged: {command.command_id}",
                ))

            actual_fingerprint = _provider_ast_sha256(command.live_input_module)
            expected_fingerprint = LIVE_PROVIDER_AST_SHA256.get(command.live_input_module)
            if expected_fingerprint != actual_fingerprint:
                issues.append(PreflightIssue(
                    Requirement.LIVE_INPUT_REGISTRY,
                    f"live-input provider AST fingerprint drifted: {command.live_input_module}",
                ))
            actual_registry = _command_registry_sha256(command)
            expected_registry = LIVE_COMMAND_REGISTRY_SHA256.get(command.command_id)
            if (
                command.registry_sha256 != actual_registry
                or expected_registry != actual_registry
            ):
                issues.append(PreflightIssue(
                    Requirement.LIVE_INPUT_REGISTRY,
                    f"live-input command snapshot drifted: {command.command_id}",
                ))
        except (AttributeError, ImportError, TypeError, ValueError, ArtifactContextError) as exc:
            issues.append(PreflightIssue(
                Requirement.LIVE_INPUT_REGISTRY,
                f"live-input registry cannot be evaluated for {command.command_id}: {exc}",
            ))
    return tuple(issues)


def _error_issues(requirement: Requirement, error: BaseException) -> list[PreflightIssue]:
    lines = [line for line in str(error).splitlines() if line]
    return [PreflightIssue(requirement, line) for line in lines] or [
        PreflightIssue(requirement, type(error).__name__)
    ]


def _bwrap_record_issues(repository_root: pathlib.Path) -> list[PreflightIssue]:
    digests: list[str] = []
    issues: list[PreflightIssue] = []
    for relative in BWRAP_RECORDS:
        path = repository_root / relative
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            digest = value["identity"]["bubblewrap_sha256"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            issues.append(PreflightIssue(
                Requirement.TOOL,
                f"bubblewrap identity record is unavailable or malformed: {path}: {exc}",
            ))
            continue
        if not isinstance(digest, str):
            issues.append(PreflightIssue(
                Requirement.TOOL,
                f"bubblewrap identity is not a digest: {path}",
            ))
            continue
        digests.append(digest)
    if len(set(digests)) > 1:
        issues.append(PreflightIssue(
            Requirement.TOOL,
            "bubblewrap digests disagree across frozen evaluation records",
        ))
    for digest in sorted(set(digests)):
        if digest != BWRAP_SHA256:
            issues.append(PreflightIssue(
                Requirement.TOOL,
                f"bubblewrap frozen digest mismatch: expected {BWRAP_SHA256}, got {digest}",
            ))
    return issues


def _sorted_live_inputs(commands: Sequence[CommandSpec]) -> tuple[LiveRequirement, ...]:
    values = {item for command in commands for item in command.live_inputs}
    return tuple(sorted(values, key=lambda item: (
        type(item).__name__,
        getattr(item, "logical_set", getattr(item, "role", "")),
        item.relative_path,
        item.kind,
        item.consumer,
        item.expected_sha256 or "",
    )))


def _git_apply_issues(
    config: VerificationConfig,
    commands: Sequence[CommandSpec],
    context: ArtifactContext,
) -> list[PreflightIssue]:
    requirements = tuple(
        requirement
        for command in commands
        for requirement in command.git_apply_inputs
    )
    if not requirements:
        return []
    try:
        git = config.tool_path("git")
    except ValueError as exc:
        return [PreflightIssue(Requirement.GIT_INPUT, str(exc))]

    issues: list[PreflightIssue] = []
    for requirement in requirements:
        source = context.resolve(ArtifactRequirement(
            requirement.logical_set,
            requirement.relative_path,
            "directory",
            requirement.consumer,
        ))
        patch = config.repository_root / requirement.patch_relative_path
        try:
            if requirement.expected_head is not None:
                observed = run_git(
                    "rev-parse", "HEAD", repository=source, git_path=git,
                )
                actual_head = observed.stdout.decode("ascii", errors="replace").strip()
                if observed.returncode != 0 or actual_head != requirement.expected_head:
                    issues.append(PreflightIssue(
                        Requirement.GIT_INPUT,
                        f"Git repository HEAD mismatch for {requirement.consumer}: "
                        f"expected {requirement.expected_head}, got {actual_head or '<unavailable>'}: {source}",
                    ))
            applied = run_git(
                "apply", "--check", "--whitespace=error-all", str(patch),
                repository=source,
                git_path=git,
            )
            if applied.returncode != 0:
                detail = (applied.stderr or applied.stdout).decode(
                    "utf-8", errors="replace"
                ).strip()
                issues.append(PreflightIssue(
                    Requirement.GIT_INPUT,
                    f"Git apply preflight failed for {requirement.consumer} at {source}: "
                    f"{detail or 'git apply --check failed'}",
                ))
        except (SourceContextError, OSError) as exc:
            issues.append(PreflightIssue(
                Requirement.GIT_INPUT,
                f"Git preflight failed for {requirement.consumer} at {source}: {exc}",
            ))
    return issues


def _prepare_preflight(
    config: VerificationConfig,
    commands: Sequence[CommandSpec],
) -> tuple[VerificationConfig, tuple[PreflightIssue, ...]]:
    issues = list(validate_live_input_registry(commands))
    requirements = frozenset(
        requirement for command in commands for requirement in command.requirements
    )
    if Requirement.OPENTTD_SOURCE in requirements:
        issue = _openttd_source_issue(config)
        if issue is not None:
            issues.append(issue)

    tools = list(config.tools)
    uses_bwrap = any(
        binding.source == "tool" and binding.key == "bwrap"
        for command in commands
        for binding in command.argument_bindings
    )
    if config.tier is Tier.FULL and uses_bwrap:
        issues.extend(_bwrap_record_issues(config.repository_root))
        tools = [
            dataclasses.replace(tool, expected_sha256=BWRAP_SHA256)
            if tool.name == "bwrap" else tool
            for tool in tools
        ]
    try:
        preflight_tools(tuple(tools))
    except ArtifactContextError as exc:
        issues.extend(_error_issues(Requirement.TOOL, exc))

    if config.tier is not Tier.FULL:
        return config, tuple(issues)

    root_issue = _artifact_root_issue(config.artifact_root)
    if root_issue is not None:
        issues.append(root_issue)

    live_requirements = _sorted_live_inputs(commands)
    artifacts = tuple(
        item for item in live_requirements if isinstance(item, ArtifactRequirement)
    )
    roles = tuple(item for item in live_requirements if isinstance(item, RoleRequirement))
    prepared = config
    if config.artifact_root is None:
        for item in artifacts:
            issues.append(PreflightIssue(
                Requirement.ARTIFACT_INPUT,
                f"artifact input unavailable without root: {item.logical_set}/{item.relative_path} "
                f"for {item.consumer}",
            ))
        for item in roles:
            issues.append(PreflightIssue(
                Requirement.LIVE_INPUT_ROLE,
                f"live-input role unavailable without root: {item.role}/{item.relative_path} "
                f"for {item.consumer}",
            ))
        return prepared, tuple(issues)

    context = ArtifactContext.live(config.artifact_root)
    if artifacts:
        try:
            context.preflight(artifacts)
        except ArtifactContextError as exc:
            issues.extend(_error_issues(Requirement.ARTIFACT_INPUT, exc))
    issues.extend(_git_apply_issues(config, commands, context))
    if roles:
        try:
            live_inputs = LiveInputManifest.load(config.artifact_root)
        except ArtifactContextError as exc:
            issues.extend(_error_issues(Requirement.LIVE_INPUT_ROLE, exc))
        else:
            prepared = dataclasses.replace(config, live_inputs=live_inputs)
            try:
                live_inputs.preflight(roles)
            except ArtifactContextError as exc:
                issues.extend(_error_issues(Requirement.LIVE_INPUT_ROLE, exc))
    return prepared, tuple(issues)


def preflight(
    config: VerificationConfig,
    commands: Sequence[CommandSpec],
) -> tuple[PreflightIssue, ...]:
    return _prepare_preflight(config, commands)[1]


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def materialize_command(
    command: CommandSpec,
    config: VerificationConfig,
) -> CommandSpec:
    argv = list(command.argv)
    for binding in command.argument_bindings:
        value: pathlib.Path | None = None
        if binding.source == "object-repository" and config.tier >= Tier.CONTRACT:
            value = config.object_repository
        elif binding.source == "artifact-root" and config.tier is Tier.FULL:
            value = config.artifact_root
        elif binding.source == "live-role" and config.tier is Tier.FULL:
            if config.live_inputs is None or binding.key is None:
                raise ValueError(f"live role is not preflighted for {command.command_id}")
            value = config.live_inputs.role_path(binding.key)
        elif binding.source == "tool" and config.tier is Tier.FULL:
            assert binding.key is not None
            value = config.tool_path(binding.key)
        if value is None:
            continue
        argv.extend((binding.option, str(value)))

    environment: dict[str, str] = {}
    git_directories = [
        str(tool.path.parent) for tool in config.tools if tool.name == "git"
    ]
    other_directories = [
        str(tool.path.parent) for tool in config.tools if tool.name != "git"
    ]
    tool_directories = tuple(dict.fromkeys((*git_directories, *other_directories)))
    if tool_directories:
        environment["PATH"] = os.pathsep.join(tool_directories)
    for name in ("LANG", "LC_ALL", "TZ", "TMPDIR"):
        if name in os.environ:
            environment[name] = os.environ[name]
    environment.update(dict(command.environment))
    for name in tuple(environment):
        if name.startswith("GIT_"):
            environment.pop(name)
    environment[VALIDATION_MODE_ENV] = (
        "live" if config.tier is Tier.FULL else "offline"
    )
    if command.cumulative_tests and config.tier is Tier.FULL:
        if config.artifact_root is None:
            raise ValueError("full cumulative tests require a preflighted artifact root")
        environment[ARTIFACT_ROOT_ENV] = str(config.artifact_root)
    else:
        environment.pop(ARTIFACT_ROOT_ENV, None)
    for name in SCRUBBED_V1_LIVE_ENV:
        environment.pop(name, None)
    return dataclasses.replace(
        command,
        argv=tuple(argv),
        environment=tuple(sorted(environment.items())),
    )


def execute_command(command: CommandSpec, config: VerificationConfig) -> CommandResult:
    materialized = materialize_command(command, config)
    kwargs: dict[str, object] = {}
    kwargs["env"] = dict(materialized.environment)
    if materialized.timeout_seconds is not None:
        kwargs["timeout"] = materialized.timeout_seconds
    try:
        completed = subprocess.run(
            materialized.argv,
            cwd=config.repository_root,
            text=True,
            capture_output=True,
            check=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=materialized,
            actual_status=None,
            stdout=_text(exc.stdout),
            stderr=_text(exc.stderr),
            failure_kind=FailureKind.TIMEOUT,
            detail=str(exc),
        )
    except OSError as exc:
        return CommandResult(
            command=materialized,
            actual_status=None,
            stdout="",
            stderr="",
            failure_kind=FailureKind.SPAWN,
            detail=str(exc),
        )

    failure_kind = None
    detail = None
    if completed.returncode != materialized.expected_status:
        failure_kind = FailureKind.UNEXPECTED_STATUS
        detail = f"expected status {materialized.expected_status}, got {completed.returncode}"
    return CommandResult(
        command=materialized,
        actual_status=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        failure_kind=failure_kind,
        detail=detail,
    )


def run_verification(
    config: VerificationConfig,
    inventory: Sequence[CommandSpec] | None = None,
) -> VerificationSummary:
    available = tuple(inventory) if inventory is not None else build_inventory(
        config.repository_root, config.tools_python,
    )
    commands = select_commands(available, config.tier)
    prepared, issues = _prepare_preflight(config, commands)
    if issues:
        return VerificationSummary(config=prepared, preflight_issues=issues, results=())
    results = tuple(execute_command(command, prepared) for command in commands)
    return VerificationSummary(config=prepared, preflight_issues=(), results=results)


def render_summary(summary: VerificationSummary) -> tuple[str, ...]:
    lines = [f"V2_VERIFY_TIER={summary.config.tier.name.lower()}"]
    lines.extend(
        f"V2_VERIFY_PREFLIGHT=FAIL category={issue.requirement.value} detail={issue.detail}"
        for issue in summary.preflight_issues
    )
    for result in summary.results:
        status = "PASS" if result.passed else "FAIL"
        actual = "none" if result.actual_status is None else str(result.actual_status)
        failure = "none" if result.failure_kind is None else result.failure_kind.value
        lines.append(
            f"V2_VERIFY_RESULT={status} command={result.command.command_id} "
            f"category={result.command.category.value} expected={result.command.expected_status} "
            f"actual={actual} failure={failure}"
        )
    passed = sum(result.passed for result in summary.results)
    lines.append(
        f"V2_VERIFY_SUMMARY={'PASS' if summary.passed else 'FAIL'} "
        f"tier={summary.config.tier.name.lower()} commands={len(summary.results)} "
        f"passed={passed} failed={len(summary.results) - passed} "
        f"preflight={len(summary.preflight_issues)}"
    )
    return tuple(lines)


def main(argv: list[str] | None = None) -> int:
    try:
        config = resolve_config(parse_args(list(sys.argv[1:] if argv is None else argv)))
    except ValueError as exc:
        print(f"v2 verify: {exc}", file=sys.stderr)
        return 2

    summary = run_verification(config)
    for result in summary.results:
        if result.stdout:
            sys.stdout.write(result.stdout)
            if not result.stdout.endswith("\n"):
                sys.stdout.write("\n")
        if result.stderr:
            sys.stderr.write(result.stderr)
            if not result.stderr.endswith("\n"):
                sys.stderr.write("\n")
    for line in render_summary(summary):
        print(line)
    if summary.preflight_issues:
        return 2
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
