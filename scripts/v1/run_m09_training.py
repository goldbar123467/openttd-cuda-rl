#!/usr/bin/env python3
"""Run the preregistered matched M09 training campaign without final-scenario access."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import pathlib
import subprocess
import sys
import time
from typing import Any

import m08_trainer_client
import run_m07_cpu_ppo as m07
import run_m08_live_architectures as m08
import validate_m06_reward_contract
import validate_m09_evaluation_contract


class M09TrainingError(RuntimeError):
    """The matched M09 training campaign failed closed."""


M06_EXECUTABLE_SHA256 = "765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c"
M09_COMPATIBILITY_SHA256 = "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e"
DEV_EVALUATION_STEPS = 128
ARCHITECTURE_DEVICES = {
    "structured-mlp-v1": "cpu",
    "spatial-cnn-v1": "cuda:0",
    "combined-cnn-mlp-v1": "cuda:0",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M09TrainingError(message)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def episode_metrics(
    environment: m07.Environment,
    result: dict[str, Any],
    *,
    capital_spend: int,
    invalid_actions: int,
    non_wait_actions: int,
    starting_balance: int,
) -> dict[str, Any]:
    snapshot = result["snapshot"]
    company = snapshot["company"]
    spatial_values = environment.observation["spatial"]["data"]
    catchment = spatial_values[31 * 32 * 32:32 * 32 * 32]
    operating_profit = company["income"] + company["expenses"]
    vehicles = round(environment.observation["structured"]["data"][6] * 8)
    return {
        "action_efficiency": non_wait_actions / environment.episode_length,
        "actions": environment.episode_length,
        "bankruptcy": result["termination"]["reason"] == "BANKRUPTCY",
        "coverage": sum(value > 0 for value in catchment) / len(catchment),
        "final_balance": company["balance"],
        "infrastructure_cost": capital_spend,
        "invalid_actions": invalid_actions,
        "net_profit": company["balance"] - starting_balance,
        "operating_profit": operating_profit,
        "passenger_deliveries": company["delivered_passengers"],
        "profitable_vehicles": int(vehicles == 1 and operating_profit > 0),
        "return": environment.episode_return,
        "roi": operating_profit / capital_spend if capital_spend else None,
        "route_profit": operating_profit,
        "station_rating": None,
        "survival": result["termination"]["reason"] != "BANKRUPTCY",
        "template_id": environment.template.stem,
    }


def evaluate_development(
    client: m08_trainer_client.TrainerClient,
    openttd: pathlib.Path,
    templates: list[pathlib.Path],
    artifact_root: pathlib.Path,
    reward_contract: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    episodes: list[dict[str, Any]] = []
    for index, template in enumerate(templates):
        environment = m07.start_environment(
            openttd,
            [template],
            artifact_root,
            reward_contract,
            index,
            90_000 + index,
            timeout,
            "development-selection",
        )
        capital_spend = 0
        invalid_actions = 0
        non_wait_actions = 0
        try:
            for _step in range(DEV_EVALUATION_STEPS):
                mask = m07.legal_mask(environment.mask)
                prediction = client.act(
                    [m07.structured(environment.observation)],
                    [m08.spatial(environment.observation)],
                    [mask],
                    deterministic=True,
                )[0]
                require(mask[prediction.action] == 1, "development policy selected an illegal action")
                result = environment.controller.step(prediction.action)
                raw = result["reward"]["raw"]
                capital_spend += raw["capital_spend"]
                invalid_actions += raw["native_rejected"]
                non_wait_actions += prediction.action != 0 and not raw["native_rejected"]
                environment.episode_return += float(result["reward"]["scalar"])
                environment.episode_length += 1
                environment.observation = environment.controller.observe()
                if result["termination"]["reason"] != "NONE":
                    break
                environment.mask = environment.controller.mask()
            episodes.append(episode_metrics(
                environment,
                result,
                capital_spend=capital_spend,
                invalid_actions=invalid_actions,
                non_wait_actions=non_wait_actions,
                starting_balance=100_000,
            ))
            environment.controller.close(timeout)
        except Exception:
            environment.controller.abort()
            raise
    return {
        "episodes": episodes,
        "mean_final_balance": sum(item["final_balance"] for item in episodes) / len(episodes),
        "mean_invalid_actions": sum(item["invalid_actions"] for item in episodes) / len(episodes),
        "mean_operating_profit": sum(item["operating_profit"] for item in episodes) / len(episodes),
        "mean_passenger_deliveries": sum(item["passenger_deliveries"] for item in episodes) / len(episodes),
        "reliably_profitable": all(
            item["operating_profit"] > 0 and item["passenger_deliveries"] > 0 and item["survival"]
            for item in episodes
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    trainer = args.trainer.resolve()
    openttd = args.openttd.resolve()
    instance_dir = args.instance_dir.resolve()
    artifact_root = args.artifact_root.resolve()
    require(trainer.is_file() and openttd.is_file(), "trainer/OpenTTD executable is missing")
    require(sha256_file(openttd) == M06_EXECUTABLE_SHA256, "training OpenTTD executable identity drifted")
    require(not artifact_root.exists(), "artifact root already exists")
    contract = validate_m09_evaluation_contract.validate(
        root / "config/v1/m09-evaluation-contract.json",
        root / "docs/project/schema/v1-m09-evaluation-contract.schema.json",
    )
    require(contract["identity"]["compatibility_sha256"] == M09_COMPATIBILITY_SHA256, "M09 contract drifted")
    training_templates, development_templates = m07.partition_templates(root, instance_dir)
    final_paths = [instance_dir / f"{template}.json" for template in contract["partitions"]["final_evaluation"]]
    require(all(path.is_file() for path in final_paths), "final templates must exist for later independent evaluation")
    # Deliberately do not open final_paths: this process may only train and select on visible splits.
    reward_contract = validate_m06_reward_contract.validate(
        root / "config/v1/m06-reward-trajectory-contract.json",
        root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json",
    )
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout
    require(status == "", "accepted training requires a clean committed repository")
    repository_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    artifact_root.mkdir(parents=True)
    budget = contract["training_budget"]
    runs: list[dict[str, Any]] = []
    for architecture in budget["architectures"]:
        for run_seed in budget["run_seeds"]:
            run_root = artifact_root / "runs" / architecture / str(run_seed)
            client = m08_trainer_client.TrainerClient.start(
                trainer,
                architecture=architecture,
                device=ARCHITECTURE_DEVICES[architecture],
                run_seed=run_seed,
                rollout_length=budget["rollout_length"],
                environment_count=budget["environment_count"],
                minibatch_size=budget["minibatch_size"],
                optimization_epochs=budget["optimization_epochs"],
                diagnostic_root=run_root / "diagnostics",
            )
            started = time.monotonic_ns()
            try:
                training = m08.train_architecture(
                    client,
                    openttd,
                    training_templates,
                    run_root,
                    reward_contract,
                    budget["updates"],
                    args.timeout,
                )
                require(training["accepted_samples"] == budget["accepted_samples_per_run"], "training sample budget drifted")
                development = evaluate_development(
                    client,
                    openttd,
                    development_templates,
                    run_root,
                    reward_contract,
                    args.timeout,
                )
                training_mean_reward = sum(update["mean_rollout_reward"] for update in training["updates"]) / len(training["updates"])
                package_id, package_path = client.export_evaluation_model(
                    artifact_root / "packages",
                    repository_commit=repository_commit,
                    training_mean_reward=training_mean_reward,
                )
                require(package_path == artifact_root / "packages" / package_id, "export escaped its content address")
                client.close()
            except Exception:
                client.abort()
                raise
            runs.append({
                "accepted_samples": training["accepted_samples"],
                "architecture": architecture,
                "completed_updates": training["updates"][-1]["update"],
                "development": development,
                "device": ARCHITECTURE_DEVICES[architecture],
                "elapsed_ns": time.monotonic_ns() - started,
                "package": {"id": package_id, "path": str(package_path.relative_to(artifact_root))},
                "run_seed": run_seed,
                "training_mean_reward": training_mean_reward,
                "training_updates": training["updates"],
            })
            print(
                f"M09_TRAINING_RUN architecture={architecture} seed={run_seed} "
                f"profit={development['mean_operating_profit']:.3f} passengers={development['mean_passenger_deliveries']:.3f}",
                flush=True,
            )
    expected_pairs = {(architecture, seed) for architecture in budget["architectures"] for seed in budget["run_seeds"]}
    require({(run["architecture"], run["run_seed"]) for run in runs} == expected_pairs, "matched run matrix is incomplete")
    require(all(run["accepted_samples"] == budget["accepted_samples_per_run"] for run in runs), "unfair accepted-sample budget")
    selected: dict[str, dict[str, Any]] = {}
    for architecture in budget["architectures"]:
        candidates = [run for run in runs if run["architecture"] == architecture]
        eligible = [run for run in candidates if run["development"]["reliably_profitable"]]
        pool = eligible or candidates
        best = max(pool, key=lambda run: (
            run["development"]["mean_operating_profit"],
            run["development"]["mean_passenger_deliveries"],
            run["development"]["mean_final_balance"],
            -run["development"]["mean_invalid_actions"],
            -run["run_seed"],
        ))
        selected[architecture] = {"package": best["package"], "run_seed": best["run_seed"]}
    result = {
        "schema_version": "openttd-rl-v1-m09-training-campaign-1",
        "status": "PASS",
        "budget": budget,
        "compatibility": {
            "evaluation": M09_COMPATIBILITY_SHA256,
            "openttd_executable_sha256": M06_EXECUTABLE_SHA256,
            "trainer_executable_sha256": sha256_file(trainer),
        },
        "final_evaluation_accessed": False,
        "repository_commit": repository_commit,
        "runs": runs,
        "selected_on_development": selected,
    }
    result["manifest_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    (artifact_root / "training-manifest.json").write_bytes(canonical_bytes(result) + b"\n")
    print(f"M09_TRAINING=PASS runs={len(runs)} final_evaluation_accessed=false", flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--trainer", type=pathlib.Path, required=True)
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--instance-dir", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print(f"M09_TRAINING=FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
