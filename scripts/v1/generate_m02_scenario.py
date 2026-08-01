#!/usr/bin/env python3
"""Select and validate a deterministic fixed-template M02 scenario offline."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m02_scenario_contract


class M02ScenarioGenerationError(ValueError):
    """A generation request or frozen scenario predicate was rejected."""

    def __init__(self, predicate: str, detail: str) -> None:
        super().__init__(f"predicate={predicate} detail={detail}")
        self.predicate = predicate
        self.detail = detail


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def identity_sha256(value: dict[str, Any], field: str) -> str:
    payload = copy.deepcopy(value)
    payload["identity"].pop(field, None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_schema(instance: Any, schema: Any, label: str) -> None:
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(instance)
    except jsonschema.SchemaError as exc:
        raise M02ScenarioGenerationError("invalid-schema", f"{label}: {exc.message}") from exc
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise M02ScenarioGenerationError(
            f"{label}-schema",
            f"path={location} error={exc.message}",
        ) from exc


def point(value: dict[str, Any]) -> tuple[int, int]:
    return value["x"], value["y"]


def route_tiles(waypoints: list[dict[str, Any]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for first, second in zip(waypoints, waypoints[1:]):
        x1, y1 = point(first)
        x2, y2 = point(second)
        if x1 != x2 and y1 != y2:
            raise M02ScenarioGenerationError(
                "route-segment-not-axis-aligned",
                f"segment=({x1},{y1})->({x2},{y2})",
            )
        if (x1, y1) == (x2, y2):
            raise M02ScenarioGenerationError(
                "route-segment-empty",
                f"point=({x1},{y1})",
            )
        dx = (x2 > x1) - (x2 < x1)
        dy = (y2 > y1) - (y2 < y1)
        x, y = x1, y1
        segment: list[tuple[int, int]] = []
        while True:
            segment.append((x, y))
            if (x, y) == (x2, y2):
                break
            x += dx
            y += dy
        if result and segment[0] == result[-1]:
            segment.pop(0)
        result.extend(segment)
    if len(result) != len(set(result)):
        raise M02ScenarioGenerationError("route-self-intersection", "route tile repeats")
    return result


def manhattan(first: tuple[int, int], second: tuple[int, int]) -> int:
    return abs(first[0] - second[0]) + abs(first[1] - second[1])


def validate_template(template: dict[str, Any], contract: dict[str, Any]) -> None:
    towns = template["towns"]
    if [town["town_id"] for town in towns] != [0, 1]:
        raise M02ScenarioGenerationError(
            "town-id-order",
            f"template={template['template_id']} expected=[0,1]",
        )
    centers = [point(town) for town in towns]
    center_distance = manhattan(centers[0], centers[1])
    town_contract = contract["towns"]
    if not (
        town_contract["center_manhattan_distance_min"]
        <= center_distance
        <= town_contract["center_manhattan_distance_max"]
    ):
        raise M02ScenarioGenerationError(
            "town-center-distance",
            f"template={template['template_id']} distance={center_distance}",
        )

    route = route_tiles(template["road_waypoints"])
    route_length = len(route) - 1
    if not (
        town_contract["road_path_length_min"]
        <= route_length
        <= town_contract["road_path_length_max"]
    ):
        raise M02ScenarioGenerationError(
            "road-path-length",
            f"template={template['template_id']} length={route_length}",
        )
    route_set = set(route)
    stops = template["bus_stops"]
    if [stop["town_id"] for stop in stops] != [0, 1]:
        raise M02ScenarioGenerationError(
            "stop-town-order",
            f"template={template['template_id']} expected=[0,1]",
        )
    for stop in stops:
        stop_point = point(stop)
        if stop_point not in route_set:
            raise M02ScenarioGenerationError(
                "stop-off-route",
                f"template={template['template_id']} stop={stop_point}",
            )
        if manhattan(stop_point, centers[stop["town_id"]]) > 4:
            raise M02ScenarioGenerationError(
                "stop-outside-town-catchment-envelope",
                f"template={template['template_id']} town={stop['town_id']}",
            )
    if point(stops[0]) == point(stops[1]):
        raise M02ScenarioGenerationError("duplicate-stop-site", template["template_id"])

    depot = point(template["road_depot"])
    if depot in route_set:
        raise M02ScenarioGenerationError("depot-on-route", template["template_id"])
    if min(manhattan(depot, tile) for tile in route) != 1:
        raise M02ScenarioGenerationError(
            "depot-not-adjacent-to-route",
            f"template={template['template_id']} depot={depot}",
        )
    occupied = {*centers, point(stops[0]), point(stops[1])}
    if depot in occupied:
        raise M02ScenarioGenerationError("facility-overlap", template["template_id"])


def validate_seed_entries(
    entries: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> None:
    ledger_seeds = [entry["seed"] for entry in entries]
    if len(ledger_seeds) != len(set(ledger_seeds)):
        raise M02ScenarioGenerationError("seed-partition-overlap", "seed occurs more than once")
    expected_entries = [
        {
            "seed": template["seed"],
            "split": template["split"],
            "template_id": template["template_id"],
            "trainer_visible": template["split"] != "final-evaluation",
        }
        for template in templates
    ]
    if entries != expected_entries:
        raise M02ScenarioGenerationError("ledger-corpus-mismatch", "ledger is not the exact corpus index")


def load_and_validate(
    contract_path: pathlib.Path,
    contract_schema_path: pathlib.Path,
    corpus_path: pathlib.Path,
    corpus_schema_path: pathlib.Path,
    ledger_path: pathlib.Path,
    ledger_schema_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = validate_m02_scenario_contract.validate(contract_path, contract_schema_path)
    corpus = validate_m02_scenario_contract.load_strict_json(corpus_path)
    corpus_schema = validate_m02_scenario_contract.load_strict_json(corpus_schema_path)
    ledger = validate_m02_scenario_contract.load_strict_json(ledger_path)
    ledger_schema = validate_m02_scenario_contract.load_strict_json(ledger_schema_path)
    if not all(isinstance(value, dict) for value in (corpus, corpus_schema, ledger, ledger_schema)):
        raise M02ScenarioGenerationError("artifact-type", "corpus, ledger, and schemas must be objects")
    validate_schema(corpus, corpus_schema, "corpus")
    validate_schema(ledger, ledger_schema, "seed-ledger")

    contract_identity = contract["identity"]["compatibility_sha256"]
    if corpus["contract_compatibility_sha256"] != contract_identity:
        raise M02ScenarioGenerationError("corpus-contract-identity", "compatibility digest drift")
    observed_corpus_schema = validate_m02_scenario_contract.sha256_file(corpus_schema_path)
    if corpus["identity"]["schema_sha256"] != observed_corpus_schema:
        raise M02ScenarioGenerationError(
            "corpus-schema-identity",
            f"expected={corpus['identity']['schema_sha256']} actual={observed_corpus_schema}",
        )
    observed_corpus = identity_sha256(corpus, "corpus_sha256")
    if corpus["identity"]["corpus_sha256"] != observed_corpus:
        raise M02ScenarioGenerationError(
            "corpus-identity",
            f"expected={corpus['identity']['corpus_sha256']} actual={observed_corpus}",
        )

    templates = corpus["templates"]
    template_ids = [template["template_id"] for template in templates]
    expected_ids = [f"m02-template-{index:02d}" for index in range(1, 9)]
    if template_ids != expected_ids:
        raise M02ScenarioGenerationError(
            "template-id-order",
            f"expected={expected_ids} actual={template_ids}",
        )
    seeds = [template["seed"] for template in templates]
    if len(seeds) != len(set(seeds)):
        raise M02ScenarioGenerationError("duplicate-corpus-seed", "template seeds are not unique")
    for template in templates:
        validate_template(template, contract)

    if ledger["contract_compatibility_sha256"] != contract_identity:
        raise M02ScenarioGenerationError("ledger-contract-identity", "compatibility digest drift")
    if ledger["corpus_sha256"] != observed_corpus:
        raise M02ScenarioGenerationError("ledger-corpus-identity", "corpus digest drift")
    observed_ledger_schema = validate_m02_scenario_contract.sha256_file(ledger_schema_path)
    if ledger["identity"]["schema_sha256"] != observed_ledger_schema:
        raise M02ScenarioGenerationError(
            "ledger-schema-identity",
            f"expected={ledger['identity']['schema_sha256']} actual={observed_ledger_schema}",
        )
    observed_ledger = identity_sha256(ledger, "ledger_sha256")
    if ledger["identity"]["ledger_sha256"] != observed_ledger:
        raise M02ScenarioGenerationError(
            "ledger-identity",
            f"expected={ledger['identity']['ledger_sha256']} actual={observed_ledger}",
        )

    validate_seed_entries(ledger["entries"], templates)
    return contract, corpus, ledger


def build_instance(
    contract: dict[str, Any],
    corpus: dict[str, Any],
    ledger: dict[str, Any],
    template: dict[str, Any],
    instance_schema_path: pathlib.Path,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "openttd-rl-v1-m02-scenario-instance-1",
        "contract_id": contract["contract_id"],
        "contract_compatibility_sha256": contract["identity"]["compatibility_sha256"],
        "corpus_sha256": corpus["identity"]["corpus_sha256"],
        "seed_ledger_sha256": ledger["identity"]["ledger_sha256"],
        "template_id": template["template_id"],
        "split": template["split"],
        "seed": template["seed"],
        "engine": contract["engine"],
        "content": contract["content"],
        "template": template,
        "generation": {
            "implicit_retry_count": 0,
            "mode": "fixed-template",
            "rejection_policy": "record-and-fail",
        },
        "identity": {
            "algorithm": "sha256-canonical-json-v1",
            "scenario_sha256": "",
            "schema_path": "docs/project/schema/v1-m02-scenario-instance.schema.json",
            "schema_sha256": validate_m02_scenario_contract.sha256_file(instance_schema_path),
        },
    }
    value["identity"]["scenario_sha256"] = identity_sha256(value, "scenario_sha256")
    schema = validate_m02_scenario_contract.load_strict_json(instance_schema_path)
    validate_schema(value, schema, "scenario-instance")
    return value


def write_new(path: pathlib.Path, value: dict[str, Any]) -> None:
    if not path.is_absolute():
        raise M02ScenarioGenerationError("output-not-absolute", str(path))
    if path.exists() or path.is_symlink():
        raise M02ScenarioGenerationError("output-exists", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, canonical_bytes(value) + b"\n")
    finally:
        os.close(descriptor)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--template-id")
    selector.add_argument("--seed", type=int)
    parser.add_argument(
        "--declared-split",
        required=True,
        choices=("training", "development", "final-evaluation"),
    )
    parser.add_argument("--allow-final-evaluation", action="store_true")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        contract, corpus, ledger = load_and_validate(
            root / "config/v1/m02-scenario-contract.json",
            root / "docs/project/schema/v1-m02-scenario-contract.schema.json",
            root / "config/v1/m02-scenario-corpus.json",
            root / "docs/project/schema/v1-m02-scenario-corpus.schema.json",
            root / "config/v1/m02-seed-ledger.json",
            root / "docs/project/schema/v1-m02-seed-ledger.schema.json",
        )
        matches = [
            template
            for template in corpus["templates"]
            if (
                template["template_id"] == args.template_id
                if args.template_id is not None
                else template["seed"] == args.seed
            )
        ]
        if len(matches) != 1:
            raise M02ScenarioGenerationError(
                "unknown-selector",
                f"template_id={args.template_id!r} seed={args.seed!r}",
            )
        template = matches[0]
        if template["split"] != args.declared_split:
            raise M02ScenarioGenerationError(
                "declared-split-mismatch",
                f"expected={template['split']} actual={args.declared_split}",
            )
        if template["split"] == "final-evaluation" and not args.allow_final_evaluation:
            raise M02ScenarioGenerationError(
                "final-evaluation-withheld",
                "explicit --allow-final-evaluation is required",
            )
        value = build_instance(
            contract,
            corpus,
            ledger,
            template,
            root / "docs/project/schema/v1-m02-scenario-instance.schema.json",
        )
        write_new(args.output, value)
    except (OSError, M02ScenarioGenerationError, validate_m02_scenario_contract.M02ScenarioContractError) as exc:
        print(f"M02_SCENARIO_GENERATION=REJECTED {exc}", file=sys.stderr)
        return 1
    print(
        "M02_SCENARIO_GENERATION=PASS "
        f"template_id={value['template_id']} scenario_sha256={value['identity']['scenario_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
