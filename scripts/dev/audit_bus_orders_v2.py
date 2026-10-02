#!/usr/bin/env python3
"""Independent packet, native-state, actual-input and unique-choice bus audit.

This is a training-fit audit of the explicitly selected manual recording, never
held-out evaluation. Packet decoding below is independent of the importer.
"""
import argparse
from collections import Counter, defaultdict
import copy
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import time

from audit_action_inputs_v2 import (PROBABILITY_TOLERANCE, artifact, checked,
    check_labels, native_aliases, parameter_row, prediction_result, reverse_legal_rows)
from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient
from local import capture_source, host, source_identity, write_json

MODES = ("signed-log-orders-v1", "signed-log-orders-v2")
# Retain the original input-audit import for archived diagnostic wrappers.
MODE = MODES[0]
SCHEMA = "v2-m15-public-development-orders-v1"
CHECKPOINT = "Fluningbury Transport, 1958-06-18.sav"
EXPECTED = {20: "BUY_BUS", 21: "INSERT_ORDER", 22: "INSERT_ORDER", 23: "FULL_LOAD_ANY",
            24: "FULL_LOAD_ANY", 25: "START_VEHICLE", 29: "BUY_BUS", 35: "COPY_ORDERS",
            36: "DELETE_ORDER", 37: "INSERT_ORDER", 38: "FULL_LOAD_ANY", 39: "START_VEHICLE"}
VEHICLE_OFFSET = 1286927


def public_order_tensor(state, data):
    """Compare actual float32 vehicle inputs to independently projected public state."""
    if len(data) != 2182927 or struct.unpack_from("<f", data, 511 * 4)[0] != 1:
        raise ValueError("Order observation binary schema marker differs")
    vehicles = sorted(state["vehicles"], key=lambda vehicle: vehicle["id"])
    exact = order_inventory(state)
    result = []
    for row, vehicle in enumerate(vehicles):
        if data[VEHICLE_OFFSET + 1024 * 40 * 4 + row] != 1:
            raise ValueError("Public own vehicle is masked from policy input")
        orders = exact[vehicle["id"]]
        expected = [float(vehicle["stopped"]), vehicle["cargo_count"] / 65535, vehicle["cargo_capacity"] / 65535,
                    len(orders) / 4, vehicle["current_real_order_index"] / 255,
                    vehicle["current_implicit_order_index"] / 255, vehicle["current_order_type"] / 255]
        if len(orders) > 4:
            raise ValueError("Public order sequence exceeds schema capacity")
        for index in range(4):
            if index < len(orders):
                raw = orders[index]
                expected += [int.from_bytes(bytes(raw[:2]), "little") / 65535,
                             int.from_bytes(bytes(raw[2:4]), "little") / 65535,
                             int.from_bytes(bytes(raw[5:7]), "little") / 65535,
                             int.from_bytes(bytes(raw[7:9]), "little") / 65535]
            else:
                expected += [0] * 4
        expected += [vehicle["current_order_destination"] / 65535,
                     math.log1p(vehicle["current_order_time"]) / math.log1p(0xFFFFFFFF), float(vehicle["orders_shared"]), 0]
        actual = struct.unpack_from("<27f", data, VEHICLE_OFFSET + (row * 40 + 13) * 4)
        if any(not math.isclose(a, b, rel_tol=2e-7, abs_tol=1e-10) for a, b in zip(actual, expected, strict=True)):
            raise ValueError("Actual vehicle input differs from public identity-ordered order state")
        result.append({"vehicle_id": vehicle["id"], "row": row, "columns_13_39": actual})
    return result


def decode_packet(event):
    """Pinned 15.3 command serialization, including all meaningful order bytes."""
    data = bytes.fromhex(event["payload"])
    name = event["name"]
    command_ids = {"CmdBuildVehicle": 34, "CmdStartStopVehicle": 120, "CmdInsertOrder": 46,
                   "CmdModifyOrder": 43, "CmdCloneOrder": 84, "CmdDeleteOrder": 45}
    if "command" in event and event["command"] != command_ids.get(name):
        raise ValueError("Recorded command name/id disagreement")
    integer = lambda offset, count: int.from_bytes(data[offset:offset + count], "little")
    if name == "CmdBuildVehicle" and len(data) == 12 and data[6:8] == bytes([1, 255]):
        return "BUY_BUS", [5, integer(0, 4), integer(4, 2), 0]
    if name == "CmdStartStopVehicle" and len(data) == 5 and data[4] == 0:
        return "START_VEHICLE", [7, integer(0, 4), 0, 0]
    if name == "CmdInsertOrder" and len(data) == 16:
        raw = data[5:]
        if raw[0] not in (0x21, 0x61) or raw[1] != 0 or raw[4:] != bytes([254, 0, 0, 0, 0, 255, 255]):
            raise ValueError("Unsupported inserted order variant")
        return "INSERT_ORDER", [6, integer(0, 4), 1 | data[4] << 8 | raw[0] << 16 | raw[1] << 24,
                                int.from_bytes(raw[2:4], "little")]
    if name == "CmdModifyOrder" and len(data) == 8 and data[5] == 3 and integer(6, 2) == 3:
        return "FULL_LOAD_ANY", [6, integer(0, 4), 2 | data[4] << 8 | 3 << 16, 3]
    if name == "CmdCloneOrder" and len(data) == 9 and data[0] == 1:
        return "COPY_ORDERS", [6, integer(1, 4), 3, integer(5, 4)]
    if name == "CmdDeleteOrder" and len(data) == 5:
        return "DELETE_ORDER", [6, integer(0, 4), 4 | data[4] << 8, 0]
    raise ValueError("Unsupported demonstrated packet")


def categorical_inputs(document):
    """Verify native v2 categories from public parameters, independent of labels."""
    counts = Counter()
    for row in document["rows"]:
        if row["family"] != 6:
            continue
        _, _, descriptor, value = row["parameters"][:4]
        operation, index = descriptor & 255, (descriptor >> 8) & 255
        if operation not in (1, 2, 3, 4) or (operation != 3 and index >= 4):
            raise ValueError("Invalid categorical order operation/index")
        expected = [0] * 12
        expected[operation - 1] = 1
        if operation == 2:
            if value not in (0, 2, 3, 4):
                raise ValueError("Invalid categorical order loading mode")
            expected[{0: 4, 2: 5, 3: 6, 4: 7}[value]] = 1
        if operation != 3:
            expected[8 + index] = 1
        if row["features"][:12] != expected:
            raise ValueError("Native categorical input differs from public operation/loading/index")
        counts[str(operation)] += 1
    return dict(counts)


def order_inventory(state):
    result = {}
    for vehicle in state["exact_orders"]:
        identity = vehicle["vehicle_id"]
        if identity in result:
            raise ValueError("Duplicate vehicle in exact order inventory")
        orders = []
        for order in vehicle["orders"]:
            raw = order["serialized"]
            if len(raw) != 11 or any(type(x) is not int or not 0 <= x <= 255 for x in raw):
                raise ValueError("Invalid complete serialized order")
            if raw[0] & 15 != order["type"] or int.from_bytes(bytes(raw[2:4]), "little") != order["destination"]:
                raise ValueError("Order summary disagrees with serialized bytes")
            orders.append(list(raw))
        result[identity] = orders
    return result


def route_status(state, vehicle_id):
    vehicles = {v["id"]: v for v in state["vehicles"]}
    orders = order_inventory(state).get(vehicle_id, [])
    route = [int.from_bytes(bytes(order[2:4]), "little") for order in orders if order[0] & 15 == 1]
    load = [(order[1] >> 4) & 7 for order in orders]
    vehicle = vehicles.get(vehicle_id)
    return {"vehicle_id": vehicle_id, "route": route, "load_modes": load,
            "both_endpoints_full_load_any": len(orders) == 2 and len(route) == 2 and load == [3, 3],
            "stopped": vehicle["stopped"] if vehicle else None,
            "cargo_count": vehicle["cargo_count"] if vehicle else None,
            "cargo_capacity": vehicle["cargo_capacity"] if vehicle else None}


def semantic_transition(event, before, after):
    operation, params = decode_packet(event)
    old, new = order_inventory(before), order_inventory(after)
    expected = copy.deepcopy(old)
    before_vehicles, after_vehicles = ({v["id"]: v for v in state["vehicles"]} for state in (before, after))
    _, target, packed, value = params
    index = (packed >> 8) & 255
    detail = {"operation": operation, "parameters": params}
    if operation == "BUY_BUS":
        added = set(new) - set(old)
        if len(added) != 1 or set(old) - set(new):
            raise ValueError("Purchase must add exactly one bus")
        identity = added.pop()
        expected[identity] = []
        if not after_vehicles[identity]["stopped"]:
            raise ValueError("Purchased bus unexpectedly running")
        detail["created_vehicle_id"] = identity
    else:
        if target not in old:
            raise ValueError("Action targets absent vehicle")
        if operation == "INSERT_ORDER":
            if index > len(old[target]):
                raise ValueError("Insertion index outside list")
            expected[target].insert(index, list(bytes.fromhex(event["payload"])[5:]))
        elif operation == "FULL_LOAD_ANY":
            if index >= len(old[target]):
                raise ValueError("Load index outside list")
            # Only load bits may change. Nonstop/type/unload/timetable remain exact.
            expected[target][index][1] = (expected[target][index][1] & ~0x70) | 0x30
        elif operation == "COPY_ORDERS":
            if value not in old or value == target:
                raise ValueError("Invalid source vehicle for independent copy")
            expected[target] = copy.deepcopy(old[value])
            if after_vehicles[target].get("orders_shared") is not False:
                raise ValueError("Copy must expose and produce independent orders")
        elif operation == "DELETE_ORDER":
            if index >= len(old[target]):
                raise ValueError("Delete would declone rather than delete an order")
            expected[target].pop(index)
        elif operation == "START_VEHICLE":
            if not before_vehicles[target]["stopped"] or after_vehicles[target]["stopped"]:
                raise ValueError("Start must change the exact stopped bus to running")
            detail["before_start"] = route_status(before, target)
    if expected != new:
        raise ValueError(f"{operation} native orders differ from exact packet semantics")
    for identity, vehicle in before_vehicles.items():
        if operation != "START_VEHICLE" or identity != target:
            if after_vehicles[identity]["stopped"] != vehicle["stopped"]:
                raise ValueError("Command unexpectedly changes another running/stopped state")
    return detail


def summarize(rows):
    by_operation = defaultdict(list)
    for row in rows:
        by_operation[row["operation"]].append(row)
    def one(items):
        return {"examples": len(items), "exact_rows": sum(x["prediction"]["exact_row"] for x in items),
                "unique_exact": sum(x["prediction"]["unique_greedy_target"] and not x["input"]["target_alias_rows"] for x in items),
                "input_alias_groups": sum(len(x["input"]["alias_groups"]) for x in items),
                "target_input_aliases": sum(bool(x["input"]["target_alias_rows"]) for x in items),
                "target_ties": sum(bool(x["prediction"]["target_near_tie_rows"]) for x in items),
                "minimum_margin": min(x["prediction"]["target_margin"] for x in items),
                "permuted_unique_exact": sum(x["permuted_prediction"]["unique_greedy_target"] for x in items),
                "permuted_minimum_margin": min(x["permuted_prediction"]["target_margin"] for x in items),
                "permutation_max_probability_error": max(x["permutation_probability_max_error"] for x in items)}
    return {"overall": one(rows), "by_operation": {name: one(items) for name, items in sorted(by_operation.items())}}


def check_replay(replay):
    report = json.loads((replay / "report.json").read_text())
    config = json.loads((replay / "config.json").read_text())
    if report["status"] != "passed" or report.get("checkpoint") != CHECKPOINT or report.get("checkpoint_occurrence") != "latest":
        raise ValueError("Audit requires the verified later manual checkpoint")
    if config["events"][-1]["kind"] != "checkpoint" or config["events"][-1]["line"] != 47:
        raise ValueError("Replay ends at another recording marker")
    for path, digest in report["inputs"].items():
        checked({"path": path, "sha256": digest})
    log_paths = [Path(path) for path in report["inputs"] if Path(path).name == "commands-out.log"]
    if len(log_paths) != 1:
        raise ValueError("Original command recording absent or ambiguous")
    raw_lines = log_paths[0].read_text(encoding="utf-8-sig").splitlines()
    recorded = {event["line"]: event for event in config["events"]}
    for line in EXPECTED:
        match = re.fullmatch(r"\[[^]]+\] cmd: ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+) \(([^)]+)\)", raw_lines[line - 1], re.I)
        if not match:
            raise ValueError("Expected label is not a confirmed original command")
        fields = match.groups()
        source = {key: int(value, 16) for key, value in zip(("date", "fraction", "company", "command", "message"), fields[:5])}
        source.update(payload=fields[5].lower(), name=fields[6])
        if any((recorded[line][key].lower() if key == "payload" else recorded[line][key]) != value for key, value in source.items()):
            raise ValueError("Replay event differs from original command log")
    manual_markers = [number for number, raw in enumerate(raw_lines, 1) if "] save: " in raw and raw.replace("\\", "/").endswith("/" + CHECKPOINT)]
    if not manual_markers or manual_markers[-1] != 47:
        raise ValueError("Original latest manual marker differs")
    a, b = (json.loads((replay / name).read_text()) for name in ("replayed.json", "checkpoint.json"))
    for key in ("exact_orders", "vehicles", "stations", "depots", "economy", "date", "date_fraction", "tick"):
        if a[key] != b[key]:
            raise ValueError("Native checkpoint mismatch: " + key)
    if a["map"]["roads"] != b["map"]["roads"]:
        raise ValueError("Native checkpoint roads mismatch")
    commands = [json.loads(line) for line in (replay / "commands.jsonl").read_text().splitlines()]
    for command in commands:
        if not command["succeeded"] or command["after_cash"] - command["before_cash"] != command["after_loan"] - command["before_loan"] - command["command_cost"]:
            raise ValueError("Native command accounting mismatch")
    supported = [c["source_command_index"] for c in commands if c["supported_policy_label"]]
    if supported != sorted(EXPECTED):
        raise ValueError("Supported command inventory differs from independently decoded demonstration")
    return config, {"commands": len(commands), "supported": len(supported), "new_order_decisions": 8,
        "excluded_successful_commands": len(commands) - len(supported), "exclusions": dict(Counter(x["reason"] for x in report["exclusions"])),
        "final_cash": a["economy"]["balance"], "final_loan": a["economy"]["loan"],
        "final_routes": [route_status(a, identity) for identity in (1, 2)]}


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "independent-bus-order-audit", "status": "running", "source": source_identity(),
              "runtime": host(), "device": "cpu", "seed": 20261002,
              "observation_schema_id": SCHEMA, "claim": "One-recording training fit and native semantics; no generalization claim",
              "rows": [], "configuration": {"minimum_margin_exclusive": 1e-6, "permutation": "reverse complete legal records within family"}}
    started, client = time.monotonic(), None
    try:
        record["source_capture"] = capture_source(output / "source")
        imitation, _ = checked_imitation_run(args.imitation_run, observation_schema=SCHEMA)
        mode = imitation["financial_features"]
        if mode not in MODES:
            raise ValueError("Bus audit requires a versioned orders preprocessing model")
        record["financial_features"] = mode
        labels, tensors, refs = check_labels(imitation)
        replay_ref = checked(imitation["dataset"]["replay_validation"])
        replay = Path(replay_ref["path"]).parent
        config, record["replay"] = check_replay(replay)
        events = {event["line"]: event for event in config["events"]}
        if [label["source_command_index"] for label in labels] != sorted(EXPECTED):
            raise ValueError("Training did not use all exact supported bus decisions")
        refs += [replay_ref, artifact(args.imitation_run / "run.json"), checked(imitation["model"]),
                 artifact(args.audit_executable), artifact(args.policy)]
        record["inputs"] = refs
        client = PolicyClient(args.policy.resolve(), output / "policy.log", "cpu", 20261002,
                              mode="greedy", weights=Path(imitation["model"]["path"]), financial_features=mode)
        client.check_financial_features()
        with (output / "predictions.jsonl").open("x") as stream:
            for index, (label, pair) in enumerate(zip(labels, tensors)):
                line = label["source_command_index"]
                event = events[line]
                operation, parameters = decode_packet(event)
                data = Path(pair["candidate"]["path"]).read_bytes()
                actual_parameters = parameter_row(data, label["action_row"])
                if operation != EXPECTED[line] or actual_parameters != parameters + [0] * 12:
                    raise ValueError("Target tensor parameters differ from independently decoded human packet")
                before_path, after_path = Path(label["observation_path"]), Path(label["after_observation_path"])
                refs += [artifact(before_path), artifact(after_path)] + list(pair.values())
                before, after = (json.loads(path.read_text()) for path in (before_path, after_path))
                semantics = semantic_transition(event, before, after)
                if parameters[0] == 6:
                    probe_path = replay / f"native-semantic-command-{line}.json"
                    probe = json.loads(probe_path.read_text())
                    required_checks = {"candidate-executes", "exact-resulting-order-bytes", "unrelated-vehicles-unchanged",
                                       "out-of-range-delete-rejected-without-mutation", "invalid-vehicle-rejected-without-mutation"}
                    if operation == "COPY_ORDERS":
                        required_checks.add("copy-independent-after-source-mutation")
                    if operation == "FULL_LOAD_ANY":
                        required_checks |= {"full-load-any-distinct-from-full-load-all", "load-change-preserves-non-stop-unload-and-timetable"}
                    if (probe["status"] != "passed" or probe["parameters"] != actual_parameters or
                            not required_checks <= set(probe["checks"]) or
                            probe["before"] != {str(k): v for k, v in order_inventory(before).items()} or
                            probe["actual_after"] != {str(k): v for k, v in order_inventory(after).items()}):
                        raise ValueError("Candidate execution probe differs from independently checked recorded semantics")
                    semantics["candidate_execution_probe"] = artifact(probe_path)
                    semantics["candidate_execution_checks"] = probe["checks"]
                    refs.append(semantics["candidate_execution_probe"])
                observation_inputs = public_order_tensor(before, Path(pair["observation"]["path"]).read_bytes())
                native_path = output / f"{index:04d}-native-inputs.json"
                command = [str(args.audit_executable.resolve()), "--observation", pair["observation"]["path"],
                           "--candidates", pair["candidate"]["path"], "--financial-features", mode]
                with native_path.open("x") as stdout, native_path.with_suffix(".log").open("x") as stderr:
                    subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=60)
                native = json.loads(native_path.read_text())
                row = {"sample_id": label["sample_id"], "operation": operation, "semantics": semantics,
                       "public_order_inputs": observation_inputs,
                       "input": native_aliases(native, data, label), "native_input": artifact(native_path)}
                if mode == MODES[1]:
                    row["categorical_legal_order_counts"] = categorical_inputs(native)
                client.request("RESET")
                prediction = client.request(f"{pair['observation']['path']}\t{pair['candidate']['path']}")
                row["prediction"] = prediction_result(prediction, label)
                permuted_data, permutation = reverse_legal_rows(data, label)
                permuted_path = output / f"{index:04d}-permuted-candidates.bin"
                permuted_path.write_bytes(permuted_data)
                client.request("RESET")
                permuted = client.request(f"{pair['observation']['path']}\t{permuted_path}")
                row["permuted_prediction"] = prediction_result(permuted, label, permutation=permutation)
                row["permutation_probability_max_error"] = max(abs(prediction["probabilities"][old] - permuted["probabilities"][new]) for new, old in permutation.items())
                record["rows"].append(row)
                stream.write(json.dumps({"sample_id": label["sample_id"], "prediction": prediction, "permuted": permuted, "permutation": permutation}) + "\n")
                stream.flush()
        client.close(); client = None
        record["summary"] = summarize(record["rows"])
        starts = [row["semantics"]["before_start"] for row in record["rows"] if row["operation"] == "START_VEHICLE"]
        record["full_load_before_start"] = starts
        if [x["route"] for x in starts] != [[1, 0], [1, 2]] or not all(x["both_endpoints_full_load_any"] for x in starts):
            raise ValueError("Demonstrated starts are missing exact full-load routes")
        for ref in refs:
            checked(ref)
        record["inputs_unchanged"] = True
        summary = record["summary"]["overall"]
        if summary["unique_exact"] != len(labels) or summary["permuted_unique_exact"] != len(labels) or summary["input_alias_groups"] or summary["permutation_max_probability_error"] > PROBABILITY_TOLERANCE:
            raise ValueError("Policy has semantic aliases, nonunique mistakes or permutation instability")
        record["status"] = "passed"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        if client:
            client.abort()
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "report.json", record)
    print(json.dumps(record["summary"], sort_keys=True), flush=True)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imitation-run", type=Path, required=True)
    parser.add_argument("--audit-executable", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
