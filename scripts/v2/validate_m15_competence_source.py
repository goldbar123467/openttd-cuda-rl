#!/usr/bin/env python3
"""Validate the exact M15 passenger-service source delta and retained build."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

import jsonschema


CONFIG = pathlib.Path("config/v2/m15-competence-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-competence-source.schema.json")
EXPECTED_FILES = ["src/rl_v2_action.cpp"]
FORBIDDEN_V1_FILES = {
    "src/rl_action.cpp", "src/rl_action.h", "src/rl_bridge.cpp", "src/rl_bridge.h",
    "src/rl_environment.cpp", "src/rl_environment.h", "src/rl_neural_agent.cpp",
    "src/rl_neural_agent.h", "src/rl_observation.cpp", "src/rl_observation.h",
    "src/rl_reward.cpp", "src/rl_reward.h",
}


class M15CompetenceSourceError(ValueError):
    """The M15 passenger-service source or build evidence is inconsistent."""


@dataclass(frozen=True)
class M15CompetenceSourceSummary:
    files: int
    result_tree: str
    live_source: bool
    live_build: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15CompetenceSourceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15CompetenceSourceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15CompetenceSourceError(f"cannot hash {path}: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *arguments], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    base_source: pathlib.Path | None = None,
    artifact_root: pathlib.Path | None = None,
) -> M15CompetenceSourceSummary:
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15CompetenceSourceError(f"M15 competence source schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 competence source schema SHA-256 mismatch")
    require(config["base"]["episode_source_evidence_sha256"] == sha256_file(root / "config/v2/m15-episode-source.json"), "M15 episode source evidence identity drifted")
    patch = root / config["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink(), "M15 competence patch is missing or a symlink")
    require(sha256_file(patch) == config["patch"]["sha256"], "M15 competence patch SHA-256 mismatch")
    patch_text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", patch_text, re.MULTILINE)
    require(touched == EXPECTED_FILES, f"M15 competence patch file scope drifted: {touched}")
    require(not (set(touched) & FORBIDDEN_V1_FILES), "M15 competence patch modifies a frozen V1 RL source file")
    for token in ("RunPassengerService", "FindServiceSite", "StateGameLoop", "CMD_BUILD_VEHICLE", "delivered_passengers", 'operation == \"SERVICE\"'):
        require(token in patch_text, f"M15 competence patch lost required token: {token}")

    if base_source is not None:
        base_source = base_source.resolve()
        require(git(base_source, "status", "--porcelain") == "", "M15 competence base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "M15 competence base commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "M15 competence base tree drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m15-competence-source-") as raw:
            target = pathlib.Path(raw) / "source"
            cloned = subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(target)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(cloned.returncode == 0, f"cannot clone competence base source: {cloned.stderr.strip()}")
            checked = subprocess.run(["git", "-C", str(target), "apply", "--check", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", checked.stdout + checked.stderr, re.I), "M15 competence patch does not apply exactly")
            applied = subprocess.run(["git", "-C", str(target), "apply", "--index", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(applied.returncode == 0, f"cannot apply M15 competence patch: {applied.stderr.strip()}")
            require(git(target, "write-tree") == config["result"]["tree"], "M15 competence result tree drifted")

    if artifact_root is not None:
        artifact_root = artifact_root.resolve()
        require(str(artifact_root) == config["build"]["artifact_root"], "M15 competence build artifact root drifted")
        executable = artifact_root / config["build"]["executable"]["path"]
        require(executable.is_file() and not executable.is_symlink(), "M15 competence executable is missing or a symlink")
        require(executable.stat().st_size == config["build"]["executable"]["size"], "M15 competence executable size drifted")
        require(sha256_file(executable) == config["build"]["executable"]["sha256"], "M15 competence executable SHA-256 drifted")
        source = artifact_root / "source"
        require(git(source, "status", "--porcelain") == "", "M15 competence retained source is dirty")
        require(git(source, "rev-parse", "HEAD") == config["result"]["commit"], "M15 competence retained commit drifted")
        require(git(source, "rev-parse", "HEAD^{tree}") == config["result"]["tree"], "M15 competence retained tree drifted")
    return M15CompetenceSourceSummary(len(touched), config["result"]["tree"], base_source is not None, artifact_root is not None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--base-source", type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, args.config, args.schema, base_source=args.base_source, artifact_root=args.artifact_root)
        print(f"V2_M15_COMPETENCE_SOURCE=PASS files={summary.files} result_tree={summary.result_tree} live_source={str(summary.live_source).lower()} live_build={str(summary.live_build).lower()}")
        return 0
    except (M15CompetenceSourceError, OSError) as exc:
        print(f"V2_M15_COMPETENCE_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
