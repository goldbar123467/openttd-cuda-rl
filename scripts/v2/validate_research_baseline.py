#!/usr/bin/env python3
"""Validate the V2 feature, command, map, source, and opponent research baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema


class V2ResearchError(ValueError):
    """The V2 research baseline violates a fail-closed invariant."""


@dataclass(frozen=True)
class ValidationSummary:
    commands: int
    feature_domains: int
    opponents: int
    sources: int
    native_rectangles: int


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise V2ResearchError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise V2ResearchError(f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise V2ResearchError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def git(root: pathlib.Path, *args: str) -> str:
    command = ["git", "-C", str(root), *args]
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise V2ResearchError(f"Git command failed ({' '.join(command)}): {detail}") from exc
    return result.stdout


def extract_pinned_commands(source: str) -> tuple[list[str], str]:
    match = re.search(
        r"enum\s+Commands\s*:\s*uint8_t\s*\{(?P<body>.*?)\bCMD_END\b",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        raise V2ResearchError("cannot find the pinned enum Commands body and CMD_END sentinel")
    body = match.group("body")
    commands = re.findall(r"^\s*(CMD_[A-Z0-9_]+)\s*,", body, flags=re.MULTILINE)
    if not commands:
        raise V2ResearchError("pinned command enum contains no commands")
    if len(commands) != len(set(commands)):
        raise V2ResearchError("pinned command enum contains duplicate command names")
    if source.count("CMD_END") < 1:
        raise V2ResearchError("pinned command enum lacks CMD_END")
    return commands, "CMD_END"


def require_unique(values: list[str], label: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise V2ResearchError(f"duplicate {label}: {duplicates}")


def validate(
    root: pathlib.Path,
    baseline_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
) -> ValidationSummary:
    root = root.resolve()
    baseline_path = baseline_path or root / "config/v2/research-baseline.json"
    schema_path = schema_path or root / "docs/project/schema/v2-research-baseline.schema.json"
    baseline = load_json(baseline_path)
    schema = load_json(schema_path)

    try:
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(baseline)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise V2ResearchError(f"schema validation failed at {location}: {exc.message}") from exc

    actual_schema_hash = sha256_file(schema_path)
    if baseline["schema_sha256"] != actual_schema_hash:
        raise V2ResearchError(
            "schema SHA-256 mismatch: "
            f"baseline={baseline['schema_sha256']} actual={actual_schema_hash}"
        )

    source_profile = load_json(root / "config/v1/openttd-source-profile.json")
    expected_engine = source_profile["upstream"]
    engine = baseline["engine"]
    for key in ("release", "commit", "tree"):
        if engine[key] != expected_engine[key]:
            raise V2ResearchError(
                f"V2 engine {key} drifted from the accepted V1 source baseline: "
                f"{engine[key]!r} != {expected_engine[key]!r}"
            )

    object_repository = root / engine["object_repository"]
    if not object_repository.is_dir():
        raise V2ResearchError(f"missing OpenTTD object repository: {object_repository}")
    actual_tree = git(object_repository, "show", "-s", "--format=%T", engine["commit"]).strip()
    if actual_tree != engine["tree"]:
        raise V2ResearchError(
            f"pinned OpenTTD commit tree mismatch: {actual_tree!r} != {engine['tree']!r}"
        )
    command_source = git(
        object_repository,
        "show",
        f"{engine['commit']}:{engine['command_source']}",
    )
    source_commands, source_sentinel = extract_pinned_commands(command_source)

    dispositions = baseline["command_dispositions"]
    disposition_ids = [item["id"] for item in dispositions]
    expected_dispositions = ["policy-required", "policy-optional", "benchmark-admin"]
    if disposition_ids != expected_dispositions:
        raise V2ResearchError(
            f"command disposition order/identity drifted: {disposition_ids} != {expected_dispositions}"
        )
    inventoried: list[str] = []
    for disposition in dispositions:
        commands = disposition["commands"]
        if commands != sorted(commands):
            raise V2ResearchError(f"{disposition['id']} commands are not bytewise sorted")
        inventoried.extend(commands)
    require_unique(inventoried, "inventoried engine command")
    source_set = set(source_commands)
    inventory_set = set(inventoried)
    missing = sorted(source_set - inventory_set)
    unknown = sorted(inventory_set - source_set)
    if missing or unknown:
        raise V2ResearchError(
            f"engine command coverage mismatch: missing={missing} unknown={unknown}"
        )
    if baseline["command_sentinel"] != source_sentinel:
        raise V2ResearchError("command sentinel drifted from pinned source")

    maps = baseline["maps"]
    sides = maps["native_side_lengths"]
    if any(side & (side - 1) for side in sides):
        raise V2ResearchError("native map side length is not a power of two")
    expected_sides = [2**power for power in range(6, 13)]
    if sides != expected_sides:
        raise V2ResearchError(f"native map side inventory drifted: {sides} != {expected_sides}")
    if maps["native_rectangle_count"] != len(sides) ** 2:
        raise V2ResearchError("native rectangle count does not cover the full side-length product")
    for group in ("curriculum", "generalization", "resource_boundary"):
        for width, height in maps[group]:
            if width not in sides or height not in sides:
                raise V2ResearchError(f"{group} contains non-native dimensions {(width, height)}")
    if not any(width != height for width, height in maps["generalization"]):
        raise V2ResearchError("generalization suite contains no rectangular map")
    if [1024, 1024] not in maps["generalization"]:
        raise V2ResearchError("generalization suite omits the 1024x1024 scale gate")

    sources = baseline["research_sources"]
    source_ids = [item["id"] for item in sources]
    require_unique(source_ids, "research source ID")
    known_sources = set(source_ids)
    domains = baseline["feature_domains"]
    domain_ids = [item["id"] for item in domains]
    require_unique(domain_ids, "feature-domain ID")
    expected_domain_ids = [f"V2-FEAT-{index:03d}" for index in range(1, len(domains) + 1)]
    if domain_ids != expected_domain_ids:
        raise V2ResearchError(
            f"feature domains are not contiguous and ordered: {domain_ids} != {expected_domain_ids}"
        )
    for domain in domains:
        dangling = sorted(set(domain["source_ids"]) - known_sources)
        if dangling:
            raise V2ResearchError(f"{domain['id']} references unknown research sources: {dangling}")
        if domain["status"] == "PASS":
            raise V2ResearchError(
                f"{domain['id']} cannot become PASS in the research baseline without gate evidence"
            )

    opponents = baseline["opponents"]
    opponent_ids = [item["content_id"] for item in opponents]
    opponent_names = [item["name"] for item in opponents]
    require_unique(opponent_ids, "opponent content ID")
    require_unique(opponent_names, "opponent name")
    for opponent in opponents:
        if not opponent["package_url"].endswith("/" + opponent["content_id"]):
            raise V2ResearchError(
                f"{opponent['name']} package URL does not match content ID {opponent['content_id']}"
            )
        modes = set(opponent["advertised_modes"])
        if "none" in modes and len(modes) != 1:
            raise V2ResearchError(f"{opponent['name']} mixes the none mode with transport modes")
    required_names = {
        "AAAHogEx",
        "LuDiAI AfterFix",
        "Trans AI",
        "ChooChoo",
        "Lufthansa",
        "ShipAI",
        "KrakenAI2",
        "SimpleAI",
        "WmDOT",
        "NoOpAI",
    }
    if set(opponent_names) != required_names:
        raise V2ResearchError(
            f"opponent audit pool drifted: missing={sorted(required_names - set(opponent_names))} "
            f"unknown={sorted(set(opponent_names) - required_names)}"
        )
    for required_mode in ("road", "rail", "ship", "air"):
        if not any(required_mode in opponent["advertised_modes"] for opponent in opponents):
            raise V2ResearchError(f"opponent pool has no advertised {required_mode} coverage")

    resolution = baseline["user_ai_name_resolution"]
    if resolution["exact_catalog_match"] is not False:
        raise V2ResearchError("unproven Minimax catalog identity must remain unresolved")
    if not {"KrakenAI2", "WmDOT"}.issubset(set(opponent_names)):
        raise V2ResearchError("Minimax-name candidate records are absent from opponent pool")

    for relative in ("docs/project/V2_RESEARCH.md", "docs/project/V2_PLAN.md"):
        path = root / relative
        if not path.is_file():
            raise V2ResearchError(f"missing V2 authority document: {relative}")
    research_text = (root / "docs/project/V2_RESEARCH.md").read_text(encoding="utf-8")
    for token in ("145 executable commands", "4096", "KrakenAI2", "WmDOT", "Minimax"):
        if token not in research_text:
            raise V2ResearchError(f"V2 research document omits required coverage token {token!r}")

    return ValidationSummary(
        commands=len(inventoried),
        feature_domains=len(domains),
        opponents=len(opponents),
        sources=len(sources),
        native_rectangles=maps["native_rectangle_count"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--baseline", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        summary = validate(args.root, args.baseline, args.schema)
    except (V2ResearchError, OSError) as exc:
        print(f"V2_RESEARCH=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V2_RESEARCH=PASS "
        f"commands={summary.commands} "
        f"feature_domains={summary.feature_domains} "
        f"opponents={summary.opponents} "
        f"sources={summary.sources} "
        f"native_rectangles={summary.native_rectangles}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
