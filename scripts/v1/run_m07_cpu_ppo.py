#!/usr/bin/env python3
"""Run batched native CPU PPO against the frozen live M06 bus environment."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import pathlib
import random
import subprocess
import sys
import time
from typing import Any

import m07_trainer_client
import m03_bridge_protocol as protocol
import run_m06_reward_trajectory
import validate_m06_reward_contract


class M07CpuPpoError(RuntimeError):
    """The live M07 CPU PPO campaign failed closed."""


ENVIRONMENT_COUNT = 4
ROLLOUT_LENGTH = 32
MINIBATCH_SIZE = 32
OPTIMIZATION_EPOCHS = 4
RUN_SEED = 2_026_080_107
M06_SOURCE_IDENTITY = "98693ab0595fb26612079683a192a12f7bce6bb4cb25a7edf895244c50c568a2"
M06_EXECUTABLE_SHA256 = "765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c"
PPO_COMPATIBILITY_SHA256 = "1b1f13cfb036afed82a630949ee727f6f20a94241923ab3a1aa60a1ec763f0de"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M07CpuPpoError(message)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclasses.dataclass
class Environment:
    environment_id: int
    episode_index: int
    template: pathlib.Path
    controller: run_m06_reward_trajectory.Controller
    observation: dict[str, Any]
    mask: dict[str, Any]
    episode_return: float = 0.0
    episode_length: int = 0


def start_environment(
    executable: pathlib.Path,
    templates: list[pathlib.Path],
    artifact_root: pathlib.Path,
    contract: dict[str, Any],
    environment_id: int,
    episode_index: int,
    timeout: float,
    phase: str,
) -> Environment:
    template = templates[(environment_id + episode_index * ENVIRONMENT_COUNT) % len(templates)]
    run_root = artifact_root / "workers" / phase / f"environment-{environment_id:02d}" / f"episode-{episode_index:05d}"
    worker = protocol.WorkerProcess.start(executable=executable, instance=template, run_root=run_root, timeout=timeout)
    session = 70_000_000 + environment_id * 100_000 + episode_index
    controller = run_m06_reward_trajectory.Controller(
        worker,
        session,
        contract,
        template,
        f"m07-{phase}-e{environment_id}-p{episode_index}",
    )
    try:
        controller.reset()
        observation = controller.observe()
        mask = controller.mask()
        return Environment(environment_id, episode_index, template, controller, observation, mask)
    except Exception:
        controller.abort()
        raise


def close_environments(environments: list[Environment], timeout: float) -> None:
    errors: list[Exception] = []
    for environment in environments:
        try:
            environment.controller.close(timeout)
        except Exception as exc:  # pragma: no cover - cleanup aggregation
            environment.controller.abort()
            errors.append(exc)
    if errors:
        raise M07CpuPpoError(f"{len(errors)} environment workers failed during close: {errors[0]}")


def structured(observation: dict[str, Any]) -> list[float]:
    values = observation["structured"]["data"]
    require(observation["structured"]["shape"] == [256] and len(values) == 256, "M04 structured shape drifted")
    require(all(isinstance(value, (int, float)) and math.isfinite(value) for value in values), "nonfinite structured input")
    return values


def legal_mask(mask: dict[str, Any]) -> list[int]:
    values = mask["legal"]
    require(len(values) == 41 and all(value in (0, 1) for value in values) and any(values), "M05 legal mask drifted")
    return values


def train(
    client: m07_trainer_client.TrainerClient,
    executable: pathlib.Path,
    templates: list[pathlib.Path],
    artifact_root: pathlib.Path,
    contract: dict[str, Any],
    updates: int,
    timeout: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    environments = [
        start_environment(executable, templates, artifact_root, contract, index, 0, timeout, "train")
        for index in range(ENVIRONMENT_COUNT)
    ]
    completed_episodes: list[dict[str, Any]] = []
    update_records: list[dict[str, Any]] = []
    latest_snapshot: dict[int, dict[str, Any]] = {}
    latest_observation: dict[int, dict[str, Any]] = {}
    try:
        for update_index in range(updates):
            transitions: list[m07_trainer_client.Transition] = []
            rollout_rewards: list[float] = []
            for _time_index in range(ROLLOUT_LENGTH):
                observations = [structured(environment.observation) for environment in environments]
                masks = [legal_mask(environment.mask) for environment in environments]
                actions = client.act(observations, masks)
                step_results: list[dict[str, Any]] = []
                next_observations: list[dict[str, Any]] = []
                next_masks: list[list[int]] = []
                for environment, action in zip(environments, actions):
                    require(masks[environment.environment_id][action.action] == 1, "native trainer sampled an illegal action")
                    result = environment.controller.step(action.action)
                    require(result["termination"]["trainable"], f"untrainable transition: {result['termination']}")
                    next_observation = environment.controller.observe()
                    terminated = result["termination"]["reason"] != "NONE"
                    if terminated:
                        next_mask = [1] + [0] * 40
                    else:
                        next_mask = legal_mask(environment.controller.mask())
                    step_results.append(result)
                    next_observations.append(next_observation)
                    next_masks.append(next_mask)
                    latest_snapshot[environment.environment_id] = result["snapshot"]
                    latest_observation[environment.environment_id] = next_observation
                next_predictions = client.act(
                    [structured(observation) for observation in next_observations],
                    next_masks,
                    deterministic=True,
                )
                replacements: list[tuple[int, Environment]] = []
                for environment, action, result, next_observation, next_mask, next_prediction in zip(
                    environments, actions, step_results, next_observations, next_masks, next_predictions
                ):
                    termination = result["termination"]
                    reward = float(result["reward"]["scalar"])
                    rollout_rewards.append(reward)
                    environment.episode_return += reward
                    environment.episode_length += 1
                    transitions.append(
                        m07_trainer_client.Transition(
                            observation=structured(environment.observation),
                            legal_mask=legal_mask(environment.mask),
                            action=action.action,
                            old_log_probability=action.log_probability,
                            old_value=action.value,
                            reward=reward,
                            next_value=next_prediction.value if termination["bootstrap"] else 0.0,
                            bootstrap=bool(termination["bootstrap"]),
                            continuation=termination["reason"] == "NONE",
                        )
                    )
                    environment.observation = next_observation
                    if termination["reason"] == "NONE":
                        environment.mask = {"legal": next_mask}
                    else:
                        completed_episodes.append(
                            {
                                "environment_id": environment.environment_id,
                                "episode_index": environment.episode_index,
                                "length": environment.episode_length,
                                "reason": termination["reason"],
                                "return": environment.episode_return,
                                "template_id": environment.template.stem,
                            }
                        )
                        environment.controller.close(timeout)
                        replacements.append(
                            (
                                environment.environment_id,
                                start_environment(
                                    executable,
                                    templates,
                                    artifact_root,
                                    contract,
                                    environment.environment_id,
                                    environment.episode_index + 1,
                                    timeout,
                                    "train",
                                ),
                            )
                        )
                for index, replacement in replacements:
                    environments[index] = replacement
            require(len(transitions) == ROLLOUT_LENGTH * ENVIRONMENT_COUNT, "rollout size drifted")
            metrics = client.update(transitions)
            record = dataclasses.asdict(metrics) | {
                "mean_rollout_reward": sum(rollout_rewards) / len(rollout_rewards),
                "minimum_rollout_reward": min(rollout_rewards),
                "maximum_rollout_reward": max(rollout_rewards),
            }
            update_records.append(record)
            print(
                f"M07_CPU_PPO_UPDATE update={metrics.update}/{updates} steps={metrics.samples} "
                f"reward={record['mean_rollout_reward']:.6f} entropy={metrics.entropy:.6f}",
                flush=True,
            )
        summary = {
            "completed_episode_count": len(completed_episodes),
            "latest_company": {
                str(environment_id): {
                    "balance": snapshot["company"]["balance"],
                    "buses": round(latest_observation[environment_id]["structured"]["data"][6] * 8),
                    "delivered_passengers": snapshot["company"]["delivered_passengers"],
                    "income": snapshot["company"]["income"],
                    "routes": round(latest_observation[environment_id]["structured"]["data"][9] * 8),
                }
                for environment_id, snapshot in sorted(latest_snapshot.items())
            },
            "mean_completed_episode_return": (
                sum(item["return"] for item in completed_episodes) / len(completed_episodes)
                if completed_episodes
                else None
            ),
        }
        return update_records, completed_episodes, summary
    except Exception:
        for environment in environments:
            environment.controller.abort()
        raise
    finally:
        live = [environment for environment in environments if environment.controller.worker.process.poll() is None]
        if live:
            close_environments(live, timeout)


def evaluate(
    client: m07_trainer_client.TrainerClient,
    executable: pathlib.Path,
    templates: list[pathlib.Path],
    artifact_root: pathlib.Path,
    contract: dict[str, Any],
    timeout: float,
    *,
    deterministic_policy: bool,
    evaluation_steps: int,
) -> dict[str, Any]:
    mode = "policy" if deterministic_policy else "random"
    generator = random.Random(RUN_SEED ^ 0xE7A1_0000)
    episodes: list[dict[str, Any]] = []
    for index, template in enumerate(templates):
        environment = start_environment(
            executable,
            [template],
            artifact_root,
            contract,
            index,
            90_000 + index,
            timeout,
            f"evaluation-{mode}",
        )
        try:
            for _step in range(evaluation_steps):
                mask = legal_mask(environment.mask)
                if deterministic_policy:
                    action = client.act([structured(environment.observation)], [mask], deterministic=True)[0].action
                else:
                    action = generator.choice([action_index for action_index, legal in enumerate(mask) if legal])
                result = environment.controller.step(action)
                environment.episode_return += float(result["reward"]["scalar"])
                environment.episode_length += 1
                environment.observation = environment.controller.observe()
                if result["termination"]["reason"] != "NONE":
                    break
                environment.mask = environment.controller.mask()
            snapshot = result["snapshot"]
            episodes.append(
                {
                    "delivered_passengers": snapshot["company"]["delivered_passengers"],
                    "income": snapshot["company"]["income"],
                    "length": environment.episode_length,
                    "return": environment.episode_return,
                    "routes": round(environment.observation["structured"]["data"][9] * 8),
                    "template_id": template.stem,
                    "vehicles": round(environment.observation["structured"]["data"][6] * 8),
                }
            )
            environment.controller.close(timeout)
        except Exception:
            environment.controller.abort()
            raise
    return {
        "episodes": episodes,
        "mean_delivered_passengers": sum(item["delivered_passengers"] for item in episodes) / len(episodes),
        "mean_return": sum(item["return"] for item in episodes) / len(episodes),
        "service_successes": sum(item["delivered_passengers"] > 0 and item["income"] > 0 for item in episodes),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    trainer_executable = args.trainer.resolve()
    openttd_executable = args.openttd.resolve()
    instance_dir = args.instance_dir.resolve()
    artifact_root = args.artifact_root.resolve()
    require(args.updates > 0 and args.evaluation_steps > 0, "updates and evaluation steps must be positive")
    require(trainer_executable.is_file() and openttd_executable.is_file(), "trainer/OpenTTD executable is missing")
    require(sha256_file(openttd_executable) == M06_EXECUTABLE_SHA256, "OpenTTD executable identity drifted")
    require(not artifact_root.exists(), "artifact root already exists")
    artifact_root.mkdir(parents=True)
    templates = sorted(instance_dir.glob("m02-template-*.json"))
    require(len(templates) == 8, "live CPU PPO campaign requires all eight M02 templates")
    contract = validate_m06_reward_contract.validate(
        root / "config/v1/m06-reward-trajectory-contract.json",
        root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json",
    )
    repository_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    client = m07_trainer_client.TrainerClient.start(
        trainer_executable,
        run_seed=RUN_SEED,
        rollout_length=ROLLOUT_LENGTH,
        environment_count=ENVIRONMENT_COUNT,
        minibatch_size=MINIBATCH_SIZE,
        optimization_epochs=OPTIMIZATION_EPOCHS,
        diagnostic_root=artifact_root / "diagnostics",
    )
    started = time.monotonic_ns()
    try:
        random_result = evaluate(
            client,
            openttd_executable,
            templates[:4],
            artifact_root,
            contract,
            args.timeout,
            deterministic_policy=False,
            evaluation_steps=args.evaluation_steps,
        )
        updates, episodes, training_summary = train(
            client,
            openttd_executable,
            templates,
            artifact_root,
            contract,
            args.updates,
            args.timeout,
        )
        policy_result = evaluate(
            client,
            openttd_executable,
            templates[:4],
            artifact_root,
            contract,
            args.timeout,
            deterministic_policy=True,
            evaluation_steps=args.evaluation_steps,
        )
        checkpoint_id, checkpoint_path = client.checkpoint(
            artifact_root / "checkpoints",
            run_name="m07-live-cpu-development",
            repository_commit=repository_commit,
            source_build_identity=M06_SOURCE_IDENTITY,
            parent_checkpoint="",
        )
        client.close()
    except Exception:
        client.abort()
        raise
    elapsed_ns = time.monotonic_ns() - started
    expected_checkpoint_path = artifact_root / "checkpoints" / checkpoint_id
    require(checkpoint_path == expected_checkpoint_path, "trainer returned a checkpoint outside its content address")
    improved = (
        policy_result["mean_return"] > random_result["mean_return"]
        and policy_result["mean_delivered_passengers"] > random_result["mean_delivered_passengers"]
        and policy_result["service_successes"] == len(policy_result["episodes"])
        and policy_result["service_successes"] >= random_result["service_successes"]
    )
    result = {
        "schema_version": "openttd-rl-v1-m07-live-cpu-run-1",
        "status": "PASS" if improved else "READINESS_NOT_MET",
        "compatibility": {
            "m06_source_identity": M06_SOURCE_IDENTITY,
            "openttd_executable_sha256": M06_EXECUTABLE_SHA256,
            "ppo": PPO_COMPATIBILITY_SHA256,
            "trainer_executable_sha256": sha256_file(trainer_executable),
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
        "checkpoint": {"id": checkpoint_id, "path": f"checkpoints/{checkpoint_id}"},
        "elapsed_ns": elapsed_ns,
        "evaluation": {"improved_over_random": improved, "policy": policy_result, "random": random_result},
        "repository_commit": repository_commit,
        "training": {
            "completed_episodes": episodes,
            "summary": training_summary,
            "updates": updates,
        },
    }
    result["manifest_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    manifest_path = artifact_root / "run-manifest.json"
    manifest_path.write_bytes(canonical_bytes(result) + b"\n")
    print(
        f"M07_CPU_PPO={'PASS' if improved else 'READINESS_NOT_MET'} "
        f"random_return={random_result['mean_return']:.6f} policy_return={policy_result['mean_return']:.6f} "
        f"checkpoint={checkpoint_id}",
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
    parser.add_argument("--updates", type=int, default=32)
    parser.add_argument("--evaluation-steps", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        print(f"M07_CPU_PPO=FAIL {exc}", file=sys.stderr)
        return 1
    return 0 if result["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
