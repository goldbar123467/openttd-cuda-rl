#!/usr/bin/env python3
"""Train and evaluate every M08 architecture against the frozen live OpenTTD environment."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import pathlib
import subprocess
import sys
import time
from typing import Any

import m08_trainer_client
import run_m07_cpu_ppo as m07
import validate_m06_reward_contract
import validate_m08_architecture_contract


class M08LiveError(RuntimeError):
    """The M08 live architecture campaign failed closed."""


ENVIRONMENT_COUNT = 4
ROLLOUT_LENGTH = 32
MINIBATCH_SIZE = 32
OPTIMIZATION_EPOCHS = 4
RUN_SEED = 2_026_080_108
M06_EXECUTABLE_SHA256 = "765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c"
M08_COMPATIBILITY_SHA256 = "52c8b622b79d793e85ef749822e6886cd7cdda63194a471d38ab25da910e101d"
ARCHITECTURE_DEVICES = [
    ("structured-mlp-v1", "cpu"),
    ("spatial-cnn-v1", "cuda:0"),
    ("combined-cnn-mlp-v1", "cuda:0"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M08LiveError(message)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def spatial(observation: dict[str, Any]) -> list[float]:
    tensor = observation["spatial"]
    values = tensor["data"]
    require(
        tensor["shape"] == [32, 32, 32]
        and tensor["logical_order"] == "channel-y-x"
        and len(values) == 32 * 32 * 32,
        "M04 spatial shape/order drifted",
    )
    require(
        all(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in values),
        "M04 spatial values left the frozen finite [0,1] range",
    )
    return values


def train_architecture(
    client: m08_trainer_client.TrainerClient,
    openttd: pathlib.Path,
    templates: list[pathlib.Path],
    artifact_root: pathlib.Path,
    reward_contract: dict[str, Any],
    updates: int,
    timeout: float,
) -> dict[str, Any]:
    environments = [
        m07.start_environment(openttd, templates, artifact_root, reward_contract, index, 0, timeout, "train")
        for index in range(ENVIRONMENT_COUNT)
    ]
    update_records: list[dict[str, Any]] = []
    completed_episodes: list[dict[str, Any]] = []
    total_inference_ns = 0
    total_update_ns = 0
    try:
        for update_index in range(updates):
            transitions: list[m08_trainer_client.Transition] = []
            rollout_rewards: list[float] = []
            for _time_index in range(ROLLOUT_LENGTH):
                structured_rows = [m07.structured(environment.observation) for environment in environments]
                spatial_rows = [spatial(environment.observation) for environment in environments]
                masks = [m07.legal_mask(environment.mask) for environment in environments]
                inference_started = time.monotonic_ns()
                actions = client.act(structured_rows, spatial_rows, masks)
                total_inference_ns += time.monotonic_ns() - inference_started
                step_results: list[dict[str, Any]] = []
                next_observations: list[dict[str, Any]] = []
                next_masks: list[list[int]] = []
                for environment, action in zip(environments, actions, strict=True):
                    require(masks[environment.environment_id][action.action] == 1, "M08 trainer sampled an illegal action")
                    result = environment.controller.step(action.action)
                    require(result["termination"]["trainable"], "M08 encountered an untrainable transition")
                    next_observation = environment.controller.observe()
                    terminated = result["termination"]["reason"] != "NONE"
                    next_mask = [1] + [0] * 40 if terminated else m07.legal_mask(environment.controller.mask())
                    step_results.append(result)
                    next_observations.append(next_observation)
                    next_masks.append(next_mask)
                inference_started = time.monotonic_ns()
                next_predictions = client.act(
                    [m07.structured(observation) for observation in next_observations],
                    [spatial(observation) for observation in next_observations],
                    next_masks,
                    deterministic=True,
                )
                total_inference_ns += time.monotonic_ns() - inference_started
                replacements: list[tuple[int, m07.Environment]] = []
                for environment, action, result, next_observation, next_mask, next_prediction in zip(
                    environments,
                    actions,
                    step_results,
                    next_observations,
                    next_masks,
                    next_predictions,
                    strict=True,
                ):
                    termination = result["termination"]
                    reward = float(result["reward"]["scalar"])
                    rollout_rewards.append(reward)
                    environment.episode_return += reward
                    environment.episode_length += 1
                    transitions.append(m08_trainer_client.Transition(
                        structured=m07.structured(environment.observation),
                        spatial=spatial(environment.observation),
                        legal_mask=m07.legal_mask(environment.mask),
                        action=action.action,
                        old_log_probability=action.log_probability,
                        old_value=action.value,
                        reward=reward,
                        next_value=next_prediction.value if termination["bootstrap"] else 0.0,
                        bootstrap=bool(termination["bootstrap"]),
                        continuation=termination["reason"] == "NONE",
                    ))
                    environment.observation = next_observation
                    if termination["reason"] == "NONE":
                        environment.mask = {"legal": next_mask}
                    else:
                        completed_episodes.append({
                            "environment_id": environment.environment_id,
                            "episode_index": environment.episode_index,
                            "length": environment.episode_length,
                            "reason": termination["reason"],
                            "return": environment.episode_return,
                            "template_id": environment.template.stem,
                        })
                        environment.controller.close(timeout)
                        replacements.append((
                            environment.environment_id,
                            m07.start_environment(
                                openttd,
                                templates,
                                artifact_root,
                                reward_contract,
                                environment.environment_id,
                                environment.episode_index + 1,
                                timeout,
                                "train",
                            ),
                        ))
                for index, replacement in replacements:
                    environments[index] = replacement
            require(len(transitions) == ROLLOUT_LENGTH * ENVIRONMENT_COUNT, "M08 rollout size drifted")
            update_started = time.monotonic_ns()
            metrics = client.update(transitions)
            total_update_ns += time.monotonic_ns() - update_started
            record = dataclasses.asdict(metrics) | {
                "mean_rollout_reward": sum(rollout_rewards) / len(rollout_rewards),
                "minimum_rollout_reward": min(rollout_rewards),
                "maximum_rollout_reward": max(rollout_rewards),
            }
            update_records.append(record)
            print(
                f"M08_LIVE_UPDATE update={update_index + 1}/{updates} samples={metrics.samples} "
                f"reward={record['mean_rollout_reward']:.6f}",
                flush=True,
            )
        return {
            "accepted_samples": update_records[-1]["samples"],
            "completed_episodes": completed_episodes,
            "inference_elapsed_ns": total_inference_ns,
            "trainer_update_elapsed_ns": total_update_ns,
            "updates": update_records,
        }
    except Exception:
        for environment in environments:
            environment.controller.abort()
        raise
    finally:
        live = [environment for environment in environments if environment.controller.worker.process.poll() is None]
        if live:
            m07.close_environments(live, timeout)


def evaluate_architecture(
    client: m08_trainer_client.TrainerClient,
    openttd: pathlib.Path,
    template: pathlib.Path,
    artifact_root: pathlib.Path,
    reward_contract: dict[str, Any],
    steps: int,
    timeout: float,
) -> dict[str, Any]:
    environment = m07.start_environment(openttd, [template], artifact_root, reward_contract, 0, 90_000, timeout, "evaluation")
    try:
        for _step in range(steps):
            mask = m07.legal_mask(environment.mask)
            action = client.act(
                [m07.structured(environment.observation)],
                [spatial(environment.observation)],
                [mask],
                deterministic=True,
            )[0].action
            result = environment.controller.step(action)
            environment.episode_return += float(result["reward"]["scalar"])
            environment.episode_length += 1
            environment.observation = environment.controller.observe()
            if result["termination"]["reason"] != "NONE":
                break
            environment.mask = environment.controller.mask()
        snapshot = result["snapshot"]
        evaluation = {
            "delivered_passengers": snapshot["company"]["delivered_passengers"],
            "income": snapshot["company"]["income"],
            "length": environment.episode_length,
            "return": environment.episode_return,
            "template_id": template.stem,
        }
        environment.controller.close(timeout)
        return evaluation
    except Exception:
        environment.controller.abort()
        raise


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    trainer = args.trainer.resolve()
    openttd = args.openttd.resolve()
    artifact_root = args.artifact_root.resolve()
    instance_dir = args.instance_dir.resolve()
    require(args.updates > 0 and args.evaluation_steps > 0, "updates and evaluation steps must be positive")
    require(trainer.is_file() and openttd.is_file(), "trainer/OpenTTD executable is missing")
    require(sha256_file(openttd) == M06_EXECUTABLE_SHA256, "frozen OpenTTD executable identity drifted")
    require(not artifact_root.exists(), "artifact root already exists")
    artifact_root.mkdir(parents=True)
    training_templates, development_templates = m07.partition_templates(root, instance_dir)
    reward_contract = validate_m06_reward_contract.validate(
        root / "config/v1/m06-reward-trajectory-contract.json",
        root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json",
    )
    architecture_contract = validate_m08_architecture_contract.validate(
        root / "config/v1/m08-architecture-cuda-contract.json",
        root / "docs/project/schema/v1-m08-architecture-cuda-contract.schema.json",
    )
    require(
        architecture_contract["identity"]["compatibility_sha256"] == M08_COMPATIBILITY_SHA256,
        "M08 architecture compatibility drifted",
    )
    architecture_results: list[dict[str, Any]] = []
    for architecture_index, (architecture, device) in enumerate(ARCHITECTURE_DEVICES):
        architecture_root = artifact_root / architecture
        client = m08_trainer_client.TrainerClient.start(
            trainer,
            architecture=architecture,
            device=device,
            run_seed=RUN_SEED,
            rollout_length=ROLLOUT_LENGTH,
            environment_count=ENVIRONMENT_COUNT,
            minibatch_size=MINIBATCH_SIZE,
            optimization_epochs=OPTIMIZATION_EPOCHS,
            diagnostic_root=architecture_root / "diagnostics",
        )
        started = time.monotonic_ns()
        try:
            training = train_architecture(
                client,
                openttd,
                training_templates,
                architecture_root,
                reward_contract,
                args.updates,
                args.timeout,
            )
            evaluation = evaluate_architecture(
                client,
                openttd,
                development_templates[architecture_index % len(development_templates)],
                architecture_root,
                reward_contract,
                args.evaluation_steps,
                args.timeout,
            )
            client.close()
        except Exception:
            client.abort()
            raise
        architecture_results.append({
            "architecture": architecture,
            "device": device,
            "elapsed_ns": time.monotonic_ns() - started,
            "evaluation": evaluation,
            "training": training,
        })
    repository_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    result = {
        "schema_version": "openttd-rl-v1-m08-live-architectures-1",
        "status": "PASS",
        "compatibility": {
            "architecture": M08_COMPATIBILITY_SHA256,
            "openttd_executable_sha256": M06_EXECUTABLE_SHA256,
            "trainer_executable_sha256": sha256_file(trainer),
        },
        "configuration": {
            "environment_count": ENVIRONMENT_COUNT,
            "evaluation_steps": args.evaluation_steps,
            "minibatch_size": MINIBATCH_SIZE,
            "optimization_epochs": OPTIMIZATION_EPOCHS,
            "rollout_length": ROLLOUT_LENGTH,
            "run_seed": RUN_SEED,
            "updates": args.updates,
        },
        "architectures": architecture_results,
        "environment_semantics": {
            "observation_encoding": "cpu-frozen-m04-direct-copy",
            "openttd_simulation": "cpu-frozen-m06-executable",
            "final_evaluation_accessed": False,
            "training_templates": [path.stem for path in training_templates],
            "development_templates": [path.stem for path in development_templates],
        },
        "repository_commit": repository_commit,
    }
    result["manifest_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    (artifact_root / "run-manifest.json").write_bytes(canonical_bytes(result) + b"\n")
    print(
        "M08_LIVE_ARCHITECTURES=PASS architectures=3 "
        f"samples_each={args.updates * ROLLOUT_LENGTH * ENVIRONMENT_COUNT} artifact_root={artifact_root}",
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--trainer", type=pathlib.Path, required=True)
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--instance-dir", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--updates", type=int, default=2)
    parser.add_argument("--evaluation-steps", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print(f"M08_LIVE_ARCHITECTURES=FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
