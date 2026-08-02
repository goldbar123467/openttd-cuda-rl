#!/usr/bin/env python3
"""Actual-engine M06 reward, exploit, termination, rollover, and trajectory campaign."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema

import m03_bridge_protocol as protocol
import m05_action_adapter
import m06_reward_reference
import m06_trajectory
import validate_m06_reward_contract


OBSERVE = 8
M06_PATCH_SHA256 = "ce2a423e5f78aed861d0ca032a21509ce976267f17718cea8e3a973f8d24e912"
M06_SERIES_SHA256 = "b001a2bffe511d1814dd820373b129d887d35cce7ad38bd02dcce5ccc106bbff"
M06_RESULT_TREE = "56b7f68297cb1ec7548c25ac9dfa0d0088e70547"
M06_COMPOSED_SOURCE_IDENTITY = "98693ab0595fb26612079683a192a12f7bce6bb4cb25a7edf895244c50c568a2"
M05_RESULT_TREE = "ad0575b92f7975ef085e5f35bfe182a504d6cb51"
M05_COMPOSED_SOURCE_IDENTITY = "9bb57367151fbf4eedcd802d179c946685a911bec9b99d7573501e0f52a3b2bd"
REPORT_SCHEMA_SHA256 = "76eae7214a0bb061d573eda4ddca3e5fa82312550d8492b767b5b005a15d43e3"


class M06RewardOracleError(ValueError):
    """Actual engine behavior violated the frozen M06 contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M06RewardOracleError(message)


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
    descriptor = path.open("xb")
    with descriptor:
        descriptor.write(canonical_bytes(value) + b"\n")
        descriptor.flush()


def validate_native_delta(root: pathlib.Path) -> None:
    directory = root / "integration/openttd/patches/15.3/m06"
    patch = directory / "0007-native-reward-termination.patch"
    series = directory / "series"
    require(patch.is_file() and not patch.is_symlink(), "M06 patch is not a regular file")
    require(series.is_file() and not series.is_symlink(), "M06 series is not a regular file")
    require(sha256_file(patch) == M06_PATCH_SHA256, "M06 patch digest drifted")
    require(sha256_file(series) == M06_SERIES_SHA256, "M06 series digest drifted")
    require(series.read_text(encoding="utf-8") == patch.name + "\n", "M06 series inventory drifted")


class Controller:
    def __init__(
        self,
        worker: protocol.WorkerProcess,
        session: int,
        contract: dict[str, Any],
        instance: pathlib.Path,
        run_id: str,
        bundle: m06_trajectory.TrajectoryBundle | None = None,
    ) -> None:
        self.worker = worker
        self.session = session
        self.contract = contract
        self.instance = instance
        self.instance_value = json.loads(instance.read_text(encoding="utf-8"))
        self.run_id = run_id
        self.bundle = bundle
        self.request_id = 0
        self.transition = 0
        self.tick_zero = 0
        self.boundary = ""
        self.last_mask: dict[str, Any] | None = None
        self.last_mask_token = ""
        self.current_observation: dict[str, Any] | None = None
        self.reward_component_hits = {f"RC-{index:03d}": 0 for index in range(1, 9)}
        self.scalar_return = 0.0
        self.action_horizon = 512
        self.tick_horizon = 65_536

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

    def reset(self, *, observe: bool = False) -> dict[str, Any]:
        frame = self._request(protocol.RESET, 0, {"bridge_compatibility_sha256": m06_trajectory.BRIDGE_COMPATIBILITY_SHA256})
        require(frame.payload["status"] == "OK", f"RESET failed: {frame.payload}")
        snapshot = frame.payload["snapshot"]
        self.action_horizon = 512
        self.tick_horizon = 65_536
        self.tick_zero = snapshot["tick"]
        self.boundary = snapshot["boundary_token"]
        if observe:
            self.current_observation = self.observe()
        return snapshot

    def reset_evaluation(
        self,
        *,
        evaluation_contract_sha256: str,
        starting_balance: int,
        action_horizon: int,
        observe: bool = False,
    ) -> dict[str, Any]:
        """Use the bounded M09-only scenario variation entrypoint."""
        require(
            evaluation_contract_sha256 == "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e"
            and starting_balance in (75_000, 100_000, 125_000)
            and action_horizon in (64, 128, 256),
            "evaluation reset is outside the preregistered M09 matrix",
        )
        frame = self._request(
            protocol.RESET,
            0,
            {
                "bridge_compatibility_sha256": m06_trajectory.BRIDGE_COMPATIBILITY_SHA256,
                "evaluation_action_horizon": action_horizon,
                "evaluation_contract_sha256": evaluation_contract_sha256,
                "evaluation_starting_balance": starting_balance,
                "evaluation_tick_horizon": action_horizon * 128,
            },
        )
        require(frame.payload["status"] == "OK", f"M09 evaluation RESET failed: {frame.payload}")
        snapshot = frame.payload["snapshot"]
        require(snapshot["company"]["balance"] == starting_balance, "M09 starting-balance override did not apply")
        self.action_horizon = action_horizon
        self.tick_horizon = action_horizon * 128
        self.tick_zero = snapshot["tick"]
        self.boundary = snapshot["boundary_token"]
        if observe:
            self.current_observation = self.observe()
        return snapshot

    def observe(self) -> dict[str, Any]:
        frame = self._request(
            OBSERVE,
            self.transition,
            {
                "include_source_projection": False,
                "observation_compatibility_sha256": m06_trajectory.OBSERVATION_COMPATIBILITY_SHA256,
            },
        )
        require(frame.payload["status"] == "OK", f"OBSERVE failed: {frame.payload}")
        self.boundary = frame.payload["boundary_token"]
        return frame.payload["observation"]

    def snapshot(self) -> dict[str, Any]:
        frame = self._request(protocol.SNAPSHOT, self.transition, {})
        require(frame.payload["status"] == "OK", f"SNAPSHOT failed: {frame.payload}")
        return frame.payload["snapshot"]

    def mask(self, *, include_source: bool = False) -> dict[str, Any]:
        frame = self._request(
            protocol.LEGAL_ACTIONS,
            self.transition,
            {
                "action_compatibility_sha256": m06_trajectory.ACTION_COMPATIBILITY_SHA256,
                "include_source_projection": include_source,
            },
        )
        require(frame.payload["status"] == "OK", f"LEGAL_ACTIONS failed: {frame.payload}")
        self.boundary = frame.payload["boundary_token"]
        self.last_mask = frame.payload["mask"]
        self.last_mask_token = frame.payload["mask_token"]
        legal = m05_action_adapter.validate_mask(self.last_mask)
        if include_source:
            require(legal == m05_action_adapter.independent_oracle_mask(self.last_mask["source_projection"]), "M05 native/oracle mask mismatch inside M06")
        return self.last_mask

    def step(
        self,
        action_index: int,
        *,
        injected_failure: str | None = None,
        injected_outcome: str | None = None,
        record: bool = False,
    ) -> dict[str, Any]:
        require(self.last_mask is not None, "STEP requires an issued mask")
        if record:
            require(self.bundle is not None and self.current_observation is not None, "recorded STEP lacks trajectory builder/current observation")
        pre_snapshot = self.snapshot()
        pre_mask = self.last_mask
        pre_mask_token = self.last_mask_token
        pre_boundary = self.boundary
        payload = {
            "action_compatibility_sha256": m06_trajectory.ACTION_COMPATIBILITY_SHA256,
            "action_index": action_index,
            "boundary_token": pre_boundary,
            "bridge_compatibility_sha256": m06_trajectory.BRIDGE_COMPATIBILITY_SHA256,
            "include_transition_tensors": record,
            "inject_episode_outcome": injected_outcome,
            "inject_native_failure": injected_failure,
            "mask_token": pre_mask_token,
            "reward_compatibility_sha256": m06_trajectory.REWARD_COMPATIBILITY_SHA256,
        }
        frame = self._request(protocol.STEP, self.transition + 1, payload)
        require(frame.payload["status"] == "OK", f"STEP failed: {frame.payload}")
        result = frame.payload
        if result["action_outcome"]["status"] == "ILLEGAL_INPUT":
            require(result["advanced_ticks"] == 0 and "reward" not in result, "ILLEGAL_INPUT formed a reward transition")
            return result
        require(result["advanced_ticks"] == 128, "accepted M06 action did not advance exactly 128 ticks")
        self.transition += 1
        self.boundary = result["post_boundary_token"]
        self.last_mask = None
        self.last_mask_token = ""
        self._validate_reward(result)
        self.scalar_return += result["reward"]["scalar"]
        for component in result["reward"]["components"]:
            if component["raw"] != 0:
                self.reward_component_hits[component["component_id"]] += 1
        if record:
            next_observation = result["next_observation"]
            record_value = self._trajectory_record(
                result,
                pre_snapshot,
                pre_mask,
                pre_mask_token,
                action_index,
            )
            self.bundle.add(record_value, self.current_observation, next_observation)
            self.current_observation = next_observation
        return result

    def _validate_reward(self, result: dict[str, Any]) -> None:
        reward = result["reward"]
        require(reward["compatibility_sha256"] == m06_trajectory.REWARD_COMPATIBILITY_SHA256, "native reward identity drifted")
        source = reward["source"]
        action = result["action_outcome"]
        action_projection = {
            "advanced_ticks": result["advanced_ticks"],
            "native_commands": action["native_commands"],
            "status": action["status"],
        }
        raw = m06_reward_reference.derive_raw(source["pre"], source["post"], action_projection)
        expected = m06_reward_reference.compute_reward(raw, self.contract)
        require(reward["raw"] == raw, f"native raw reward differs from independent oracle: {reward['raw']} != {raw}")
        require(tuple(item["raw"] for item in reward["components"]) == expected.raw, "native component raw vector drifted")
        require(tuple(item["clamped"] for item in reward["components"]) == expected.clamped, "native component clamp vector drifted")
        require(tuple(item["weighted"] for item in reward["components"]) == expected.weighted, "native component weighted vector drifted")
        require(reward["scalar"] == expected.scalar, "native scalar left fold drifted")
        require(reward["scalar_float64_bits"] == m06_reward_reference.float64_bits(expected.scalar), "native scalar float guard drifted")
        for item, weighted in zip(reward["components"], expected.weighted):
            expected_bits = m06_reward_reference.float64_bits(weighted)
            require(item["weighted_float64_bits"] == expected_bits, f"{item['component_id']} float guard drifted: {item['weighted_float64_bits']} != {expected_bits}")
        termination = result["termination"]
        expected_termination = m06_reward_reference.classify_termination(
            self.contract,
            bankruptcy=bool(raw["bankruptcy"]),
            action_horizon=self.transition >= self.action_horizon,
            tick_horizon=result["snapshot"]["tick"] - self.tick_zero >= self.tick_horizon,
        )
        for name, value in dataclasses.asdict(expected_termination).items():
            require(termination[name] == value, f"native termination {name} drifted: {termination[name]} != {value}")

    def _trajectory_record(
        self,
        result: dict[str, Any],
        pre_snapshot: dict[str, Any],
        mask: dict[str, Any],
        mask_token: str,
        action_index: int,
    ) -> dict[str, Any]:
        outcome = result["action_outcome"]
        bootstrap = result["termination"]["bootstrap"]
        return {
            "action": {
                "index": action_index,
                "log_probability": 0.0,
                "log_probability_float64_bits": m06_reward_reference.float64_bits(0.0),
                "outcome": outcome,
                "parameters": outcome["parameters"],
                "selection_mode": "SCRIPTED",
                "value": 0.0,
                "value_float64_bits": m06_reward_reference.float64_bits(0.0),
            },
            "action_mask": {"dtype": "uint8", "legal": mask["legal"], "mask_token": mask_token},
            "boundary": {
                "advanced_ticks": result["advanced_ticks"],
                "post_tick": result["snapshot"]["tick"],
                "post_token": result["post_boundary_token"],
                "pre_tick": pre_snapshot["tick"],
                "pre_token": result["pre_boundary_token"],
            },
            "identities": {
                "action": m06_trajectory.ACTION_COMPATIBILITY_SHA256,
                "bridge": m06_trajectory.BRIDGE_COMPATIBILITY_SHA256,
                "model_checkpoint": None,
                "observation": m06_trajectory.OBSERVATION_COMPATIBILITY_SHA256,
                "reward": m06_trajectory.REWARD_COMPATIBILITY_SHA256,
            },
            "ids": {
                "environment_id": 0,
                "episode_id": 1,
                "request_id": self.request_id,
                "run_id": self.run_id,
                "transition_ordinal": self.transition,
                "worker_id": 0,
            },
            "next_value": {"float64_bits": m06_reward_reference.float64_bits(0.0), "value": 0.0} if bootstrap else None,
            "reward": result["reward"],
            "scenario": {
                "seed_ledger_sha256": self.instance_value["seed_ledger_sha256"],
                "template_id": self.instance_value["template_id"],
                "template_sha256": sha256_file(self.instance),
            },
            "schema_version": m06_trajectory.TRAJECTORY_SCHEMA_VERSION,
            "termination": result["termination"],
        }

    def close(self, timeout: float) -> str:
        frame = self._request(protocol.CLOSE, self.transition, {})
        require(frame.payload["status"] == "OK", f"CLOSE failed: {frame.payload}")
        code, stdout, stderr = self.worker.finish(timeout)
        require(code == 0 and stderr == b"", f"worker failed code={code} stderr={stderr.decode(errors='replace')}")
        return stdout.decode().strip()

    def abort(self) -> None:
        if self.worker.process.poll() is None:
            self.worker.process.kill()
        self.worker.client.close_descriptors()
        self.worker.process.communicate()


def legal_step(controller: Controller, index: int, *, record: bool = False, injected_failure: str | None = None, injected_outcome: str | None = None) -> dict[str, Any]:
    mask = controller.mask()
    require(mask["legal"][index] == 1, f"scripted action {index} is masked at transition {controller.transition}")
    return controller.step(index, record=record, injected_failure=injected_failure, injected_outcome=injected_outcome)


def build_service(controller: Controller, *, record: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    initial_mask = controller.mask(include_source=True)
    source = initial_mask["source_projection"]
    results = [controller.step(1, record=record)]
    results.append(legal_step(controller, 3, record=record))
    for stop in source["stops"]:
        results.append(legal_step(controller, 4 + stop["town_slot"] * 4 + stop["expected_direction"], record=record))
    results.append(legal_step(controller, 12 + source["depot"]["expected_direction"], record=record))
    results.append(legal_step(controller, 16, record=record))
    results.append(legal_step(controller, 17, record=record))
    results.append(legal_step(controller, 25, record=record))
    snapshot = results[-1]["snapshot"]
    while snapshot["company"]["delivered_passengers"] == 0 or snapshot["company"]["income"] <= 0:
        require(controller.transition < 511, "service policy reached horizon before passenger revenue")
        results.append(legal_step(controller, 0, record=record and controller.transition < 128))
        snapshot = results[-1]["snapshot"]
    require(any(item["reward"]["raw"]["delivered_passengers_delta"] > 0 for item in results), "service produced no delivery reward delta")
    require(any(item["reward"]["raw"]["operating_profit_delta"] > 0 for item in results), "service produced no positive operating-profit delta")
    require(any(item["reward"]["raw"]["capital_spend"] > 0 and item["reward"]["components"][2]["weighted"] < 0 for item in results), "construction spend was not negatively rewarded")
    return snapshot, results


def run_service_template(
    executable: pathlib.Path,
    instance: pathlib.Path,
    run_root: pathlib.Path,
    contract: dict[str, Any],
    session: int,
    timeout: float,
    *,
    bundle: m06_trajectory.TrajectoryBundle | None = None,
    continue_to_horizon: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=run_root, timeout=timeout)
    controller = Controller(worker, session, contract, instance, f"m06-service-{session}", bundle)
    try:
        controller.reset(observe=bundle is not None)
        snapshot, results = build_service(controller, record=bundle is not None)
        delivery_return = sum(item["reward"]["scalar"] for item in results)
        horizon_evidence = None
        if continue_to_horizon:
            current_income = snapshot["company"]["income"]
            current_delivered = snapshot["company"]["delivered_passengers"]
            quarter_resets = 0
            while controller.transition < 512:
                result = legal_step(controller, 0, record=bundle is not None and controller.transition < 128)
                new_income = result["snapshot"]["company"]["income"]
                new_delivered = result["snapshot"]["company"]["delivered_passengers"]
                if new_income < current_income or new_delivered < current_delivered:
                    quarter_resets += 1
                current_income, current_delivered = new_income, new_delivered
            final = result
            require(final["termination"]["reason"] == "ACTION_AND_TICK_HORIZON", "simultaneous horizon reason drifted")
            require(final["truncation_reason"] == "action-horizon", "legacy M03/M05 truncation reason compatibility drifted")
            require(final["termination"]["bootstrap"] and final["termination"]["truncated"] and not final["termination"]["terminal"], "horizon bootstrap semantics drifted")
            require(quarter_resets > 0, "actual campaign did not cross a current-economy quarter reset")
            final_observation = controller.observe()
            final_observation_sha256, _ = m06_trajectory.observation_sha256(final_observation)
            horizon_evidence = {
                "final_observation_sha256": final_observation_sha256,
                "quarter_counter_resets": quarter_resets,
                "reason": final["termination"]["reason"],
                "relative_ticks": final["snapshot"]["tick"] - controller.tick_zero,
                "transition_ordinal": controller.transition,
            }
        controller.close(timeout)
        return (
            {
                "capital_spend_hits": controller.reward_component_hits["RC-003"],
                "delivered_passengers": snapshot["company"]["delivered_passengers"],
                "delivery_interval_return": delivery_return,
                "delivery_reward_hits": controller.reward_component_hits["RC-001"],
                "income": snapshot["company"]["income"],
                "operating_profit_hits": controller.reward_component_hits["RC-002"],
                "reward_component_hits": controller.reward_component_hits,
                "transitions_to_service": len(results),
            },
            horizon_evidence,
        )
    except Exception:
        controller.abort()
        raise


def run_exploits(executable: pathlib.Path, instance: pathlib.Path, root: pathlib.Path, contract: dict[str, Any], timeout: float) -> dict[str, Any]:
    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=root / "waste-cycles", timeout=timeout)
    controller = Controller(worker, 8101, contract, instance, "m06-exploits")
    try:
        controller.reset()
        initial = controller.mask(include_source=True)
        source = initial["source_projection"]
        construction = [controller.step(1), legal_step(controller, 3)]
        duplicate_mask = controller.mask()
        require(duplicate_mask["legal"][3] == 0, "duplicate connector was not masked")
        duplicate = controller.step(3)
        require(duplicate["action_outcome"]["status"] == "ILLEGAL_INPUT" and "reward" not in duplicate, "duplicate attempt formed reward")
        for stop in source["stops"]:
            construction.append(legal_step(controller, 4 + stop["town_slot"] * 4 + stop["expected_direction"]))
        construction.append(legal_step(controller, 12 + source["depot"]["expected_direction"]))
        construction.append(legal_step(controller, 16))
        construction_return = sum(item["reward"]["scalar"] for item in construction)
        require(construction_return <= 0.0, "pure construction produced positive return")
        rejections = [legal_step(controller, 17, injected_failure="route-after-first-order") for _ in range(4)]
        require(
            all(item["reward"]["raw"]["native_rejected"] == 1 and item["reward"]["scalar"] <= -0.25 for item in rejections),
            "repeated native rejection penalty missing",
        )
        legal_step(controller, 17)
        idle = [legal_step(controller, 0) for _ in range(8)]
        require(all(item["reward"]["raw"]["idle_bus_ticks"] == 128 for item in idle), "idle bus-tick penalty did not fire")
        require(sum(item["reward"]["scalar"] for item in idle) < 0.0, "idling produced nonnegative return")
        cycling: list[dict[str, Any]] = []
        for _ in range(4):
            cycling.extend((legal_step(controller, 2), legal_step(controller, 17), legal_step(controller, 1), legal_step(controller, 17)))
        require(sum(item["reward"]["scalar"] for item in cycling) <= 0.0, "route-selection cycling produced positive return")
        vehicle_loss = legal_step(controller, 0, injected_outcome="vehicle-loss")
        require(vehicle_loss["reward"]["raw"]["vehicle_loss_count"] == 1, "actual-engine vehicle-loss component did not fire")
        require(vehicle_loss["reward"]["components"][6]["weighted"] == -2.0, "vehicle-loss coefficient drifted")
        controller.close(timeout)
        waste = {
            "construction_return": construction_return,
            "cycling_return": sum(item["reward"]["scalar"] for item in cycling),
            "duplicate_attempt_advanced_ticks": duplicate["advanced_ticks"],
            "duplicate_attempt_rewarded": "reward" in duplicate,
            "idle_return": sum(item["reward"]["scalar"] for item in idle),
            "native_rejection_return": sum(item["reward"]["scalar"] for item in rejections),
            "vehicle_loss_return": vehicle_loss["reward"]["scalar"],
        }
    except Exception:
        controller.abort()
        raise

    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=root / "noop", timeout=timeout)
    controller = Controller(worker, 8102, contract, instance, "m06-noop")
    try:
        controller.reset()
        noop = [legal_step(controller, 0) for _ in range(32)]
        noop_return = sum(item["reward"]["scalar"] for item in noop)
        require(noop_return < 0.0 and all(item["reward"]["raw"]["noop"] == 1 for item in noop), "no-op farming was not penalized")
        controller.close(timeout)
    except Exception:
        controller.abort()
        raise

    worker = protocol.WorkerProcess.start(executable=executable, instance=instance, run_root=root / "bankruptcy", timeout=timeout)
    controller = Controller(worker, 8103, contract, instance, "m06-bankruptcy")
    try:
        controller.reset()
        bankrupt = legal_step(controller, 0, injected_outcome="bankruptcy")
        termination = bankrupt["termination"]
        require(termination["reason"] == "BANKRUPTCY" and termination["terminal"] and not termination["bootstrap"] and termination["trainable"], "bankruptcy termination semantics drifted")
        require(bankrupt["reward"]["raw"]["bankruptcy"] == 1 and bankrupt["reward"]["scalar"] <= -8.0, "bankruptcy penalty missing")
        final_observation = controller.observe()
        final_sha256, _ = m06_trajectory.observation_sha256(final_observation)
        controller.close(timeout)
    except Exception:
        controller.abort()
        raise
    return waste | {
        "bankruptcy_final_observation_sha256": final_sha256,
        "bankruptcy_return": bankrupt["reward"]["scalar"],
        "bankruptcy_terminal": termination["terminal"],
        "bankruptcy_bootstrap": termination["bootstrap"],
        "noop_return": noop_return,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    executable = args.executable.resolve()
    instance_dir = args.instance_dir.resolve()
    artifact_root = args.artifact_root.resolve()
    require(executable.is_file(), f"executable does not exist: {executable}")
    require(instance_dir.is_dir(), f"instance directory does not exist: {instance_dir}")
    artifact_root.mkdir(parents=True, exist_ok=False)
    validate_native_delta(root)
    contract = validate_m06_reward_contract.validate(
        root / "config/v1/m06-reward-trajectory-contract.json",
        root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json",
    )
    instances = sorted(instance_dir.glob("m02-template-*.json"))
    require(len(instances) == 8, "M06 campaign requires all eight frozen M02 templates")
    bundle = m06_trajectory.TrajectoryBundle(
        {
            "campaign": "m06-actual-engine",
            "composed_source_identity_sha256": M06_COMPOSED_SOURCE_IDENTITY,
            "executable_sha256": sha256_file(executable),
            "reward_contract_sha256": sha256_file(root / "config/v1/m06-reward-trajectory-contract.json"),
        }
    )
    templates = []
    horizon = None
    for number, instance in enumerate(instances, 1):
        evidence, template_horizon = run_service_template(
            executable,
            instance,
            artifact_root / "templates" / instance.stem,
            contract,
            8000 + number,
            args.timeout,
            bundle=bundle if number == 1 else None,
            continue_to_horizon=number == 1,
        )
        templates.append({"template_id": instance.stem, **evidence})
        if template_horizon is not None:
            horizon = template_horizon
        print(f"M06_REWARD_TEMPLATE=PASS template={instance.stem} transitions={evidence['transitions_to_service']} delivered={evidence['delivered_passengers']}")
    require(horizon is not None, "horizon evidence was not produced")
    bundle_path = artifact_root / "trajectory"
    trajectory_manifest = bundle.write(bundle_path)
    loaded = m06_trajectory.load_bundle(bundle_path)
    require(loaded == trajectory_manifest, "trajectory round trip changed the manifest")
    require(trajectory_manifest["record_count"] == 128, "actual rollout segment did not exercise the 128-transition bound")
    exploits = run_exploits(executable, instances[0], artifact_root / "exploits", contract, args.timeout)
    manifest = {
        "actual_engine_templates": templates,
        "executable_sha256": sha256_file(executable),
        "exploit_campaign": exploits,
        "horizon_and_rollover": horizon,
        "native_delta": {
            "composed_source_identity_sha256": M06_COMPOSED_SOURCE_IDENTITY,
            "patch_sha256": M06_PATCH_SHA256,
            "result_tree": M06_RESULT_TREE,
            "series_sha256": M06_SERIES_SHA256,
        },
        "reward_compatibility_sha256": contract["identity"]["compatibility_sha256"],
        "reward_contract_sha256": sha256_file(root / "config/v1/m06-reward-trajectory-contract.json"),
        "schema_version": "openttd-rl-v1-m06-reward-oracle-report-1",
        "status": "PASS",
        "trajectory": {
            "bundle_sha256": trajectory_manifest["bundle_sha256"],
            "observation_blob_count": len(trajectory_manifest["observation_blobs"]),
            "record_count": trajectory_manifest["record_count"],
            "round_trip": "PASS",
        },
    }
    report_schema_path = root / "docs/project/schema/v1-m06-reward-oracle-report.schema.json"
    require(sha256_file(report_schema_path) == REPORT_SCHEMA_SHA256, "M06 reward oracle report schema drifted")
    report_schema = validate_m06_reward_contract.load_strict_json(report_schema_path)
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
        print(f"M06_REWARD_ORACLE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M06_REWARD_ORACLE=PASS "
        f"templates={len(manifest['actual_engine_templates'])} trajectory_records={manifest['trajectory']['record_count']} "
        f"bundle_sha256={manifest['trajectory']['bundle_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
