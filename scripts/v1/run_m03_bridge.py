#!/usr/bin/env python3
"""Run the native M03 lifecycle, determinism, isolation, and soak oracle."""

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

import generate_m02_scenario
import m03_bridge_protocol as protocol
import run_m02_reset_oracle
import validate_m02_reset_projection
import validate_m02_scenario_contract
import validate_m02_scripted_trajectory
import validate_m03_bridge_contract


class M03BridgeOracleError(ValueError):
    """A native bridge, lifecycle, determinism, or evidence guard failed."""


BRIDGE_COMPATIBILITY = "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6"
M03_PATCH_SHA256 = "6677d5a32abc5250394133e162236f1b2c5a9acfe19ea867a8b0512b10343c50"
M03_SERIES_SHA256 = "bb0f27f2bd530d89433dbf6b32fdbd4e63fed4e08224f8b190298f5185d7959e"
M03_RESULT_TREE = "39ed7069eca2c48c512a9bdd989c049aca3c5329"
M03_COMPOSED_SOURCE_IDENTITY = "d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1"
M02_BASE_COMPOSED_SOURCE_IDENTITY = "edc76541bfda23c2916fc85d499e6e0d5a5cefaad09f40bf19972c2d3307385e"
M03_REPORT_SCHEMA_SHA256 = "5f4e69c6414b15c92c43b5d9798edcc316ab5f01c7b6242460cf5b1666be5423"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M03BridgeOracleError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new_bytes(path: pathlib.Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise M03BridgeOracleError(f"output already exists: {path}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(value):
            offset += os.write(descriptor, value[offset:])
    finally:
        os.close(descriptor)


def write_canonical_new(path: pathlib.Path, value: dict[str, Any]) -> None:
    write_new_bytes(path, protocol.canonical_bytes(value) + b"\n")


def normalize_command(
    command: list[str],
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
) -> list[str]:
    normalized: list[str] = []
    for value in command:
        if value == str(executable):
            normalized.append("<runtime>/openttd")
        elif value == str(instance):
            normalized.append("<instance>")
        elif value == str(run_root / "openttd.cfg"):
            normalized.append("<run>/openttd.cfg")
        elif ":" in value and all(part.isdigit() for part in value.split(":")):
            normalized.append("<inherited-read-fd>:<inherited-write-fd>")
        else:
            normalized.append(value)
    return normalized


def expect_ok(frame: protocol.Frame, label: str) -> dict[str, Any]:
    require(frame.flags == protocol.FLAG_RESPONSE, f"{label}: response flags are not success")
    require(frame.payload.get("status") == "OK", f"{label}: response status is not OK")
    require(
        frame.payload.get("schema_version") == "openttd-rl-v1-m03-bridge-response-1",
        f"{label}: response schema version drifted",
    )
    return frame.payload


def expect_error(
    frame: protocol.Frame,
    code: str,
    label: str,
    *,
    fatal: bool = False,
) -> dict[str, Any]:
    require(
        frame.flags == protocol.FLAG_RESPONSE | protocol.FLAG_ERROR,
        f"{label}: response flags are not typed error",
    )
    require(frame.payload.get("status") == "ERROR", f"{label}: status is not ERROR")
    error = frame.payload.get("error")
    require(isinstance(error, dict), f"{label}: error payload is missing")
    require(error.get("code") == code, f"{label}: expected {code}, got {error.get('code')}")
    require(error.get("fatal") is fatal, f"{label}: fatal classification drifted")
    require(isinstance(error.get("message"), str) and error["message"], f"{label}: error message is empty")
    return error


def request(
    worker: protocol.WorkerProcess,
    *,
    message_type: int,
    session_id: int,
    episode_id: int,
    request_id: int,
    transition: int,
    payload: dict[str, Any],
) -> protocol.Frame:
    return worker.client.request(
        message_type=message_type,
        session_id=session_id,
        episode_id=episode_id,
        request_id=request_id,
        transition_ordinal=transition,
        payload=payload,
    )


def step_payload(
    action_id: int,
    boundary_token: str,
    action_interval_ticks: int = 128,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "action_interval_ticks": action_interval_ticks,
        "boundary_token": boundary_token,
        "bridge_compatibility_sha256": BRIDGE_COMPATIBILITY,
    }


def strip_control_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(snapshot)
    for field in (
        "boundary_token",
        "episode_id",
        "lifecycle",
        "session_id",
        "transition_ordinal",
    ):
        value.pop(field)
    return value


def strip_lifecycle(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(snapshot)
    value.pop("lifecycle")
    return value


def finish_worker(
    worker: protocol.WorkerProcess,
    run_root: pathlib.Path,
    executable: pathlib.Path,
    instance: pathlib.Path,
    timeout: float,
) -> dict[str, Any]:
    returncode, stdout, stderr = worker.finish(timeout)
    write_new_bytes(run_root / "stdout.txt", stdout)
    write_new_bytes(run_root / "stderr.txt", stderr)
    require(returncode == 0, f"worker exited {returncode}: {(stderr or stdout).decode(errors='replace')}")
    require(stderr == b"", f"worker wrote stderr: {stderr.decode(errors='replace')}")
    return {
        "command": normalize_command(worker.command, executable, instance, run_root),
        "returncode": returncode,
        "stderr_sha256": sha256_bytes(stderr),
        "stdout": stdout.decode("utf-8").rstrip("\n"),
        "stdout_sha256": sha256_bytes(stdout),
    }


def exercise_scripted_worker(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    session_id: int,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root,
        timeout=timeout,
    )
    next_request = 1
    try:
        frame = request(
            worker,
            message_type=protocol.SNAPSHOT,
            session_id=session_id,
            episode_id=0,
            request_id=next_request,
            transition=0,
            payload={},
        )
        expect_error(frame, "INVALID_LIFECYCLE", "snapshot-before-reset")
        next_request += 1

        frame = request(
            worker,
            message_type=protocol.RESET,
            session_id=session_id,
            episode_id=0,
            request_id=next_request,
            transition=0,
            payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
        )
        reset = expect_ok(frame, "reset")
        next_request += 1
        episode_id = reset["episode_id"]
        require(episode_id == 1, "first reset did not allocate episode 1")
        initial = reset["snapshot"]
        require(initial["tick"] == 0, "reset boundary tick is not zero")

        frame = request(
            worker,
            message_type=protocol.SNAPSHOT,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        queried = expect_ok(frame, "initial-snapshot")["snapshot"]
        next_request += 1
        require(queried == initial, "observation-only snapshot changed the reset boundary")

        frame = request(
            worker,
            message_type=protocol.LEGAL_ACTIONS,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        legal = expect_ok(frame, "initial-legal-actions")
        next_request += 1
        require([item["id"] for item in legal["legal_actions"]] == [0, 1], "initial legal action inventory drifted")
        require(legal["boundary_token"] == initial["boundary_token"], "snapshot/legal boundary token mismatch")

        frame = request(
            worker,
            message_type=protocol.SNAPSHOT,
            session_id=session_id + 1,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        expect_error(frame, "STALE_HANDLE", "stale-handle")
        next_request += 1

        frame = request(
            worker,
            message_type=protocol.PAUSE,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        paused = expect_ok(frame, "pause")
        next_request += 1
        require(paused["lifecycle"] == "PAUSED", "pause did not enter PAUSED")

        frame = request(
            worker,
            message_type=protocol.STEP,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=1,
            payload=step_payload(0, initial["boundary_token"]),
        )
        expect_error(frame, "INVALID_LIFECYCLE", "step-while-paused")
        next_request += 1

        frame = request(
            worker,
            message_type=protocol.SNAPSHOT,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        paused_snapshot = expect_ok(frame, "paused-snapshot")["snapshot"]
        next_request += 1
        require(
            strip_lifecycle(paused_snapshot) == strip_lifecycle(initial),
            "pause or invalid step perturbed engine state",
        )

        frame = request(
            worker,
            message_type=protocol.LEGAL_ACTIONS,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        paused_legal = expect_ok(frame, "paused-legal-actions")
        next_request += 1
        require(paused_legal["legal_actions"] == [], "PAUSED exposed step actions")

        frame = request(
            worker,
            message_type=protocol.RESUME,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        resumed = expect_ok(frame, "resume")
        next_request += 1
        require(resumed["lifecycle"] == "AT_BOUNDARY", "resume did not return to AT_BOUNDARY")

        frame = request(
            worker,
            message_type=protocol.STEP,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=1,
            payload=step_payload(1, "m03b1:stale"),
        )
        expect_error(frame, "STALE_BOUNDARY", "stale-boundary")
        next_request += 1

        frame = request(
            worker,
            message_type=protocol.SNAPSHOT,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={},
        )
        after_stale = expect_ok(frame, "snapshot-after-stale")["snapshot"]
        next_request += 1
        require(after_stale == initial, "stale boundary request perturbed engine state")

        trace: list[dict[str, Any]] = []
        frame = request(
            worker,
            message_type=protocol.STEP,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=1,
            payload=step_payload(1, initial["boundary_token"]),
        )
        first_step = expect_ok(frame, "scripted-setup-step")
        next_request += 1
        require(first_step["advanced_ticks"] == 128, "scripted setup step did not advance 128 ticks")
        require(first_step["snapshot"]["tick"] == 128, "first post-action tick is not 128")
        trace.append(first_step["snapshot"])

        frame = request(
            worker,
            message_type=protocol.STEP,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=2,
            payload=step_payload(1, first_step["post_boundary_token"]),
        )
        expect_error(frame, "INVALID_ACTION", "repeated-scripted-setup")
        next_request += 1

        current = first_step
        transition = 1
        while (
            current["snapshot"]["company"]["delivered_passengers"] == 0
            or current["snapshot"]["company"]["income"] <= 0
        ):
            require(transition < 512, "scripted bus did not deliver within the M02 action horizon")
            transition += 1
            frame = request(
                worker,
                message_type=protocol.STEP,
                session_id=session_id,
                episode_id=episode_id,
                request_id=next_request,
                transition=transition,
                payload=step_payload(0, current["post_boundary_token"]),
            )
            current = expect_ok(frame, f"wait-step-{transition}")
            next_request += 1
            require(current["advanced_ticks"] == 128, "WAIT step did not advance 128 ticks")
            require(
                current["snapshot"]["tick"] == transition * 128,
                "post-step tick does not equal transition times 128",
            )
            trace.append(current["snapshot"])

        frame = request(
            worker,
            message_type=protocol.SNAPSHOT,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=transition,
            payload={},
        )
        delivery_query = expect_ok(frame, "delivery-snapshot")["snapshot"]
        next_request += 1
        require(delivery_query == current["snapshot"], "delivery snapshot query perturbed state")

        frame = request(
            worker,
            message_type=protocol.RESET,
            session_id=session_id,
            episode_id=episode_id,
            request_id=next_request,
            transition=0,
            payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
        )
        second_reset = expect_ok(frame, "same-process-reset")
        next_request += 1
        require(second_reset["episode_id"] == 2, "same-process reset did not allocate episode 2")
        require(
            strip_control_snapshot(second_reset["snapshot"])
            == strip_control_snapshot(initial),
            "same-process reset does not reproduce the clean episode state",
        )

        frame = request(
            worker,
            message_type=protocol.CLOSE,
            session_id=session_id,
            episode_id=2,
            request_id=next_request,
            transition=0,
            payload={},
        )
        closed = expect_ok(frame, "close")
        require(closed["lifecycle"] == "CLOSED", "close did not enter CLOSED")

        process_record = finish_worker(worker, run_root, executable, instance, timeout)
        require(
            process_record["stdout"]
            == f"M03_BRIDGE=CLOSED session={session_id} episodes=2 transitions=0",
            "worker close log is not canonical",
        )
        normalized_trace = [strip_control_snapshot(item) for item in trace]
        return {
            "delivery_transition": transition,
            "final_delivery_snapshot": strip_control_snapshot(current["snapshot"]),
            "initial_snapshot": strip_control_snapshot(initial),
            "process": process_record,
            "trace_sha256": sha256_bytes(protocol.canonical_bytes(normalized_trace)),
            "trace": normalized_trace,
        }
    except Exception:
        if worker.process.poll() is None:
            worker.process.kill()
            stdout, stderr = worker.process.communicate()
            if not (run_root / "stdout.txt").exists():
                write_new_bytes(run_root / "stdout.txt", stdout)
            if not (run_root / "stderr.txt").exists():
                write_new_bytes(run_root / "stderr.txt", stderr)
        worker.client.close_descriptors()
        raise


def exercise_action_free_soak(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    session_id: int,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root,
        timeout=timeout,
    )
    request_id = 1
    try:
        reset = expect_ok(
            request(
                worker,
                message_type=protocol.RESET,
                session_id=session_id,
                episode_id=0,
                request_id=request_id,
                transition=0,
                payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
            ),
            "soak-reset",
        )
        request_id += 1
        episode_id = reset["episode_id"]
        token = reset["snapshot"]["boundary_token"]
        final: dict[str, Any] | None = None
        for transition in range(1, 513):
            final = expect_ok(
                request(
                    worker,
                    message_type=protocol.STEP,
                    session_id=session_id,
                    episode_id=episode_id,
                    request_id=request_id,
                    transition=transition,
                    payload=step_payload(0, token),
                ),
                f"soak-step-{transition}",
            )
            request_id += 1
            require(final["advanced_ticks"] == 128, "soak step did not advance 128 ticks")
            require(final["snapshot"]["tick"] == transition * 128, "soak tick counter desynchronized")
            require(final["snapshot"]["pools"]["vehicles"] == 0, "action-free soak created a vehicle")
            token = final["post_boundary_token"]
        assert final is not None
        require(final["snapshot"]["tick"] == 65536, "soak did not end at tick horizon 65536")
        require(final["truncated"] is True, "soak horizon did not truncate")
        require(final["truncation_reason"] == "action-horizon", "simultaneous horizon priority drifted")

        frame = request(
            worker,
            message_type=protocol.STEP,
            session_id=session_id,
            episode_id=episode_id,
            request_id=request_id,
            transition=513,
            payload=step_payload(0, token),
        )
        expect_error(frame, "INVALID_ACTION", "post-horizon-step")
        request_id += 1
        snapshot = expect_ok(
            request(
                worker,
                message_type=protocol.SNAPSHOT,
                session_id=session_id,
                episode_id=episode_id,
                request_id=request_id,
                transition=512,
                payload={},
            ),
            "post-horizon-snapshot",
        )["snapshot"]
        request_id += 1
        require(snapshot == final["snapshot"], "post-horizon rejection perturbed state")
        expect_ok(
            request(
                worker,
                message_type=protocol.CLOSE,
                session_id=session_id,
                episode_id=episode_id,
                request_id=request_id,
                transition=512,
                payload={},
            ),
            "soak-close",
        )
        process_record = finish_worker(worker, run_root, executable, instance, timeout)
        return {
            "action_count": 512,
            "final_snapshot_sha256": sha256_bytes(
                protocol.canonical_bytes(strip_control_snapshot(snapshot))
            ),
            "final_tick": 65536,
            "process": process_record,
            "truncation_reason": "action-horizon",
        }
    except Exception:
        if worker.process.poll() is None:
            worker.process.kill()
            worker.process.communicate()
        worker.client.close_descriptors()
        raise


def exercise_process_isolation(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    timeout: float,
) -> dict[str, Any]:
    """Interleave two workers and prove their engine state cannot cross-contaminate."""
    workers: list[tuple[str, protocol.WorkerProcess, pathlib.Path, int]] = []
    try:
        for label, session_id in (
            ("worker-a", 0x4D0349534F4C4101),
            ("worker-b", 0x4D0349534F4C4202),
        ):
            worker_root = run_root / label
            worker = protocol.WorkerProcess.start(
                executable=executable,
                instance=instance,
                run_root=worker_root,
                timeout=timeout,
            )
            workers.append((label, worker, worker_root, session_id))

        (_, worker_a, root_a, session_a), (_, worker_b, root_b, session_b) = workers
        reset_a = expect_ok(
            request(
                worker_a,
                message_type=protocol.RESET,
                session_id=session_a,
                episode_id=0,
                request_id=1,
                transition=0,
                payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
            ),
            "isolation-reset-a",
        )
        reset_b = expect_ok(
            request(
                worker_b,
                message_type=protocol.RESET,
                session_id=session_b,
                episode_id=0,
                request_id=1,
                transition=0,
                payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
            ),
            "isolation-reset-b",
        )
        initial_a = reset_a["snapshot"]
        initial_b = reset_b["snapshot"]
        require(
            strip_control_snapshot(initial_a) == strip_control_snapshot(initial_b),
            "isolated workers did not begin from the same engine state",
        )

        step_a = expect_ok(
            request(
                worker_a,
                message_type=protocol.STEP,
                session_id=session_a,
                episode_id=1,
                request_id=2,
                transition=1,
                payload=step_payload(1, initial_a["boundary_token"]),
            ),
            "isolation-step-a",
        )
        unchanged_b = expect_ok(
            request(
                worker_b,
                message_type=protocol.SNAPSHOT,
                session_id=session_b,
                episode_id=1,
                request_id=2,
                transition=0,
                payload={},
            ),
            "isolation-query-b",
        )["snapshot"]
        require(unchanged_b == initial_b, "worker A mutation crossed into worker B")
        require(step_a["snapshot"]["pools"]["vehicles"] == 1, "worker A did not create its fixture bus")
        require(unchanged_b["pools"]["vehicles"] == 0, "worker B gained worker A's fixture bus")

        step_b = expect_ok(
            request(
                worker_b,
                message_type=protocol.STEP,
                session_id=session_b,
                episode_id=1,
                request_id=3,
                transition=1,
                payload=step_payload(0, unchanged_b["boundary_token"]),
            ),
            "isolation-step-b",
        )
        unchanged_a = expect_ok(
            request(
                worker_a,
                message_type=protocol.SNAPSHOT,
                session_id=session_a,
                episode_id=1,
                request_id=3,
                transition=1,
                payload={},
            ),
            "isolation-query-a",
        )["snapshot"]
        require(unchanged_a == step_a["snapshot"], "worker B mutation crossed into worker A")
        require(step_b["snapshot"]["pools"]["vehicles"] == 0, "worker B WAIT mutated its vehicle pool")
        require(step_a["snapshot"]["tick"] == step_b["snapshot"]["tick"] == 128, "worker ticks desynchronized")

        for worker, session_id in ((worker_a, session_a), (worker_b, session_b)):
            expect_ok(
                request(
                    worker,
                    message_type=protocol.CLOSE,
                    session_id=session_id,
                    episode_id=1,
                    request_id=4,
                    transition=1,
                    payload={},
                ),
                "isolation-close",
            )

        process_a = finish_worker(worker_a, root_a, executable, instance, timeout)
        process_b = finish_worker(worker_b, root_b, executable, instance, timeout)
        return {
            "environment_count": 2,
            "process_count": 2,
            "processes": [process_a, process_b],
            "worker_a_snapshot_sha256": sha256_bytes(
                protocol.canonical_bytes(strip_control_snapshot(unchanged_a))
            ),
            "worker_b_snapshot_sha256": sha256_bytes(
                protocol.canonical_bytes(strip_control_snapshot(step_b["snapshot"]))
            ),
        }
    except Exception:
        for _, worker, worker_root, _ in workers:
            if worker.process.poll() is None:
                worker.process.kill()
                stdout, stderr = worker.process.communicate()
                if not (worker_root / "stdout.txt").exists():
                    write_new_bytes(worker_root / "stdout.txt", stdout)
                if not (worker_root / "stderr.txt").exists():
                    write_new_bytes(worker_root / "stderr.txt", stderr)
            worker.client.close_descriptors()
        raise


def exercise_configurable_ticks(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    session_id: int,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root,
        timeout=timeout,
    )
    request_id = 1
    try:
        reset = expect_ok(
            request(
                worker,
                message_type=protocol.RESET,
                session_id=session_id,
                episode_id=0,
                request_id=request_id,
                transition=0,
                payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
            ),
            "configurable-ticks-reset",
        )
        request_id += 1
        token = reset["snapshot"]["boundary_token"]

        rejected_intervals = (0, 129, 4_294_967_297)
        for invalid_interval in rejected_intervals:
            frame = request(
                worker,
                message_type=protocol.STEP,
                session_id=session_id,
                episode_id=1,
                request_id=request_id,
                transition=1,
                payload=step_payload(0, token, invalid_interval),
            )
            expect_error(frame, "BAD_PAYLOAD", f"invalid-interval-{invalid_interval}")
            request_id += 1

        huge_action_id = 4_294_967_297
        frame = request(
            worker,
            message_type=protocol.STEP,
            session_id=session_id,
            episode_id=1,
            request_id=request_id,
            transition=1,
            payload=step_payload(huge_action_id, token, 1),
        )
        expect_error(frame, "INVALID_ACTION", "narrowing-action-id")
        request_id += 1

        intervals = (1, 64, 128)
        cumulative_tick = 0
        for transition, interval in enumerate(intervals, 1):
            step = expect_ok(
                request(
                    worker,
                    message_type=protocol.STEP,
                    session_id=session_id,
                    episode_id=1,
                    request_id=request_id,
                    transition=transition,
                    payload=step_payload(0, token, interval),
                ),
                f"configurable-ticks-step-{interval}",
            )
            request_id += 1
            cumulative_tick += interval
            require(step["advanced_ticks"] == interval, "configured step interval was not recorded")
            require(step["snapshot"]["tick"] == cumulative_tick, "configured step interval desynchronized ticks")
            token = step["post_boundary_token"]

        expect_ok(
            request(
                worker,
                message_type=protocol.CLOSE,
                session_id=session_id,
                episode_id=1,
                request_id=request_id,
                transition=len(intervals),
                payload={},
            ),
            "configurable-ticks-close",
        )
        process_record = finish_worker(worker, run_root, executable, instance, timeout)
        return {
            "accepted_intervals": list(intervals),
            "final_tick": cumulative_tick,
            "maximum_interval": 128,
            "minimum_interval": 1,
            "process": process_record,
            "rejected_action_ids": [huge_action_id],
            "rejected_intervals": list(rejected_intervals),
        }
    except Exception:
        if worker.process.poll() is None:
            worker.process.kill()
            stdout, stderr = worker.process.communicate()
            if not (run_root / "stdout.txt").exists():
                write_new_bytes(run_root / "stdout.txt", stdout)
            if not (run_root / "stderr.txt").exists():
                write_new_bytes(run_root / "stderr.txt", stderr)
        worker.client.close_descriptors()
        raise


def exercise_bad_checksum(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    session_id: int,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root,
        timeout=timeout,
    )
    frame = worker.client.request(
        message_type=protocol.RESET,
        session_id=session_id,
        episode_id=0,
        request_id=1,
        transition_ordinal=0,
        payload={"bridge_compatibility_sha256": BRIDGE_COMPATIBILITY},
        checksum_override=1,
    )
    error = expect_error(frame, "BAD_CHECKSUM", "bad-checksum", fatal=True)
    require(error["lifecycle"] == "FAILED", "fatal checksum failure did not enter FAILED")
    closed = expect_ok(
        request(
            worker,
            message_type=protocol.CLOSE,
            session_id=session_id,
            episode_id=0,
            request_id=1,
            transition=0,
            payload={},
        ),
        "failed-close",
    )
    require(closed["lifecycle"] == "CLOSED", "FAILED worker did not close cleanly")
    process_record = finish_worker(worker, run_root, executable, instance, timeout)
    return {"code": "BAD_CHECKSUM", "fatal": True, "process": process_record}


def exercise_timeout_detection(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root,
        timeout=timeout,
    )
    classified = False
    try:
        protocol.decode_frame(worker.client.response_descriptor, 0.05)
    except protocol.M03BridgeTimeout:
        classified = True
    require(classified, "coordinator did not classify a bounded response timeout")
    returncode, stdout, stderr = worker.terminate_for_timeout_evidence()
    write_new_bytes(run_root / "stdout.txt", stdout)
    write_new_bytes(run_root / "stderr.txt", stderr)
    require(returncode < 0, "timed-out worker was not terminated by a signal")
    return {
        "classification": "timeout",
        "returncode": returncode,
        "stderr_sha256": sha256_bytes(stderr),
        "stdout_sha256": sha256_bytes(stdout),
    }


def exercise_crash_detection(
    *,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    timeout: float,
) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(
        executable=executable,
        instance=instance,
        run_root=run_root,
        timeout=timeout,
    )
    worker.process.kill()
    stdout, stderr = worker.process.communicate()
    classified = False
    try:
        protocol.decode_frame(worker.client.response_descriptor, timeout)
    except protocol.M03BridgeProtocolError:
        classified = True
    finally:
        worker.client.close_descriptors()
    require(classified, "coordinator did not classify a terminated worker as a crash")
    write_new_bytes(run_root / "stdout.txt", stdout)
    write_new_bytes(run_root / "stderr.txt", stderr)
    require(worker.process.returncode < 0, "crash exercise worker was not terminated by a signal")
    return {
        "classification": "crash",
        "returncode": worker.process.returncode,
        "stderr_sha256": sha256_bytes(stderr),
        "stdout_sha256": sha256_bytes(stdout),
    }


def validate_native_delta(root: pathlib.Path) -> None:
    series = root / "integration/openttd/patches/15.3/m03/series"
    patch = root / "integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch"
    require(series.is_file() and not series.is_symlink(), "M03 series is not a regular file")
    require(patch.is_file() and not patch.is_symlink(), "M03 patch is not a regular file")
    require(sha256_file(series) == M03_SERIES_SHA256, "M03 series digest drifted")
    require(sha256_file(patch) == M03_PATCH_SHA256, "M03 patch digest drifted")
    require(
        series.read_text(encoding="utf-8") == "0004-synchronized-environment-bridge.patch\n",
        "M03 series inventory drifted",
    )


def run_bridge_disabled_reference(
    *,
    root: pathlib.Path,
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    expected: dict[str, str],
    environment: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    output, trajectory, command, stdout = run_m02_reset_oracle.run_native(
        executable,
        run_root,
        instance,
        1,
        environment,
        timeout,
    )
    _, projection_digest = validate_m02_reset_projection.validate_paths(
        output,
        instance,
        root / "config/v1/m02-scenario-contract.json",
        root / "docs/project/schema/v1-m02-scenario-contract.schema.json",
        root / "docs/project/schema/v1-m02-reset-projection.schema.json",
    )
    _, trajectory_digest = validate_m02_scripted_trajectory.validate_paths(
        trajectory,
        instance,
        root / "docs/project/schema/v1-m02-scripted-bus-trajectory.schema.json",
    )
    require(projection_digest == expected["projection_sha256"], "bridge-disabled M02 projection drifted")
    require(trajectory_digest == expected["trajectory_report_sha256"], "bridge-disabled M02 trajectory drifted")
    return {
        "command": command,
        "projection_sha256": projection_digest,
        "stdout": stdout,
        "trajectory_report_sha256": trajectory_digest,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    executable = args.executable.resolve()
    opengfx = args.opengfx_tar.resolve()
    artifact_root = args.artifact_root.resolve()
    require(executable.is_file() and os.access(executable, os.X_OK), "OpenTTD executable is not executable")
    require(opengfx.is_file() and not opengfx.is_symlink(), "OpenGFX archive is not a regular file")
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root already exists")

    contract = validate_m03_bridge_contract.validate(
        root / "config/v1/m03-bridge-contract.json",
        root / "docs/project/schema/v1-m03-bridge-contract.schema.json",
    )
    require(contract["identity"]["compatibility_sha256"] == BRIDGE_COMPATIBILITY, "bridge identity drifted")
    validate_native_delta(root)

    m02_oracle_path = root / "config/v1/m02-reset-oracle.json"
    m02_oracle = validate_m02_scenario_contract.load_strict_json(m02_oracle_path)
    expected_templates = run_m02_reset_oracle.validate_oracle_config(root, m02_oracle)
    require(sha256_file(opengfx) == m02_oracle["content"]["opengfx_archive_sha256"], "OpenGFX identity drifted")
    m02_contract, corpus, ledger = generate_m02_scenario.load_and_validate(
        root / "config/v1/m02-scenario-contract.json",
        root / "docs/project/schema/v1-m02-scenario-contract.schema.json",
        root / "config/v1/m02-scenario-corpus.json",
        root / "docs/project/schema/v1-m02-scenario-corpus.schema.json",
        root / "config/v1/m02-seed-ledger.json",
        root / "docs/project/schema/v1-m02-seed-ledger.schema.json",
    )
    by_id = {item["template_id"]: item for item in corpus["templates"]}
    selected = args.template_id or list(by_id)
    require(len(selected) == len(set(selected)), "template selection contains duplicates")
    require(set(selected) <= set(by_id), f"unknown templates: {sorted(set(selected) - set(by_id))}")
    if any(by_id[item]["split"] == "final-evaluation" for item in selected):
        require(args.allow_final_evaluation, "final-evaluation templates require --allow-final-evaluation")

    artifact_root.mkdir(parents=True)
    runtime = artifact_root / "runtime"
    runtime_assets = run_m02_reset_oracle.stage_runtime(executable, opengfx, runtime)
    staged_executable = runtime / "openttd"
    environment = {
        **os.environ,
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
        "SOURCE_DATE_EPOCH": "1742688000",
    }
    instance_schema = root / "docs/project/schema/v1-m02-scenario-instance.schema.json"
    records: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    first_instance: pathlib.Path | None = None
    for template_index, template_id in enumerate(selected, 1):
        template = by_id[template_id]
        instance_value = generate_m02_scenario.build_instance(
            m02_contract,
            corpus,
            ledger,
            template,
            instance_schema,
        )
        instance = artifact_root / "instances" / f"{template_id}.json"
        write_canonical_new(instance, instance_value)
        if first_instance is None:
            first_instance = instance

        runs: list[dict[str, Any]] = []
        session_id = 0x4D03000000000000 + template_index
        for repetition in (1, 2):
            run_root = artifact_root / "runs" / template_id / f"bridge-{repetition}"
            result = exercise_scripted_worker(
                executable=staged_executable,
                instance=instance,
                run_root=run_root,
                session_id=session_id,
                timeout=args.operation_timeout,
            )
            commands.append({
                "argv": result["process"]["command"],
                "mode": f"bridge-{repetition}",
                "template_id": template_id,
            })
            runs.append(result)
        require(runs[0]["trace"] == runs[1]["trace"], f"{template_id} repeated bridge traces differ")
        require(
            runs[0]["delivery_transition"] == runs[1]["delivery_transition"],
            f"{template_id} delivery transition differs across processes",
        )

        reference = run_bridge_disabled_reference(
            root=root,
            executable=staged_executable,
            instance=instance,
            run_root=artifact_root / "runs" / template_id / "bridge-disabled-m02",
            expected=expected_templates[template_id],
            environment=environment,
            timeout=args.process_timeout,
        )
        commands.append({
            "argv": reference["command"],
            "mode": "bridge-disabled-m02",
            "template_id": template_id,
        })
        records.append({
            "bridge_disabled_projection_sha256": reference["projection_sha256"],
            "bridge_disabled_trajectory_report_sha256": reference["trajectory_report_sha256"],
            "delivery_transition": runs[0]["delivery_transition"],
            "initial_snapshot_sha256": sha256_bytes(protocol.canonical_bytes(runs[0]["initial_snapshot"])),
            "scenario_sha256": instance_value["identity"]["scenario_sha256"],
            "split": template["split"],
            "template_id": template_id,
            "trace_sha256": runs[0]["trace_sha256"],
        })
        print(
            "M03_BRIDGE_TEMPLATE=PASS "
            f"template={template_id} delivery_transition={runs[0]['delivery_transition']} "
            f"trace_sha256={runs[0]['trace_sha256']}"
        )

    assert first_instance is not None
    soak = exercise_action_free_soak(
        executable=staged_executable,
        instance=first_instance,
        run_root=artifact_root / "soak" / "action-free-512",
        session_id=0x4D03504F414B0001,
        timeout=args.operation_timeout,
    )
    isolation = exercise_process_isolation(
        executable=staged_executable,
        instance=first_instance,
        run_root=artifact_root / "isolation" / "two-processes",
        timeout=args.operation_timeout,
    )
    for index, process in enumerate(isolation["processes"], 1):
        commands.append({
            "argv": process["command"],
            "mode": f"isolation-worker-{index}",
            "template_id": selected[0],
        })
    scheduler = exercise_configurable_ticks(
        executable=staged_executable,
        instance=first_instance,
        run_root=artifact_root / "scheduler" / "configurable-ticks",
        session_id=0x4D035449434B0001,
        timeout=args.operation_timeout,
    )
    commands.append({
        "argv": scheduler["process"]["command"],
        "mode": "configurable-ticks",
        "template_id": selected[0],
    })
    bad_checksum = exercise_bad_checksum(
        executable=staged_executable,
        instance=first_instance,
        run_root=artifact_root / "failures" / "bad-checksum",
        session_id=0x4D03424144435243,
        timeout=args.operation_timeout,
    )
    timeout_evidence = exercise_timeout_detection(
        executable=staged_executable,
        instance=first_instance,
        run_root=artifact_root / "failures" / "timeout",
        timeout=args.operation_timeout,
    )
    crash_evidence = exercise_crash_detection(
        executable=staged_executable,
        instance=first_instance,
        run_root=artifact_root / "failures" / "crash",
        timeout=args.operation_timeout,
    )

    manifest = {
        "bridge_contract_compatibility_sha256": BRIDGE_COMPATIBILITY,
        "commands_sha256": sha256_bytes(protocol.canonical_bytes(commands)),
        "executable_sha256": sha256_file(staged_executable),
        "failure_evidence": {
            "bad_checksum": bad_checksum,
            "crash": crash_evidence,
            "timeout": timeout_evidence,
        },
        "isolation": isolation,
        "m03_composed_source_identity_sha256": M03_COMPOSED_SOURCE_IDENTITY,
        "m03_result_tree": M03_RESULT_TREE,
        "runtime_asset_identity_sha256": sha256_bytes(protocol.canonical_bytes(runtime_assets)),
        "scheduler": scheduler,
        "schema_version": "openttd-rl-v1-m03-bridge-oracle-report-1",
        "soak": soak,
        "status": "PASS",
        "templates": records,
    }
    report_schema_path = root / "docs/project/schema/v1-m03-bridge-oracle-report.schema.json"
    require(sha256_file(report_schema_path) == M03_REPORT_SCHEMA_SHA256, "oracle report schema drifted")
    report_schema = validate_m02_scenario_contract.load_strict_json(report_schema_path)
    jsonschema.Draft202012Validator.check_schema(report_schema)
    jsonschema.Draft202012Validator(report_schema).validate(manifest)
    write_canonical_new(artifact_root / "commands.json", {"commands": commands})
    write_canonical_new(artifact_root / "manifest.json", manifest)
    return manifest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--executable", required=True, type=pathlib.Path)
    parser.add_argument("--opengfx-tar", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--template-id", action="append")
    parser.add_argument("--allow-final-evaluation", action="store_true")
    parser.add_argument("--operation-timeout", type=float, default=30.0)
    parser.add_argument("--process-timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        require(0.1 <= args.operation_timeout <= 300, "operation timeout must be in 0.1..300 seconds")
        require(1 <= args.process_timeout <= 3600, "process timeout must be in 1..3600 seconds")
        manifest = run(args)
    except (
        OSError,
        KeyError,
        TypeError,
        M03BridgeOracleError,
        protocol.M03BridgeProtocolError,
        protocol.M03BridgeTimeout,
        generate_m02_scenario.M02ScenarioGenerationError,
        run_m02_reset_oracle.M02ResetOracleError,
        validate_m02_reset_projection.M02ResetProjectionError,
        validate_m02_scripted_trajectory.M02ScriptedTrajectoryError,
        validate_m02_scenario_contract.M02ScenarioContractError,
        validate_m03_bridge_contract.M03BridgeContractError,
        jsonschema.SchemaError,
        jsonschema.ValidationError,
    ) as exc:
        print(f"M03_BRIDGE_ORACLE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M03_BRIDGE_ORACLE=PASS "
        f"templates={len(manifest['templates'])} "
        f"soak_ticks={manifest['soak']['final_tick']} "
        f"executable_sha256={manifest['executable_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
