#!/usr/bin/env python3
"""Extract every setting definition from the pinned OpenTTD 15.3 source tree."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

from source_context import (
    SourceContext,
    SourceContextError,
    add_object_repository_argument,
)


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


def _tree_entries(context: SourceContext, tree: str) -> list[tuple[str, str, str]]:
    try:
        text = context.git_bytes("cat-file", "-p", tree).decode("utf-8")
    except (SourceContextError, UnicodeDecodeError) as exc:
        raise SettingInventoryError(f"cannot read pinned Git tree {tree}: {exc}") from exc
    entries: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        metadata, separator, name = line.partition("\t")
        parts = metadata.split()
        require(separator == "\t" and len(parts) == 3, f"malformed pinned Git tree entry: {line!r}")
        _mode, kind, object_id = parts
        entries.append((kind, object_id, name))
    return entries


def _source_paths(
    context: SourceContext,
    root_tree: str,
) -> list[str]:
    tree = root_tree
    prefix: list[str] = []
    for component in SOURCE_ROOT.split("/"):
        match = next(
            (
                (kind, object_id)
                for kind, object_id, name in _tree_entries(context, tree)
                if name == component
            ),
            None,
        )
        require(match is not None and match[0] == "tree", f"missing pinned source directory: {'/'.join((*prefix, component))}")
        tree = match[1]
        prefix.append(component)

    discovered: list[str] = []

    def walk(tree_id: str, relative: tuple[str, ...]) -> None:
        for kind, object_id, name in _tree_entries(context, tree_id):
            current = (*relative, name)
            if kind == "tree":
                walk(object_id, current)
            elif kind == "blob" and name.endswith("_settings.ini"):
                discovered.append("/".join((*SOURCE_ROOT.split("/"), *current)))

    walk(tree, ())
    return sorted(discovered)


def build_inventory(
    root: pathlib.Path,
    source_context: SourceContext,
    snapshot_date: str = "2026-08-02",
) -> dict[str, Any]:
    root = root.resolve()
    source_profile = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    commit = source_profile["commit"]
    require(source_context.is_live, "setting inventory generation requires live source context")
    require(source_context.pinned_commit == commit, "live source context pin differs from source profile")
    try:
        source_context.preflight()
        actual_tree = source_context.git("rev-parse", f"{commit}^{{tree}}")
    except SourceContextError as exc:
        raise SettingInventoryError(f"live source preflight failed: {exc}") from exc
    require(actual_tree == source_profile["tree"], "pinned OpenTTD source tree does not match source profile")
    source_paths = _source_paths(source_context, actual_tree)
    basenames = {pathlib.PurePosixPath(path).name for path in source_paths}
    require(
        len(source_paths) == len(FILE_POLICIES)
        and len(basenames) == len(source_paths)
        and basenames == set(FILE_POLICIES),
        "setting source-file policy is incomplete: "
        f"expected={sorted(FILE_POLICIES)} actual={sorted(basenames)} "
        f"paths={source_paths}",
    )

    source_files: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    for path in source_paths:
        try:
            content = source_context.git_bytes("show", f"{commit}:{path}")
        except SourceContextError as exc:
            raise SettingInventoryError(f"cannot read pinned setting source {path}: {exc}") from exc
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
    add_object_repository_argument(parser)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--snapshot-date", default="2026-08-02")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.root.resolve()
    output = (args.output or root / "config/v2/setting-inventory.json").resolve()
    try:
        require(args.object_repository is not None, "--object-repo is required for setting inventory generation")
        commit = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]["commit"]
        context = SourceContext.live(args.object_repository.resolve(), commit)
        inventory = build_inventory(root, context, args.snapshot_date)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
        print(
            f"V2_SETTING_INVENTORY_GENERATED files={inventory['counts']['source_files']} "
            f"definitions={inventory['counts']['definitions']} unique_keys={inventory['counts']['unique_setting_keys']} "
            f"output={output}"
        )
        return 0
    except (SettingInventoryError, SourceContextError, OSError) as exc:
        print(f"V2_SETTING_INVENTORY_GENERATION=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
