#!/usr/bin/env python3
"""Actual-engine M05 mask differential, transaction, and bus-service acceptance campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import random
import sys
from typing import Any

import jsonschema

import m03_bridge_protocol as protocol
import m05_action_adapter as adapter
import validate_m05_action_contract


BRIDGE_COMPATIBILITY_SHA256 = "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6"
M05_PATCH_SHA256 = "c512111713b3c03cd9d0fd6c621c69e1881f3aa837efc0d27e78e3f816a2d006"
M05_SERIES_SHA256 = "50d3a06c62bf3fe3535d06260142dcabcd7f5bdf4ad1d842099414b5345904c1"
M05_RESULT_TREE = "ad0575b92f7975ef085e5f35bfe182a504d6cb51"
M05_COMPOSED_SOURCE_IDENTITY = "9bb57367151fbf4eedcd802d179c946685a911bec9b99d7573501e0f52a3b2bd"
M04_RESULT_TREE = "fe815570b5c816c6b324a9bf63d965157ea425c6"
M04_COMPOSED_SOURCE_IDENTITY = "820cf3ee0fb36734c318cb260e6cc4567a2a9acc55c831d5b36d1875341b291e"
REPORT_SCHEMA_SHA256 = "76ad4019a9291e9efac70628424ba4855d352c7ad3dffa952f96776f9626e331"


class M05ActionOracleError(ValueError):
    """Actual engine behavior violated the frozen M05 action contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M05ActionOracleError(message)


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
        raise M05ActionOracleError(f"refusing to overwrite {path}")
    path.write_bytes(canonical_bytes(value) + b"\n")


def validate_native_delta(root: pathlib.Path) -> None:
    directory = root / "integration/openttd/patches/15.3/m05"
    patch = directory / "0006-explicit-bus-actions-and-masks.patch"
    series = directory / "series"
    require(patch.is_file() and not patch.is_symlink(), "M05 patch is not a regular file")
    require(series.is_file() and not series.is_symlink(), "M05 series is not a regular file")
    require(sha256_file(patch) == M05_PATCH_SHA256, "M05 patch digest drifted")
    require(sha256_file(series) == M05_SERIES_SHA256, "M05 series digest drifted")
    require(series.read_text(encoding="utf-8") == patch.name + "\n", "M05 series inventory drifted")


class Controller:
    def __init__(self, worker: protocol.WorkerProcess, session: int) -> None:
        self.worker = worker
        self.session = session
        self.request_id = 0
        self.transition = 0
        self.boundary = ""
        self.last_mask: dict[str, Any] | None = None
        self.last_mask_token = ""

    def _request(self, message_type: int, transition: int, payload: dict[str, Any]) -> protocol.Frame:
        self.request_id += 1
        return self.worker.client.request(
            message_type=message_type,
            session_id=self.session,
            episode_id=0 if message_type == protocol.RESET else 1,
            request_id=self.request_id,
            transition_ordinal=transition,
            payload=payload,
        )

    def reset(self) -> dict[str, Any]:
        frame = self._request(protocol.RESET, 0, {"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY_SHA256})
        require(frame.payload["status"] == "OK", "RESET failed")
        self.transition = 0
        self.boundary = frame.payload["snapshot"]["boundary_token"]
        return frame.payload["snapshot"]

    def snapshot(self) -> dict[str, Any]:
        frame = self._request(protocol.SNAPSHOT, self.transition, {})
        require(frame.payload["status"] == "OK", "SNAPSHOT failed")
        return frame.payload["snapshot"]

    def mask(self, *, include_source: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
        frame = self._request(
            protocol.LEGAL_ACTIONS,
            self.transition,
            {
                "action_compatibility_sha256": adapter.ACTION_COMPATIBILITY_SHA256,
                "include_source_projection": include_source,
            },
        )
        require(frame.payload["status"] == "OK", "LEGAL_ACTIONS failed")
        mask = frame.payload["mask"]
        legal = adapter.validate_mask(mask)
        if include_source:
            oracle = adapter.independent_oracle_mask(mask["source_projection"])
            require(legal == oracle, f"native/oracle mask mismatch native={legal} oracle={oracle}")
        self.boundary = frame.payload["boundary_token"]
        self.last_mask = mask
        self.last_mask_token = frame.payload["mask_token"]
        return frame.payload, mask

    def step(
        self,
        action_index: int,
        *,
        injected_failure: str | None = None,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        require(self.last_mask is not None, "STEP requires a mask query")
        payload = {
            "action_compatibility_sha256": adapter.ACTION_COMPATIBILITY_SHA256,
            "action_index": action_index,
            "boundary_token": self.boundary,
            "bridge_compatibility_sha256": BRIDGE_COMPATIBILITY_SHA256,
            "inject_native_failure": injected_failure,
            "mask_token": self.last_mask_token,
        }
        frame = self._request(protocol.STEP, self.transition + 1, payload)
        require(frame.payload["status"] == "OK", f"STEP returned protocol error: {frame.payload}")
        outcome = frame.payload["action_outcome"]
        if expected_status is not None:
            require(outcome["status"] == expected_status, f"expected {expected_status}, got {outcome['status']}")
        if outcome["status"] == "ILLEGAL_INPUT":
            require(frame.payload["advanced_ticks"] == 0, "ILLEGAL_INPUT advanced ticks")
            return frame.payload
        require(frame.payload["advanced_ticks"] == 128, "accepted M05 action did not advance exactly 128 ticks")
        self.transition += 1
        self.boundary = frame.payload["post_boundary_token"]
        self.last_mask = None
        self.last_mask_token = ""
        self._validate_action_log(outcome)
        return frame.payload

    @staticmethod
    def _validate_action_log(outcome: dict[str, Any]) -> None:
        require(outcome["schema_version"] == "openttd-rl-v1-m05-action-result-1", "action result schema drifted")
        commands = outcome["native_commands"]
        for command in commands:
            require(
                set(command) == {"command", "cost", "error_message_id", "extra_error_message_id", "phase", "status"},
                "native command log field inventory drifted",
            )
        execute_cost = sum(command["cost"] for command in commands if command["phase"] == "EXECUTE" and command["status"] == "SUCCESS")
        rollback_cost = sum(command["cost"] for command in commands if command["phase"] == "ROLLBACK" and command["status"] == "SUCCESS")
        require(
            outcome["balance_before"] - outcome["balance_after"] == execute_cost + rollback_cost,
            f"balance delta does not match native costs for {outcome['family']}",
        )
        require(outcome["tick_before_command"] == outcome["tick_after_command"], "command phase advanced a simulation tick")

    def close(self) -> None:
        frame = self._request(protocol.CLOSE, self.transition, {})
        require(frame.payload["status"] == "OK", "CLOSE failed")


def exercise_rejections(controller: Controller) -> dict[str, Any]:
    before = controller.snapshot()
    wrong = controller._request(
        protocol.LEGAL_ACTIONS,
        controller.transition,
        {"action_compatibility_sha256": "0" * 64, "include_source_projection": False},
    )
    require(wrong.payload["status"] == "ERROR" and wrong.payload["error"]["code"] == "BAD_PAYLOAD", "wrong identity was accepted")
    require(controller.snapshot() == before, "wrong identity rejection mutated the snapshot")

    first_payload, first_mask = controller.mask()
    second_payload, second_mask = controller.mask()
    require(first_mask == second_mask, "repeated mask query is not byte-identical")
    require(first_payload["mask_token"] == second_payload["mask_token"], "repeated mask token drifted")
    before = controller.snapshot()
    stale_payload = {
        "action_compatibility_sha256": adapter.ACTION_COMPATIBILITY_SHA256,
        "action_index": 0,
        "boundary_token": "stale-boundary",
        "bridge_compatibility_sha256": BRIDGE_COMPATIBILITY_SHA256,
        "inject_native_failure": None,
        "mask_token": controller.last_mask_token,
    }
    stale = controller._request(protocol.STEP, controller.transition + 1, stale_payload)
    require(stale.payload["status"] == "ERROR" and stale.payload["error"]["code"] == "STALE_REJECTED", "stale boundary was not classified")
    require(controller.snapshot() == before, "stale rejection mutated the snapshot")

    _, mask = controller.mask()
    illegal = next(index for index in range(4, 12) if not mask["legal"][index])
    before = controller.snapshot()
    result = controller.step(illegal, expected_status="ILLEGAL_INPUT")
    require(result["snapshot"] == before, "ILLEGAL_INPUT mutated snapshot")
    require(controller.snapshot() == before, "ILLEGAL_INPUT changed committed snapshot")
    return {
        "illegal_index": illegal,
        "repeated_mask_identical": True,
        "stale_rejected": True,
        "wrong_identity_rejected": True,
    }


def legal_step(controller: Controller, index: int, *, injected_failure: str | None = None, expected: str = "SUCCESS") -> dict[str, Any]:
    _, mask = controller.mask()
    require(mask["legal"][index] == 1, f"scripted action {index} is masked at transition {controller.transition}")
    return controller.step(index, injected_failure=injected_failure, expected_status=expected)


def run_scripted_template(
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    session: int,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=run_root, timeout=timeout)
    controller = Controller(worker, session)
    action_logs: list[dict[str, Any]] = []
    try:
        reset = controller.reset()
        rejection = exercise_rejections(controller)
        action_logs.append(legal_step(controller, 1)["action_outcome"])
        action_logs.append(legal_step(controller, 3)["action_outcome"])
        _, mask = controller.mask()
        source = mask["source_projection"]
        for stop in source["stops"]:
            index = 4 + stop["town_slot"] * 4 + stop["expected_direction"]
            action_logs.append(controller.step(index, expected_status="SUCCESS")["action_outcome"])
            controller.mask()
        depot_index = 12 + source["depot"]["expected_direction"]
        action_logs.append(controller.step(depot_index, expected_status="SUCCESS")["action_outcome"])
        action_logs.append(legal_step(controller, 16)["action_outcome"])

        failed = legal_step(controller, 17, injected_failure="route-after-first-order", expected="NATIVE_REJECTED")
        action_logs.append(failed["action_outcome"])
        require(failed["action_outcome"]["rolled_back"], "injected route failure did not report rollback")
        _, after_failure = controller.mask()
        require(after_failure["source_projection"]["vehicles"][0]["orders"] == [], "route rollback did not restore empty orders")
        action_logs.append(controller.step(17, expected_status="SUCCESS")["action_outcome"])

        action_logs.append(legal_step(controller, 2)["action_outcome"])
        action_logs.append(legal_step(controller, 17)["action_outcome"])
        _, reverse_mask = controller.mask()
        reverse_source = reverse_mask["source_projection"]
        reverse_target = [reverse_source["stops"][1]["station_id"], reverse_source["stops"][0]["station_id"]]
        require(reverse_source["vehicles"][0]["orders"] == reverse_target, "reverse route update order mismatch")
        action_logs.append(controller.step(1, expected_status="SUCCESS")["action_outcome"])
        action_logs.append(legal_step(controller, 17)["action_outcome"])

        action_logs.append(legal_step(controller, 25)["action_outcome"])
        action_logs.append(legal_step(controller, 33)["action_outcome"])
        action_logs.append(legal_step(controller, 25)["action_outcome"])

        snapshot = action_logs and controller.snapshot()
        wait_actions = 0
        while snapshot["company"]["delivered_passengers"] == 0 or snapshot["company"]["income"] <= 0:
            require(controller.transition < 511, "scripted policy exhausted the M05 action horizon before passenger revenue")
            wait_result = legal_step(controller, 0, expected="NO_OP")
            if wait_actions == 0:
                action_logs.append(wait_result["action_outcome"])
            wait_actions += 1
            snapshot = controller.snapshot()

        _, final_mask = controller.mask()
        final_source = final_mask["source_projection"]
        require(snapshot["pools"]["stations"] == 2 and snapshot["pools"]["depots"] == 1 and snapshot["pools"]["vehicles"] == 1, "final entity counts drifted")
        require(final_source["connector"]["built"] and final_source["depot"]["present"], "road/depot lifecycle incomplete")
        require(all(stop["station_id"] >= 0 for stop in final_source["stops"]), "bus stop lifecycle incomplete")
        require(final_source["connector"]["start_owner"] >= 0 and final_source["connector"]["end_owner"] == 0, "connector ownership mismatch")
        require(final_source["depot"]["owner"] == 0 and all(stop["owner"] == 0 for stop in final_source["stops"]), "facility ownership mismatch")
        require(final_source["vehicles"][0]["present"] and final_source["vehicles"][0]["running"], "bus did not finish running")
        require(final_source["vehicles"][0]["orders"] == [final_source["stops"][0]["station_id"], final_source["stops"][1]["station_id"]], "final route order mismatch")
        controller.close()
        code, stdout, stderr = worker.finish(timeout)
        require(code == 0 and stderr == b"", f"scripted worker failed code={code} stderr={stderr.decode(errors='replace')}")
        return {
            "action_families": sorted({item["family"] for item in action_logs}),
            "action_log_sha256": hashlib.sha256(canonical_bytes(action_logs)).hexdigest(),
            "delivered_passengers": snapshot["company"]["delivered_passengers"],
            "final_balance": snapshot["company"]["balance"],
            "income": snapshot["company"]["income"],
            "mask_differential_states": controller.transition + 8,
            "native_command_count": sum(len(item["native_commands"]) for item in action_logs),
            "rejections": rejection,
            "route_rollback": "PASS",
            "stdout": stdout.decode().strip(),
            "transitions": controller.transition,
            "wait_actions": wait_actions,
        }
    except Exception:
        if worker.process.poll() is None:
            worker.process.kill()
        worker.client.close_descriptors()
        worker.process.communicate()
        raise


def run_randomized_template(
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    session: int,
    timeout: float,
    seed: int,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=run_root, timeout=timeout)
    controller = Controller(worker, session)
    rng = random.Random(seed)
    selected: list[int] = []
    try:
        controller.reset()
        for step in range(32):
            _, mask = controller.mask()
            logits = [math.sin((step + 1) * (index + 3)) * 8.0 for index in range(41)]
            distribution = adapter.masked_distribution(logits, mask, consumer="m05-oracle")
            index = adapter.sample_action(distribution, rng.random())
            require(mask["legal"][index] == 1, "shared sampler selected a masked action")
            result = controller.step(index)
            require(result["action_outcome"]["status"] in ("SUCCESS", "NO_OP"), "random legal action was rejected")
            selected.append(index)
        controller.close()
        code, stdout, stderr = worker.finish(timeout)
        require(code == 0 and stderr == b"", "randomized worker failed")
        return {
            "action_indices": selected,
            "action_indices_sha256": hashlib.sha256(canonical_bytes(selected)).hexdigest(),
            "mask_differential_states": 32,
            "seed": seed,
            "stdout": stdout.decode().strip(),
        }
    except Exception:
        if worker.process.poll() is None:
            worker.process.kill()
        worker.client.close_descriptors()
        worker.process.communicate()
        raise


def run_integration_failure(
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=run_root, timeout=timeout)
    controller = Controller(worker, 7001)
    try:
        reset = controller.reset()
        controller.mask()
        frame = controller._request(
            protocol.STEP,
            1,
            {
                "action_compatibility_sha256": adapter.ACTION_COMPATIBILITY_SHA256,
                "action_index": 0,
                "boundary_token": controller.boundary,
                "bridge_compatibility_sha256": BRIDGE_COMPATIBILITY_SHA256,
                "inject_native_failure": "unsupported-oracle-hook",
                "mask_token": controller.last_mask_token,
            },
        )
        require(frame.payload["status"] == "ERROR", "integration failure hook was accepted")
        require(frame.payload["error"]["code"] == "INTEGRATION_FAILURE", "integration failure outcome class drifted")
        require(frame.payload["error"]["fatal"] and frame.payload["error"]["lifecycle"] == "FAILED", "integration failure did not fail the worker")
        require(frame.transition_ordinal == 0 and reset["tick"] == 0, "integration failure committed a transition")
        controller.close()
        code, stdout, stderr = worker.finish(timeout)
        require(code == 0 and stderr == b"", "failed worker did not close cleanly")
        return {"classification": "INTEGRATION_FAILURE", "fatal": True, "stdout": stdout.decode().strip(), "transition_ordinal": 0}
    except Exception:
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
    contract = validate_m05_action_contract.validate(
        root / "config/v1/m05-action-contract.json",
        root / "docs/project/schema/v1-m05-action-contract.schema.json",
    )
    instances = sorted(instance_dir.glob("m02-template-*.json"))
    require(len(instances) == 8, "M05 campaign requires all eight frozen M02 templates")
    templates = []
    for number, instance in enumerate(instances, 1):
        scripted = run_scripted_template(
            executable, instance, artifact_root / "templates" / instance.stem / "scripted", 5000 + number, args.timeout
        )
        randomized = run_randomized_template(
            executable, instance, artifact_root / "templates" / instance.stem / "randomized", 6000 + number, args.timeout, 0x4D303500 + number
        )
        templates.append({"template_id": instance.stem, "scripted": scripted, "randomized": randomized})
        print(f"M05_ACTION_TEMPLATE=PASS template={instance.stem} transitions={scripted['transitions']} income={scripted['income']}")
    required_families = {
        "WAIT", "SELECT_TOWNS", "BUILD_ROAD_CONNECTOR", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT",
        "BUY_BUS", "ASSIGN_ROUTE", "SET_RUNNING", "SET_STOPPED",
    }
    observed_families = {family for item in templates for family in item["scripted"]["action_families"]}
    require(observed_families == required_families, f"actual engine family coverage drifted: {observed_families}")
    integration_failure = run_integration_failure(
        executable,
        instances[0],
        artifact_root / "integration-failure",
        args.timeout,
    )
    manifest = {
        "action_compatibility_sha256": contract["identity"]["compatibility_sha256"],
        "action_contract_sha256": sha256_file(root / "config/v1/m05-action-contract.json"),
        "action_families_covered": sorted(observed_families),
        "executable_sha256": sha256_file(executable),
        "integration_failure": integration_failure,
        "mask_differential_states": sum(item["scripted"]["mask_differential_states"] + item["randomized"]["mask_differential_states"] for item in templates),
        "schema_version": "openttd-rl-v1-m05-action-oracle-report-1",
        "status": "PASS",
        "templates": templates,
    }
    report_schema_path = root / "docs/project/schema/v1-m05-action-oracle-report.schema.json"
    require(sha256_file(report_schema_path) == REPORT_SCHEMA_SHA256, "M05 oracle report schema drifted")
    report_schema = validate_m05_action_contract.load_strict_json(report_schema_path)
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
        print(f"M05_ACTION_ORACLE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M05_ACTION_ORACLE=PASS "
        f"templates={len(manifest['templates'])} mask_states={manifest['mask_differential_states']} "
        f"executable_sha256={manifest['executable_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
