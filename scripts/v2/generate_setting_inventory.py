#!/usr/bin/env python3
"""Extract every setting definition from the pinned OpenTTD 15.3 source tree."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any


class SettingInventoryError(ValueError):
    """Pinned setting source could not be inventoried exactly."""


SOURCE_ROOT = "src/table/settings"
SECTION = re.compile(r"^\[(SD[A-Z0-9_]+)\]$")
FIELD = re.compile(r"^([a-z_]+)\s*=\s*(.*?)\s*$")
FLAG = re.compile(r"SettingFlag::([A-Za-z0-9_]+)")
FILE_POLICIES = {
    "company_settings.ini": ("COMPANY_PIN", "per-company-behavior"),
    "currency_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "difficulty_settings.ini": ("SCENARIO_PIN", "native-simulation"),
    "economy_settings.ini": ("SCENARIO_PIN", "native-simulation"),
    "game_settings.ini": ("SCENARIO_PIN", "native-simulation"),
    "gui_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "linkgraph_settings.ini": ("SCENARIO_PIN", "native-simulation"),
    "locale_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "misc_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "multimedia_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "network_private_settings.ini": ("HARNESS_PIN", "competition-runtime"),
    "network_secrets_settings.ini": ("SECRET_FORBIDDEN", "credential-material"),
    "network_settings.ini": ("HARNESS_PIN", "competition-runtime"),
    "news_display_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "old_gameopt_settings.ini": ("LEGACY_LOAD_ONLY", "historical-save-compatibility"),
    "pathfinding_settings.ini": ("SCENARIO_PIN", "native-simulation"),
    "script_settings.ini": ("SCENARIO_PIN", "native-simulation"),
    "win32_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "window_settings.ini": ("PRESENTATION_ONLY", "non-simulation-client-presentation"),
    "world_settings.ini": ("SCENARIO_PIN", "native-simulation"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SettingInventoryError(message)


def run_git(repository: pathlib.Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.decode("utf-8", errors="replace").strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise SettingInventoryError(f"git {' '.join(args)} failed: {detail}") from exc


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingInventoryError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def normalize_name(value: str) -> str:
    value = value.strip()
    if len(value) >= 4 and value.startswith('""') and value.endswith('""'):
        return value[2:-2]
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_definitions(path: str, content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SettingInventoryError(f"setting source is not UTF-8: {path}") from exc
    blocks: list[tuple[str, dict[str, str]]] = []
    kind: str | None = None
    fields: dict[str, str] = {}

    def finish() -> None:
        nonlocal kind, fields
        if kind is not None:
            blocks.append((kind, fields))
        kind = None
        fields = {}

    for raw_line in text.splitlines():
        section = SECTION.fullmatch(raw_line.strip())
        if section:
            finish()
            kind = section.group(1)
            continue
        if raw_line.startswith("["):
            finish()
            continue
        if kind is None:
            continue
        field = FIELD.match(raw_line)
        if field:
            fields[field.group(1)] = field.group(2)
    finish()

    result: list[dict[str, Any]] = []
    for ordinal, (block_kind, block) in enumerate(blocks, start=1):
        require("var" in block, f"{path} setting {ordinal} ({block_kind}) has no storage variable")
        raw_name = block.get("name")
        key = normalize_name(raw_name) if raw_name is not None else block["var"]
        require(bool(key), f"{path} setting {ordinal} has an empty key")
        if block_kind.startswith("SDTG"):
            scope = "GLOBAL"
        elif block_kind.startswith("SDTC"):
            scope = "CLIENT"
        else:
            require(block_kind.startswith("SDT"), f"unknown setting kind {block_kind}")
            scope = "GAME"
        result.append({
            "source_file": path,
            "source_ordinal": ordinal,
            "kind": block_kind,
            "scope": scope,
            "setting_key": key,
            "storage_variable": block["var"],
            "flags": sorted(set(FLAG.findall(block.get("flags", "")))),
            "default_expression": block.get("def"),
            "minimum_expression": block.get("min"),
            "maximum_expression": block.get("max"),
            "from_version": block.get("from"),
            "to_version": block.get("to"),
        })
    return result


def build_inventory(root: pathlib.Path, object_repository: pathlib.Path, snapshot_date: str = "2026-08-02") -> dict[str, Any]:
    root = root.resolve()
    object_repository = object_repository.resolve()
    source_profile = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    commit = source_profile["commit"]
    actual_tree = run_git(object_repository, "rev-parse", f"{commit}^{{tree}}").decode("ascii").strip()
    require(actual_tree == source_profile["tree"], "pinned OpenTTD source tree does not match source profile")
    listed = run_git(object_repository, "ls-tree", "-r", "--name-only", commit, "--", SOURCE_ROOT).decode("utf-8").splitlines()
    source_paths = sorted(path for path in listed if path.endswith("_settings.ini"))
    basenames = {pathlib.PurePosixPath(path).name for path in source_paths}
    require(basenames == set(FILE_POLICIES), f"setting source-file policy is incomplete: expected={sorted(FILE_POLICIES)} actual={sorted(basenames)}")

    source_files: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    for path in source_paths:
        content = run_git(object_repository, "show", f"{commit}:{path}")
        parsed = parse_definitions(path, content)
        require(parsed, f"setting source has no definitions: {path}")
        disposition, rationale = FILE_POLICIES[pathlib.PurePosixPath(path).name]
        source_files.append({
            "path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "definition_count": len(parsed),
            "disposition": disposition,
            "rationale_code": rationale,
        })
        for row in parsed:
            row["disposition"] = disposition
            row["rationale_code"] = rationale
            definitions.append(row)

    for index, row in enumerate(definitions, start=1):
        row["id"] = f"V2-SETTING-{index:04d}"
        row.move_to_end("id", last=False) if isinstance(row, collections.OrderedDict) else None
    # Plain dictionaries preserve insertion order; rebuild to put the stable ID first.
    definitions = [{"id": row.pop("id"), **row} for row in definitions]
    key_counts = collections.Counter((row["scope"], row["setting_key"]) for row in definitions)
    by_scope = collections.Counter(row["scope"] for row in definitions)
    by_disposition = collections.Counter(row["disposition"] for row in definitions)
    schema_path = root / "docs/project/schema/v2-setting-inventory.schema.json"
    return {
        "$schema": "../../docs/project/schema/v2-setting-inventory.schema.json",
        "schema_version": "openttd-rl-v2-setting-inventory-1",
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "snapshot_date": snapshot_date,
        "engine_source": {key: source_profile[key] for key in ("release", "commit", "tree")},
        "source_root": SOURCE_ROOT,
        "policy": {
            "definition_granularity": "one-row-per-SD-section-at-pinned-commit",
            "duplicates_retained": True,
            "source_order_retained": True,
            "secret_values_forbidden": True,
            "scenario_and_competition_manifests_pin_applicable_values": True,
            "presentation_settings_never_enter_policy_input": True,
        },
        "source_files": source_files,
        "definitions": definitions,
        "counts": {
            "source_files": len(source_files),
            "definitions": len(definitions),
            "unique_setting_keys": len(key_counts),
            "duplicate_key_definitions": sum(count - 1 for count in key_counts.values()),
            "by_scope": dict(sorted(by_scope.items())),
            "by_disposition": dict(sorted(by_disposition.items())),
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--object-repo", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--snapshot-date", default="2026-08-02")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.root.resolve()
    object_repository = (args.object_repo or root / load_json(root / "config/v1/openttd-source-profile.json")["object_repository"]).resolve()
    output = (args.output or root / "config/v2/setting-inventory.json").resolve()
    try:
        inventory = build_inventory(root, object_repository, args.snapshot_date)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        print(
            f"V2_SETTING_INVENTORY_GENERATED files={inventory['counts']['source_files']} "
            f"definitions={inventory['counts']['definitions']} unique_keys={inventory['counts']['unique_setting_keys']} "
            f"output={output}"
        )
        return 0
    except (SettingInventoryError, OSError) as exc:
        print(f"V2_SETTING_INVENTORY_GENERATION=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
