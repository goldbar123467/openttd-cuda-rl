#!/usr/bin/env python3
"""Validate the frozen scenario-specific ShipAI qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import jsonschema

import qualify_ai_runtime


CONFIG = pathlib.Path("config/v2/m18-shipai-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m18-shipai-evidence.schema.json")
PACKAGE_INDEX = pathlib.Path("config/v2/opponent-package-evidence.json")
RUNTIME_INDEX = pathlib.Path("config/v2/opponent-runtime-evidence.json")


class M18ShipAIError(ValueError):
    """The M18 ShipAI evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M18ShipAIError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve()
    evidence = load(root / CONFIG)
    try:
        jsonschema.Draft202012Validator(load(root / SCHEMA)).validate(evidence)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M18ShipAIError(f"ShipAI schema failed at {where}: {exc.message}") from exc
    package_index, runtime_index = load(root / PACKAGE_INDEX), load(root / RUNTIME_INDEX)
    package_records = [item for item in package_index["results"] if item["name"] == "ShipAI"]
    runtime_records = [item for item in runtime_index["results"] if item["name"] == "ShipAI"]
    require(len(package_records) == 1 and len(runtime_records) == 1, "M14 ShipAI index cardinality drifted")
    package_record, runtime_record = package_records[0], runtime_records[0]
    require(runtime_record["outcome"] == evidence["m14"]["outcome"] and
            runtime_record["admission"] == evidence["m14"]["admission"] and
            runtime_record["evidence_sha256"] == evidence["m14"]["evidence_sha256"],
            "M14 ShipAI runtime disposition drifted")
    lock_path = pathlib.Path(package_index["artifact_base_hint"]) / package_record["artifact_dir"] / package_record["evidence_file"]
    require(lock_path.is_file() and sha256(lock_path) == package_record["evidence_sha256"], "M14 ShipAI package lock identity drifted")
    lock = load(lock_path)
    require(len(lock["packages"]) == 1 and lock["request"] == {
        "catalog_url": "https://bananas.openttd.org/package/ai/53484950", "content_unique_id": "53484950",
        "name": "ShipAI", "version": 10}, "M14 ShipAI package request drifted")
    locked_package = lock["packages"][0]
    require(evidence["package"] == {"name": locked_package["name"], "content_unique_id": locked_package["local_unique_id"],
            "version": locked_package["version"], "archive_sha256": locked_package["archive_sha256"]},
            "M14 ShipAI package projection drifted")
    for key in ("scenario", "qualification_manifest"):
        record = evidence[key]
        path = pathlib.Path(record["path"])
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"],
                f"ShipAI {key} identity drifted")
    manifest = qualify_ai_runtime.validate_manifest(root, pathlib.Path(evidence["qualification_manifest"]["path"]))
    require(manifest["outcome"] == "QUALIFIED_ACTIVE" and all(manifest["checks"].values()), "ShipAI runtime qualification is not active and healthy")
    before, after = manifest["observations"]["company_before_load"], manifest["observations"]["company_after_load"]
    require(before["ships"] >= 1 and after["ships"] == before["ships"] and sum(before[k] for k in ("trains", "road_vehicles", "aircraft")) == 0,
            "ShipAI did not retain an all-ship fleet across save/load")
    observations = evidence["observations"]
    require(observations == {"minimum_days": manifest["scenario"]["minimum_elapsed_days"], "ships_before_load": before["ships"],
            "ships_after_load": after["ships"], "save_load_restored": True}, "ShipAI observation projection drifted")
    return {"ships": after["ships"], "days": observations["minimum_days"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        summary = validate(args.root)
        print(f"V2_M18_SHIPAI=PASS ships={summary['ships']} days={summary['days']} save_load=true")
        return 0
    except (M18ShipAIError, qualify_ai_runtime.AIRuntimeError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M18_SHIPAI=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
