#!/usr/bin/env python3
"""Validate the retained native M16 cargo source delta, patch, content, and executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any

import jsonschema


CONFIG = pathlib.Path("config/v2/m16-cargo-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m16-cargo-source.schema.json")
TOUCHED = ["src/CMakeLists.txt", "src/economy.cpp", "src/economy_func.h", "src/openttd.cpp", "src/rl_v2_cargo.cpp", "src/rl_v2_cargo.h", "src/station_cmd.cpp", "src/station_func.h"]


class M16SourceError(ValueError):
    """M16 native source evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M16SourceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repository: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0, f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None, *, artifact_root: pathlib.Path | None = None, base_source: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    config, schema = load(config_path or root / CONFIG), load(schema_path or root / SCHEMA)
    try:
        jsonschema.Draft202012Validator(schema).validate(config)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M16SourceError(f"source schema failed at {where}: {exc.message}") from exc
    patch = root / config["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink() and sha256(patch) == config["patch"]["sha256"], "patch identity drifted")
    text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
    require(touched == TOUCHED, f"patch scope drifted: {touched}")
    for token in ("RunRlV2CargoQualification", "PayFinalDelivery", "PayTransfer", "ProcessIndustryInputCargo", "CMD_BUILD_ROAD_STOP", "CMD_BUILD_VEHICLE", "OrderUnloadType::Transfer", "RebuildSubsidisedSourceAndDestinationCache"):
        require(token in text, f"patch lost required token: {token}")
    if base_source is not None:
        base_source = base_source.resolve()
        require(git(base_source, "status", "--porcelain") == "", "base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "base commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "base tree drifted")
        checked = subprocess.run(["git", "-C", str(base_source), "apply", "--check", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", checked.stdout + checked.stderr, re.I), "patch does not apply exactly to base")
    live = artifact_root is not None
    if live:
        artifact_root = artifact_root.resolve()
        require(str(artifact_root) == config["retained_artifact"], "retained artifact path drifted")
        source = pathlib.Path(config["source"]["path"])
        require(source == artifact_root / "source" and git(source, "status", "--porcelain") == "", "retained source is missing or dirty")
        require(git(source, "rev-parse", "HEAD") == config["source"]["commit"], "retained source commit drifted")
        require(git(source, "rev-parse", "HEAD^{tree}") == config["source"]["tree"], "retained source tree drifted")
        executable = pathlib.Path(config["executable"]["path"])
        require(executable == artifact_root / "build/openttd" and executable.is_file() and not executable.is_symlink(), "retained executable is missing")
        require(executable.stat().st_size == config["executable"]["bytes"] and sha256(executable) == config["executable"]["sha256"], "executable identity drifted")
        opengfx = pathlib.Path(config["build"]["open_gfx"]["path"])
        require(opengfx.is_file() and sha256(opengfx) == config["build"]["open_gfx"]["sha256"], "OpenGFX identity drifted")
    return {"files": len(touched), "tree": config["source"]["tree"], "live": live}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--base-source", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, artifact_root=args.artifact_root, base_source=args.base_source)
        print(f"V2_M16_CARGO_SOURCE=PASS files={summary['files']} tree={summary['tree']} live={str(summary['live']).lower()}")
        return 0
    except (M16SourceError, OSError, json.JSONDecodeError) as exc:
        print(f"V2_M16_CARGO_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
