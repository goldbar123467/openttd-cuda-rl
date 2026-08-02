#!/usr/bin/env python3
"""Actual-engine golden, semantic, equivalence, and non-perturbation oracle for M04."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
import re
import struct
import sys
from typing import Any

import jsonschema

import m03_bridge_protocol
import m04_preprocessing
import validate_m04_observation_contract


BRIDGE_COMPATIBILITY_SHA256 = "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6"
OBSERVE = 8
REPORT_SCHEMA_SHA256 = "1e194350eeedfa0142b7bb21c4fad3ba2874aba9924f7f4c0f11e77aa8f35c93"
M04_PATCH_SHA256 = "fd63122a88dc86ddd8caacb6be3ddce0445ab889701b779e60d264aa736ebea4"
M04_SERIES_SHA256 = "b676ddaaf9cfe3fa1610a25941fac136c91e5c50445f604d0bc2637ada809670"
M04_RESULT_TREE = "fe815570b5c816c6b324a9bf63d965157ea425c6"
M04_COMPOSED_SOURCE_IDENTITY = "820cf3ee0fb36734c318cb260e6cc4567a2a9acc55c831d5b36d1875341b291e"
M03_RESULT_TREE = "39ed7069eca2c48c512a9bdd989c049aca3c5329"
M03_COMPOSED_SOURCE_IDENTITY = "d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1"


class M04ObservationOracleError(ValueError):
    """Actual engine output violated the frozen M04 observation contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M04ObservationOracleError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_canonical_new(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise M04ObservationOracleError(f"refusing to overwrite {path}")
    path.write_bytes(canonical_bytes(value) + b"\n")


def validate_native_delta(root: pathlib.Path) -> None:
    directory = root / "integration/openttd/patches/15.3/m04"
    series = directory / "series"
    patch = directory / "0005-versioned-policy-observation.patch"
    require(series.is_file() and not series.is_symlink(), "M04 series is not a regular file")
    require(patch.is_file() and not patch.is_symlink(), "M04 patch is not a regular file")
    require(sha256_file(series) == M04_SERIES_SHA256, "M04 series digest drifted")
    require(sha256_file(patch) == M04_PATCH_SHA256, "M04 patch digest drifted")
    require(series.read_text(encoding="utf-8") == patch.name + "\n", "M04 series inventory drifted")


def float32_bytes(value: float) -> bytes:
    return struct.pack("<f", value)


def slot_presence(raw: list[int], index: int, group: str) -> int:
    if group == "global":
        return 1
    if group == "town":
        return raw[28 + ((index - 28) // 10) * 10]
    if group == "vehicle":
        return raw[48 + ((index - 48) // 10) * 10]
    if group == "station":
        return raw[128 + ((index - 128) // 5) * 5]
    if group == "route":
        return raw[208 + ((index - 208) // 6) * 6]
    raise AssertionError(group)


def normalized_field(field: dict[str, Any], raw: list[int]) -> float:
    index = field["index"]
    value = raw[index]
    transform = field["transform"]
    if field["group"] != "global" and slot_presence(raw, index, field["group"]) == 0:
        return 0.0
    if "capacity zero" in transform:
        if field["group"] == "vehicle":
            slot = (index - 48) // 10
        else:
            slot = (index - 208) // 6
        capacity = raw[48 + slot * 10 + 5]
        return 0.0 if capacity == 0 else min(max(value, 0), capacity) / capacity
    if transform == "raw/32 when tile valid":
        return 0.0 if value < 0 else value / 32.0
    if transform.startswith("exact"):
        return 1.0 if value else 0.0
    plus = re.fullmatch(r"\(raw\+1\)/(\d+)", transform)
    if plus:
        return (value + 1) / int(plus.group(1))
    raw_div = re.fullmatch(r"raw/(\d+)", transform)
    if raw_div:
        return value / int(raw_div.group(1))
    numeric_clip = re.fullmatch(r"clip\(raw,(-?\d+),(-?\d+)\)/(\d+)", transform)
    if numeric_clip:
        low, high, denominator = map(int, numeric_clip.groups())
        return min(max(value, low), high) / denominator
    if transform == "clip(raw,0,Ticks::DAY_TICKS)/Ticks::DAY_TICKS":
        return min(max(value, 0), 74) / 74.0
    raise M04ObservationOracleError(f"oracle has no transform for {field['name']}: {transform}")


def validate_structured(observation: dict[str, Any], contract: dict[str, Any]) -> int:
    source = observation["source_projection"]["structured"]
    actual = observation["structured"]["data"]
    require(len(source) == 256 and len(actual) == 256, "structured/source size mismatch")
    for field in contract["tensors"]["structured"]["fields"]:
        index = field["index"]
        expected = normalized_field(field, source)
        require(
            float32_bytes(expected) == float32_bytes(actual[index]),
            f"structured mismatch index={index} name={field['name']} raw={source[index]} expected={expected} actual={actual[index]}",
        )
    return 256


def validate_spatial(observation: dict[str, Any], company_id: int = 0) -> tuple[int, list[float]]:
    source = observation["source_projection"]
    actual = observation["spatial"]["data"]
    require(len(actual) == 32 * 1024, "spatial size mismatch")
    channel_sums = [0.0] * 32
    for tile in range(1024):
        tile_type = source["tile_type"][tile]
        road_bits = source["road_bits"][tile]
        road_owner = source["road_owner"][tile]
        stop_direction = source["bus_stop_direction"][tile]
        depot_direction = source["depot_direction"][tile]
        valid = tile_type != 7
        expected = [
            float(valid),
            float(not valid),
            min(source["height"][tile], 256) / 256.0,
            float(tile_type == 0),
            float(road_owner >= 0),
            float(road_owner == company_id),
            float(bool(road_bits & 8)),
            float(bool(road_bits & 4)),
            float(bool(road_bits & 2)),
            float(bool(road_bits & 1)),
            float(tile_type == 3),
            float(source["town_id"][tile] == 0),
            float(source["town_id"][tile] == 1),
            float(bool(source["town_center"][tile])),
            min(source["house_population"][tile], 256) / 256.0,
            float(bool(source["passenger_source"][tile])),
            float(stop_direction >= 0),
            float(stop_direction == 0),
            float(stop_direction == 1),
            float(stop_direction == 2),
            float(stop_direction == 3),
            float(depot_direction >= 0),
            float(depot_direction == 0),
            float(depot_direction == 1),
            float(depot_direction == 2),
            float(depot_direction == 3),
            float(bool(source["route_endpoint"][tile])),
            min(source["vehicle_count"][tile], 8) / 8.0,
            float(bool(source["clear_flat"][tile])),
            float(valid and not source["clear_flat"][tile]),
            float(
                road_owner == company_id
                or (stop_direction >= 0 and source["tile_owner"][tile] == company_id)
                or (depot_direction >= 0 and source["tile_owner"][tile] == company_id)
            ),
            float(bool(source["station_catchment"][tile])),
        ]
        for channel, value in enumerate(expected):
            position = channel * 1024 + tile
            require(
                float32_bytes(value) == float32_bytes(actual[position]),
                f"spatial mismatch channel={channel} tile={tile} expected={value} actual={actual[position]}",
            )
            channel_sums[channel] += actual[position]
    return 32 * 1024, channel_sums


def request_reset(worker: m03_bridge_protocol.WorkerProcess, session: int, request_id: int = 1) -> m03_bridge_protocol.Frame:
    return worker.client.request(
        message_type=m03_bridge_protocol.RESET,
        session_id=session,
        episode_id=0,
        request_id=request_id,
        transition_ordinal=0,
        payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY_SHA256},
    )


def request_step_setup(worker: m03_bridge_protocol.WorkerProcess, session: int, request_id: int, boundary: str) -> m03_bridge_protocol.Frame:
    return worker.client.request(
        message_type=m03_bridge_protocol.STEP,
        session_id=session,
        episode_id=1,
        request_id=request_id,
        transition_ordinal=1,
        payload={
            "action_id": 1,
            "action_interval_ticks": 1,
            "boundary_token": boundary,
            "bridge_compatibility_sha256": BRIDGE_COMPATIBILITY_SHA256,
        },
    )


def request_observe(
    worker: m03_bridge_protocol.WorkerProcess,
    *,
    session: int,
    request_id: int,
    transition: int,
    compatibility: str,
    source: bool,
) -> m03_bridge_protocol.Frame:
    return worker.client.request(
        message_type=OBSERVE,
        session_id=session,
        episode_id=1,
        request_id=request_id,
        transition_ordinal=transition,
        payload={
            "include_source_projection": source,
            "observation_compatibility_sha256": compatibility,
        },
    )


def request_snapshot(worker: m03_bridge_protocol.WorkerProcess, session: int, request_id: int, transition: int) -> m03_bridge_protocol.Frame:
    return worker.client.request(
        message_type=m03_bridge_protocol.SNAPSHOT,
        session_id=session,
        episode_id=1,
        request_id=request_id,
        transition_ordinal=transition,
        payload={},
    )


def request_close(worker: m03_bridge_protocol.WorkerProcess, session: int, request_id: int, transition: int) -> None:
    response = worker.client.request(
        message_type=m03_bridge_protocol.CLOSE,
        session_id=session,
        episode_id=1,
        request_id=request_id,
        transition_ordinal=transition,
        payload={},
    )
    require(response.payload["status"] == "OK", "worker CLOSE failed")


def run_template(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    contract: dict[str, Any],
    session: int,
    timeout: float,
) -> dict[str, Any]:
    observed = m03_bridge_protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root / "observed",
        timeout=timeout,
    )
    control = m03_bridge_protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root / "control",
        timeout=timeout,
    )
    try:
        observed_reset = request_reset(observed, session)
        control_reset = request_reset(control, session)
        require(observed_reset.payload["snapshot"] == control_reset.payload["snapshot"], "reset snapshots differ")
        boundary = observed_reset.payload["snapshot"]["boundary_token"]

        reset_a = request_observe(
            observed,
            session=session,
            request_id=2,
            transition=0,
            compatibility=contract["identity"]["compatibility_sha256"],
            source=False,
        )
        reset_b = request_observe(
            observed,
            session=session,
            request_id=3,
            transition=0,
            compatibility=contract["identity"]["compatibility_sha256"],
            source=False,
        )
        require(reset_a.payload_bytes == reset_b.payload_bytes, "reset observations are not byte-identical")
        reset_snapshot = request_snapshot(observed, session, 4, 0)
        require(reset_snapshot.payload["snapshot"] == observed_reset.payload["snapshot"], "reset observation perturbed snapshot")

        observed_step = request_step_setup(observed, session, 5, boundary)
        control_step = request_step_setup(control, session, 2, boundary)
        require(observed_step.payload["snapshot"] == control_step.payload["snapshot"], "pre-step observations perturbed engine result")
        setup_before = request_snapshot(observed, session, 6, 1)
        full_a = request_observe(
            observed,
            session=session,
            request_id=7,
            transition=1,
            compatibility=contract["identity"]["compatibility_sha256"],
            source=True,
        )
        full_b = request_observe(
            observed,
            session=session,
            request_id=8,
            transition=1,
            compatibility=contract["identity"]["compatibility_sha256"],
            source=True,
        )
        require(full_a.payload_bytes == full_b.payload_bytes, "setup observations are not byte-identical")
        setup_after = request_snapshot(observed, session, 9, 1)
        control_snapshot = request_snapshot(control, session, 3, 1)
        require(setup_before.payload["snapshot"] == setup_after.payload["snapshot"], "OBSERVE perturbed setup snapshot")
        require(setup_after.payload["snapshot"] == control_snapshot.payload["snapshot"], "observed/control snapshots differ")

        wrong = request_observe(
            observed,
            session=session,
            request_id=10,
            transition=1,
            compatibility="0" * 64,
            source=False,
        )
        require(wrong.payload["status"] == "ERROR", "wrong observation identity was accepted")
        require(wrong.payload["error"]["code"] == "BAD_PAYLOAD", "wrong identity error class drifted")
        after_wrong = request_snapshot(observed, session, 11, 1)
        require(after_wrong.payload["snapshot"] == setup_after.payload["snapshot"], "identity rejection perturbed snapshot")

        observation = full_a.payload["observation"]
        structured_comparisons = validate_structured(observation, contract)
        spatial_comparisons, channel_sums = validate_spatial(observation)
        policy_observation = copy.deepcopy(observation)
        policy_observation.pop("source_projection")
        hashes = {}
        for consumer in contract["shared_preprocessing"]["consumers"]:
            candidate = observation if consumer == "m04-bridge-oracle" else policy_observation
            hashes[consumer] = m04_preprocessing.load_policy_tensors(
                candidate,
                consumer=consumer,
                contract=contract,
            ).sha256
        require(len(set(hashes.values())) == 1, "consumer tensor bytes differ")

        request_close(observed, session, 12, 1)
        request_close(control, session, 4, 1)
        observed_code, observed_stdout, observed_stderr = observed.finish(timeout)
        control_code, control_stdout, control_stderr = control.finish(timeout)
        require(observed_code == control_code == 0, "worker did not exit cleanly")
        require(observed_stderr == control_stderr == b"", "worker emitted stderr")
        return {
            "channel_sums": channel_sums,
            "consumer_tensor_sha256": hashes,
            "control_stdout": control_stdout.decode().strip(),
            "nonperturbation": "PASS",
            "observed_stdout": observed_stdout.decode().strip(),
            "post_setup_observation_sha256": hashlib.sha256(canonical_bytes(policy_observation)).hexdigest(),
            "post_setup_payload_bytes": full_a.payload_length,
            "post_setup_tensor_sha256": next(iter(hashes.values())),
            "reset_observation_sha256": hashlib.sha256(canonical_bytes(reset_a.payload["observation"])).hexdigest(),
            "semantic_comparisons": structured_comparisons + spatial_comparisons,
            "structured_comparisons": structured_comparisons,
            "spatial_comparisons": spatial_comparisons,
            "wrong_identity_rejected": True,
        }
    except Exception:
        for worker in (observed, control):
            if worker.process.poll() is None:
                worker.process.kill()
            worker.client.close_descriptors()
            worker.process.communicate()
        raise


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    executable = args.executable.resolve()
    instance_dir = args.instance_dir.resolve()
    artifact_root = args.artifact_root.resolve()
    require(executable.is_file(), f"executable does not exist: {executable}")
    require(instance_dir.is_dir(), f"instance directory does not exist: {instance_dir}")
    artifact_root.mkdir(parents=True, exist_ok=False)
    validate_native_delta(root)
    contract = validate_m04_observation_contract.validate(
        root / "config/v1/m04-observation-contract.json",
        root / "docs/project/schema/v1-m04-observation-contract.schema.json",
    )
    instances = sorted(instance_dir.glob("m02-template-*.json"))
    require(len(instances) == 8, "M04 oracle requires all eight M02 template instances")
    templates = []
    channel_positive = [0.0] * 32
    for index, instance in enumerate(instances, 1):
        result = run_template(
            executable=executable,
            instance=instance,
            run_root=artifact_root / "templates" / instance.stem,
            contract=contract,
            session=400 + index,
            timeout=args.timeout,
        )
        for channel, value in enumerate(result["channel_sums"]):
            channel_positive[channel] += value
        templates.append({"template_id": instance.stem, **result})
        print(f"M04_OBSERVATION_TEMPLATE=PASS template={instance.stem} tensor={result['post_setup_tensor_sha256']}")
    require(all(value > 0.0 for value in channel_positive), f"one or more spatial channels lack a positive actual-engine fixture: {channel_positive}")
    golden = {
        "compatibility_sha256": contract["identity"]["compatibility_sha256"],
        "schema_version": "openttd-rl-v1-m04-observation-goldens-1",
        "templates": [
            {
                "post_setup_observation_sha256": item["post_setup_observation_sha256"],
                "post_setup_tensor_sha256": item["post_setup_tensor_sha256"],
                "reset_observation_sha256": item["reset_observation_sha256"],
                "template_id": item["template_id"],
            }
            for item in templates
        ],
    }
    write_canonical_new(artifact_root / "goldens.json", golden)
    manifest = {
        "channel_positive_sums": channel_positive,
        "compatibility_sha256": contract["identity"]["compatibility_sha256"],
        "contract_sha256": sha256_file(root / "config/v1/m04-observation-contract.json"),
        "executable_sha256": sha256_file(executable),
        "goldens_sha256": hashlib.sha256(canonical_bytes(golden) + b"\n").hexdigest(),
        "nonperturbation": "PASS",
        "schema_version": "openttd-rl-v1-m04-observation-oracle-report-1",
        "status": "PASS",
        "templates": templates,
        "total_semantic_comparisons": sum(item["semantic_comparisons"] for item in templates),
    }
    report_schema_path = root / "docs/project/schema/v1-m04-observation-oracle-report.schema.json"
    require(sha256_file(report_schema_path) == REPORT_SCHEMA_SHA256, "M04 oracle report schema drifted")
    report_schema = validate_m04_observation_contract.load_strict_json(report_schema_path)
    jsonschema.Draft202012Validator.check_schema(report_schema)
    jsonschema.Draft202012Validator(report_schema).validate(manifest)
    write_canonical_new(artifact_root / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--instance-dir", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        manifest = run(args)
    except Exception as exc:
        print(f"M04_OBSERVATION_ORACLE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M04_OBSERVATION_ORACLE=PASS "
        f"templates={len(manifest['templates'])} comparisons={manifest['total_semantic_comparisons']} "
        f"executable_sha256={manifest['executable_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
