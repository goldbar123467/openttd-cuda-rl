#!/usr/bin/env python3
"""Run the ordered V2 verification inventory at an explicit cumulative tier."""

from __future__ import annotations

import argparse
import dataclasses
import enum
import os
import pathlib
import subprocess
import sys
from collections.abc import Mapping, Sequence


ARTIFACT_ROOT_ENV = "OPENTTD_RL_ARTIFACT_ROOT"
OPENTTD_SUBMODULE = pathlib.Path("openttd-upstream")
OPENTTD_PIN = "29f808ef0022064e6d9a83c8476d1e0f4686af86"


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


class FailureKind(enum.Enum):
    UNEXPECTED_STATUS = "unexpected-status"
    SPAWN = "spawn"
    TIMEOUT = "timeout"


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


@dataclasses.dataclass(frozen=True)
class VerificationConfig:
    repository_root: pathlib.Path
    tools_python: pathlib.Path
    tier: Tier = Tier.FULL
    artifact_root: pathlib.Path | None = None


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


def resolve_config(
    args: argparse.Namespace,
    environ: Mapping[str, str] = os.environ,
) -> VerificationConfig:
    tools_python = pathlib.Path(args.tools_python)
    if not tools_python.is_absolute() or not tools_python.is_file() or not os.access(tools_python, os.X_OK):
        raise ValueError("tools Python must be an executable absolute path")

    configured_artifact = args.artifact_root
    if configured_artifact is None:
        configured_artifact = environ.get(ARTIFACT_ROOT_ENV) or None
    artifact_root = pathlib.Path(configured_artifact) if configured_artifact is not None else None
    if artifact_root is not None:
        if not artifact_root.is_absolute():
            raise ValueError("artifact root must be an absolute path")

    return VerificationConfig(
        repository_root=pathlib.Path(args.root).resolve(),
        tools_python=tools_python.resolve(),
        tier=args.tier,
        artifact_root=artifact_root,
    )


def build_inventory(
    repository_root: pathlib.Path,
    tools_python: pathlib.Path,
) -> tuple[CommandSpec, ...]:
    root = pathlib.Path(repository_root).resolve()
    python = str(pathlib.Path(tools_python))
    scripts = root / "scripts/v2"
    pythonpath = (("PYTHONPATH", str(scripts)),)
    source_requirement = frozenset({Requirement.OPENTTD_SOURCE})

    def command(
        command_id: str,
        script: str,
        *,
        category: CommandCategory = CommandCategory.VALIDATOR,
        arguments: tuple[str, ...] = (),
        requirements: frozenset[Requirement] = frozenset(),
        expected_status: int = 0,
    ) -> CommandSpec:
        return CommandSpec(
            command_id=command_id,
            minimum_tier=Tier.CONTRACT,
            category=category,
            argv=(python, str(scripts / script), "--root", str(root), *arguments),
            expected_status=expected_status,
            environment=pythonpath,
            requirements=requirements,
        )

    inventory = (
        command("research-baseline", "validate_research_baseline.py", requirements=source_requirement),
        command(
            "setting-inventory",
            "validate_setting_inventory.py",
            arguments=("--object-repo", str(root / OPENTTD_SUBMODULE)),
            requirements=source_requirement,
        ),
        command("opponent-package-evidence", "validate_opponent_package_evidence.py"),
        command("opponent-runtime-evidence", "validate_opponent_runtime_evidence.py"),
        command("competition-manifest", "validate_competition_manifest.py"),
        command("m15-scalable-contract", "validate_m15_scalable_contract.py"),
        command("m15-policy-contract", "validate_m15_policy_contract.py"),
        command("m15-policy-evidence", "validate_m15_policy_evidence.py"),
        command("m15-map-matrix", "run_m15_map_matrix.py"),
        command("m15-native-source", "validate_m15_native_source.py"),
        command("m15-native-reset-evidence", "validate_m15_native_reset_evidence.py"),
        command("m15-native-reset-matrix", "run_m15_native_reset_matrix.py"),
        command("m15-observation-contract", "validate_m15_observation_contract.py"),
        command("m15-observation-source", "validate_m15_observation_source.py"),
        command(
            "m15-observation-evidence",
            "freeze_m15_observation_evidence.py",
            category=CommandCategory.BUILDER,
        ),
        command("m15-action-contract", "validate_m15_action_contract.py"),
        command("m15-action-source", "validate_m15_action_source.py"),
        command(
            "m15-action-evidence",
            "freeze_m15_action_evidence.py",
            category=CommandCategory.BUILDER,
        ),
        command("m15-episode-source", "validate_m15_episode_source.py"),
        command(
            "m15-episode-evidence",
            "freeze_m15_episode_evidence.py",
            category=CommandCategory.BUILDER,
        ),
        command("m15-cross-scale-replay-evidence", "validate_m15_cross_scale_replay_evidence.py"),
        command("m15-competence-source", "validate_m15_competence_source.py"),
        command("m15-competence-evidence", "validate_m15_competence_evidence.py"),
        command("m16-cargo-source", "validate_m16_cargo_source.py"),
        command("m16-cargo-evidence", "validate_m16_cargo_evidence.py"),
        command("m17-rail-source", "validate_m17_rail_source.py"),
        command("m17-rail-evidence", "validate_m17_rail_evidence.py"),
        command("m18-ship-source", "validate_m18_ship_source.py"),
        command("m18-shipai-evidence", "validate_m18_shipai_evidence.py"),
        command("m18-ship-evidence", "validate_m18_ship_evidence.py"),
        command("m19-air-source", "validate_m19_air_source.py"),
        command("m19-air-evidence", "validate_m19_air_evidence.py"),
        command("m20-competition-source", "validate_m20_competition_source.py"),
        command("m20-competition-evidence", "validate_m20_competition_evidence.py"),
        command("m21-broad-source", "validate_m21_broad_source.py"),
        command("m21-broad-evidence", "validate_m21_broad_evidence.py"),
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
        command(
            "m22-recovery-v1-evidence",
            "validate_m22_recovery_evidence.py",
            arguments=("--report", str(root / "config/v2/m22-recovery-evidence.json")),
        ),
        command(
            "m22-recovery-v2-evidence",
            "validate_m22_recovery_evidence.py",
            arguments=("--report", str(root / "config/v2/m22-recovery-evidence-v2.json")),
        ),
        command(
            "m22-training-evidence",
            "validate_m22_training_evidence.py",
            arguments=("--report", str(root / "config/v2/m22-training-evidence.json")),
        ),
        command(
            "m22-qualification-evidence",
            "validate_m22_qualification_evidence.py",
            arguments=("--report", str(root / "config/v2/m22-qualification-evidence.json")),
        ),
        command("m22-final-runtime-source", "validate_m22_final_runtime_source.py"),
        command("m22-followup-runtime-source", "validate_m22_followup_runtime_source.py"),
        command(
            "m22-final-v1-evaluation",
            "validate_m22_final_evaluation.py",
            expected_status=2,
        ),
        command(
            "m22-followup-v1-manifest-build",
            "build_m22_followup_manifest.py",
            category=CommandCategory.BUILDER,
        ),
        command("m22-followup-v1-manifest", "validate_m22_followup_manifest.py"),
        command(
            "m22-followup-v1-evaluation",
            "validate_m22_followup_evaluation.py",
            expected_status=2,
        ),
        command(
            "m22-followup-v2-manifest-build",
            "build_m22_followup_v2_manifest.py",
            category=CommandCategory.BUILDER,
        ),
        command("m22-followup-v2-manifest", "validate_m22_followup_v2_manifest.py"),
        command("m22-followup-v2-evaluation", "validate_m22_followup_v2_evaluation.py"),
        command("m23-contract", "validate_m23_release_contract.py"),
        command("v2-traceability", "validate_traceability.py"),
        CommandSpec(
            command_id="v2-unit-tests",
            minimum_tier=Tier.FAST,
            category=CommandCategory.TEST,
            argv=(
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(root / "tests/project/v2"),
                "-p",
                "test_*.py",
                "-v",
            ),
            environment=pythonpath,
        ),
        CommandSpec(
            command_id="v1-traceability",
            minimum_tier=Tier.FULL,
            category=CommandCategory.REGRESSION,
            argv=(str(root / "scripts/v1/traceability.sh"), "--tools-python", python),
        ),
    )
    return inventory


def select_commands(
    inventory: Sequence[CommandSpec],
    tier: Tier,
) -> tuple[CommandSpec, ...]:
    return tuple(command for command in inventory if command.minimum_tier <= tier)


def _git(repository_root: pathlib.Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(repository_root), *arguments),
        cwd=repository_root,
        text=True,
        capture_output=True,
        check=False,
    )


def _openttd_source_issue(repository_root: pathlib.Path) -> PreflightIssue | None:
    source = repository_root / OPENTTD_SUBMODULE
    expected = f"initialized clean OpenTTD submodule at {OPENTTD_PIN}"
    if not source.is_dir() or source.is_symlink() or not (source / ".git").exists():
        return PreflightIssue(Requirement.OPENTTD_SOURCE, f"missing {expected}: {source}")

    index = _git(repository_root, "ls-files", "--stage", "--", OPENTTD_SUBMODULE.as_posix())
    expected_index = f"160000 {OPENTTD_PIN} 0\t{OPENTTD_SUBMODULE.as_posix()}"
    if index.returncode != 0 or index.stdout.strip() != expected_index:
        return PreflightIssue(Requirement.OPENTTD_SOURCE, f"outer gitlink is not the {expected}")

    top = _git(source, "rev-parse", "--show-toplevel")
    head = _git(source, "rev-parse", "HEAD")
    status = _git(source, "status", "--porcelain", "--untracked-files=all")
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


def preflight(
    config: VerificationConfig,
    commands: Sequence[CommandSpec],
) -> tuple[PreflightIssue, ...]:
    issues: list[PreflightIssue] = []
    requirements = frozenset(requirement for command in commands for requirement in command.requirements)
    if Requirement.OPENTTD_SOURCE in requirements:
        issue = _openttd_source_issue(config.repository_root)
        if issue is not None:
            issues.append(issue)
    if config.tier is Tier.FULL:
        issue = _artifact_root_issue(config.artifact_root)
        if issue is not None:
            issues.append(issue)
    return tuple(issues)


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def execute_command(command: CommandSpec, repository_root: pathlib.Path) -> CommandResult:
    kwargs: dict[str, object] = {}
    if command.environment:
        kwargs["env"] = {**os.environ, **dict(command.environment)}
    if command.timeout_seconds is not None:
        kwargs["timeout"] = command.timeout_seconds
    try:
        completed = subprocess.run(
            command.argv,
            cwd=repository_root,
            text=True,
            capture_output=True,
            check=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            actual_status=None,
            stdout=_text(exc.stdout),
            stderr=_text(exc.stderr),
            failure_kind=FailureKind.TIMEOUT,
            detail=str(exc),
        )
    except OSError as exc:
        return CommandResult(
            command=command,
            actual_status=None,
            stdout="",
            stderr="",
            failure_kind=FailureKind.SPAWN,
            detail=str(exc),
        )

    failure_kind = None
    detail = None
    if completed.returncode != command.expected_status:
        failure_kind = FailureKind.UNEXPECTED_STATUS
        detail = f"expected status {command.expected_status}, got {completed.returncode}"
    return CommandResult(
        command=command,
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
    issues = preflight(config, commands)
    if issues:
        return VerificationSummary(config=config, preflight_issues=issues, results=())
    results = tuple(execute_command(command, config.repository_root) for command in commands)
    return VerificationSummary(config=config, preflight_issues=(), results=results)


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
