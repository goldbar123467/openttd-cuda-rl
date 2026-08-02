#!/usr/bin/env python3
"""Validate the complete pinned OpenTTD setting inventory and source derivation."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

import generate_setting_inventory


class SettingInventoryValidationError(ValueError):
    """The checked-in setting inventory is incomplete, drifted, or misclassified."""


@dataclass(frozen=True)
class SettingInventorySummary:
    source_files: int
    definitions: int
    unique_keys: int
    duplicates: int
    live_source: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SettingInventoryValidationError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingInventoryValidationError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SettingInventoryValidationError(f"cannot hash {path}: {exc}") from exc


def validate(
    root: pathlib.Path,
    inventory_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    object_repository: pathlib.Path | None = None,
) -> SettingInventorySummary:
    root = root.resolve()
    inventory_path = inventory_path or root / "config/v2/setting-inventory.json"
    schema_path = schema_path or root / "docs/project/schema/v2-setting-inventory.schema.json"
    inventory = load_json(inventory_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(inventory)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise SettingInventoryValidationError(f"setting inventory schema failed at {location}: {exc.message}") from exc
    require(inventory["schema_sha256"] == sha256_file(schema_path), "setting inventory schema SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(inventory["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "setting inventory engine source drifted")

    source_files = inventory["source_files"]
    paths = [item["path"] for item in source_files]
    require(paths == sorted(paths), "setting inventory source files are not bytewise sorted")
    require(len(paths) == len(set(paths)), "setting inventory has duplicate source files")
    basenames = {pathlib.PurePosixPath(path).name for path in paths}
    require(basenames == set(generate_setting_inventory.FILE_POLICIES), "setting inventory source-file policy is incomplete")
    for item in source_files:
        expected_policy = generate_setting_inventory.FILE_POLICIES[pathlib.PurePosixPath(item["path"]).name]
        require((item["disposition"], item["rationale_code"]) == expected_policy, f"{item['path']} setting disposition policy drifted")

    definitions = inventory["definitions"]
    require([item["id"] for item in definitions] == [f"V2-SETTING-{index:04d}" for index in range(1, len(definitions) + 1)], "setting inventory IDs are not complete and contiguous")
    positions = [(item["source_file"], item["source_ordinal"]) for item in definitions]
    require(positions == sorted(positions), "setting inventory definitions do not retain source order")
    require(len(positions) == len(set(positions)), "setting inventory repeats a source definition")
    grouped = collections.Counter(item["source_file"] for item in definitions)
    for source_file in source_files:
        path = source_file["path"]
        require(grouped[path] == source_file["definition_count"], f"{path} definition count drifted")
        ordinals = [item["source_ordinal"] for item in definitions if item["source_file"] == path]
        require(ordinals == list(range(1, source_file["definition_count"] + 1)), f"{path} definition ordinals are not contiguous")
    for item in definitions:
        expected_scope = "GLOBAL" if item["kind"].startswith("SDTG") else "CLIENT" if item["kind"].startswith("SDTC") else "GAME"
        require(item["scope"] == expected_scope, f"{item['id']} setting scope drifted")
        expected_policy = generate_setting_inventory.FILE_POLICIES[pathlib.PurePosixPath(item["source_file"]).name]
        require((item["disposition"], item["rationale_code"]) == expected_policy, f"{item['id']} setting disposition drifted")
        require(item["flags"] == sorted(set(item["flags"])), f"{item['id']} flags are not normalized")

    key_counts = collections.Counter((item["scope"], item["setting_key"]) for item in definitions)
    by_scope = collections.Counter(item["scope"] for item in definitions)
    by_disposition = collections.Counter(item["disposition"] for item in definitions)
    expected_counts = {
        "source_files": len(source_files),
        "definitions": len(definitions),
        "unique_setting_keys": len(key_counts),
        "duplicate_key_definitions": sum(count - 1 for count in key_counts.values()),
        "by_scope": dict(sorted(by_scope.items())),
        "by_disposition": dict(sorted(by_disposition.items())),
    }
    require(inventory["counts"] == expected_counts, "setting inventory summary counts drifted")
    require(expected_counts["source_files"] == 20, "pinned OpenTTD 15.3 setting source count drifted")
    require(expected_counts["definitions"] == 435, "pinned OpenTTD 15.3 setting definition count drifted")
    require(by_disposition["SECRET_FORBIDDEN"] == 7, "network secret setting disposition drifted")

    if object_repository is not None:
        try:
            generated = generate_setting_inventory.build_inventory(root, object_repository, inventory["snapshot_date"])
        except generate_setting_inventory.SettingInventoryError as exc:
            raise SettingInventoryValidationError(f"live setting source extraction failed: {exc}") from exc
        require(inventory == generated, "checked-in setting inventory differs from live pinned-source extraction")

    return SettingInventorySummary(
        source_files=expected_counts["source_files"],
        definitions=expected_counts["definitions"],
        unique_keys=expected_counts["unique_setting_keys"],
        duplicates=expected_counts["duplicate_key_definitions"],
        live_source=object_repository is not None,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--inventory", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--object-repo", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summary = validate(args.root, args.inventory, args.schema, object_repository=args.object_repo)
        print(
            f"V2_SETTING_INVENTORY=PASS files={summary.source_files} definitions={summary.definitions} "
            f"unique_keys={summary.unique_keys} duplicates={summary.duplicates} live={str(summary.live_source).lower()}"
        )
        return 0
    except (SettingInventoryValidationError, OSError) as exc:
        print(f"V2_SETTING_INVENTORY=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
