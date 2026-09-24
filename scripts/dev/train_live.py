#!/usr/bin/env python3
"""Run the existing C++ PPO trainer against real OpenTTD, outside release gates.

This uses the existing M08 live collector and game contract unchanged. Locally
compiled binary identities are recorded rather than compared with release hashes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

from local import ROOT, capture_source, positive, source_identity, write_json
import bridge_validation

sys.path.insert(0, str(ROOT / "scripts/v1"))
import m08_trainer_client  # noqa: E402
import run_m07_cpu_ppo as m07  # noqa: E402
import run_m08_live_architectures as m08  # noqa: E402
import validate_m06_reward_contract  # noqa: E402
from training_environment import training_episodes  # noqa: E402
from training_reward import BalancedEconomicReward, EconomicReward, ServicePotentialReward, UniversalDecisionCost  # noqa: E402
from live_checkpoint import checkpoint_collection, compatibility, start_trainer  # noqa: E402
from credit_trace import CreditTrace  # noqa: E402
from policy_inputs import spatial_validation  # noqa: E402


class ProgressLog:
    """Retain the existing collector's progress without changing its behavior."""

    def __init__(self, console, log):
        self.console, self.log = console, log

    def write(self, text):
        self.log.write(text)
        self.log.flush()
        return self.console.write(text)

    def flush(self):
        self.log.flush()
        self.console.flush()


@contextmanager
def collector_rollout_length(length):
    """Configure the frozen collector within one isolated development process."""
    if length not in (32, 64):
        raise ValueError("Development rollout length must be 32 or 64")
    original = m08.ROLLOUT_LENGTH
    m08.ROLLOUT_LENGTH = length
    try:
        yield
    finally:
        m08.ROLLOUT_LENGTH = original


def run(args: argparse.Namespace) -> None:
    validation = getattr(args, "bridge_validation", "reference")
    horizon = getattr(args, "episode_horizon", 512)
    training_reward = getattr(args, "training_reward", "native")
    entropy_coefficient = getattr(args, "entropy_coefficient", 0.01)
    gae_lambda = getattr(args, "gae_lambda", 0.95)
    if not math.isfinite(entropy_coefficient) or entropy_coefficient < 0:
        raise ValueError("Entropy coefficient must be finite and nonnegative")
    if not math.isfinite(gae_lambda) or not 0 <= gae_lambda <= 1:
        raise ValueError("GAE lambda must be finite and in [0,1]")
    rollout_length = getattr(args, "rollout_length", m08.ROLLOUT_LENGTH)
    bridge_validation.configure(validation)
    trainer, engine = args.trainer.resolve(), args.openttd.resolve()
    for executable in (trainer, engine):
        if not executable.is_file():
            raise ValueError(f"Executable is missing: {executable}")
    training, development = m07.partition_templates(ROOT, args.instance_dir.resolve())
    reward = validate_m06_reward_contract.validate(
        ROOT / "config/v1/m06-reward-trajectory-contract.json",
        ROOT / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    identity = source_identity()
    record = {"kind": "live-openttd-development-training", "status": "running",
              "claim": "development experiment; not a release or held-out evaluation",
              "source": identity, "architecture": args.architecture, "device": args.device,
              "platform": platform.platform(), "python": sys.version,
              "seed": args.seed, "requested_updates": args.updates,
              "bridge_validation": validation,
              "episode_action_horizon": horizon,
              "training_reward": training_reward,
              "entropy_coefficient": entropy_coefficient,
              "gae_lambda": gae_lambda,
              "credit_trace": bool(getattr(args, "credit_trace", False)),
              "spatial_validation": getattr(args, "spatial_validation", "reference"),
              "rollout_length": rollout_length, "environments": m08.ENVIRONMENT_COUNT,
              "minibatch_size": m08.MINIBATCH_SIZE, "epochs": m08.OPTIMIZATION_EPOCHS,
              "deterministic_cudnn": bool(getattr(args, "checkpoint_interval", 0) or getattr(args, "resume", None)),
              "training_templates": [path.stem for path in training],
              "development_templates": [path.stem for path in development],
              "trainer_sha256": hashlib.sha256(trainer.read_bytes()).hexdigest(),
              "openttd_sha256": hashlib.sha256(engine.read_bytes()).hexdigest()}
    record["spatial_validation_numpy"] = (__import__("numpy").__version__
        if record["spatial_validation"] == "vectorized" else None)
    write_json(output / "run.json", record)
    client = None
    try:
        record["source_archive"] = capture_source(output / "source")
        build_record = trainer.parent / "development-build.json"
        if build_record.is_file():
            record["trainer_build"] = json.loads(build_record.read_text())
        write_json(output / "run.json", record)
        client = start_trainer(
            trainer, architecture=args.architecture, device=args.device, run_seed=args.seed,
            deterministic_cudnn=record["deterministic_cudnn"],
            entropy_coefficient=entropy_coefficient,
            gae_lambda=gae_lambda,
            rollout_length=rollout_length, environment_count=m08.ENVIRONMENT_COUNT,
            minibatch_size=m08.MINIBATCH_SIZE, optimization_epochs=m08.OPTIMIZATION_EPOCHS,
            diagnostic_root=output / "diagnostics")
        # The existing collector retains old log probabilities/masks and handles
        # terminal/truncated bootstrapping; do not duplicate PPO or rollout math.
        collection_started = time.monotonic_ns()
        record["resume_from"] = str(args.resume.resolve()) if getattr(args, "resume", None) else None
        record["checkpoint_interval"] = getattr(args, "checkpoint_interval", 0)
        with checkpoint_collection(client, output / "checkpoints", compatibility(record, training),
                                   record["checkpoint_interval"], identity, record["resume_from"]) as checkpoint_client:
            collected_client = (CreditTrace(checkpoint_client, output / "credit-trace.jsonl", rollout_length,
                                           m08.ENVIRONMENT_COUNT) if record["credit_trace"] else checkpoint_client)
            reward_adapter = ({"universal-decision-cost": UniversalDecisionCost, "service-potential": ServicePotentialReward,
                               "economic": EconomicReward, "balanced-economic": BalancedEconomicReward}
                              [training_reward](collected_client) if training_reward != "native" else None)
            with (output / "training.log").open("w") as log, redirect_stdout(ProgressLog(sys.stdout, log)), \
                    training_episodes(output / "episode-metrics", horizon, reward_adapter), collector_rollout_length(rollout_length), \
                    spatial_validation(m08, record["spatial_validation"]):
                result = m08.train_architecture(reward_adapter or collected_client, engine, training, output, reward, args.updates, args.timeout)
            record["checkpoints"] = checkpoint_client.saved
        result["collection_and_optimization_elapsed_ns"] = time.monotonic_ns() - collection_started
        if reward_adapter is not None:
            for metrics, transformed in zip(result["updates"], reward_adapter.updates, strict=True):
                metrics.update(transformed)
        record["training"] = result
        package_id, package_path = client.export_evaluation_model(
            output / "models", repository_commit=identity["commit"],
            training_mean_reward=result["updates"][-1].get("mean_training_reward", result["updates"][-1]["mean_rollout_reward"]))
        record["model"] = {"id": package_id, "path": str(package_path),
                           "purpose": "inference weights; not an optimizer-resume checkpoint"}
        write_json(output / "run.json", record)
        record["development"] = [
            m08.evaluate_architecture(client, engine, template, output / f"development-{index}",
                                      reward, args.evaluation_steps, args.timeout)
            for index, template in enumerate(development)
        ]
        client.close()
        client = None
        record["status"] = "completed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if client is not None:
            try:
                client.abort()
            except Exception as exc:
                record["cleanup_error"] = str(exc)
        write_json(output / "run.json", record)
    print(f"Live OpenTTD run and model: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--instance-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--architecture", choices=("structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"),
                        default="structured-mlp-v1")
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--seed", type=positive, default=20260923)
    parser.add_argument("--updates", type=positive, default=2)
    parser.add_argument("--evaluation-steps", type=positive, default=64)
    parser.add_argument("--timeout", type=positive, default=60)
    parser.add_argument("--bridge-validation", choices=("reference", "fast"), default="reference")
    parser.add_argument("--episode-horizon", type=int, choices=(128, 256, 512), default=512,
                        help="Native training time limit; evaluation retains the ordinary 512-action reset")
    parser.add_argument("--training-reward", choices=("native", "universal-decision-cost", "service-potential", "economic", "balanced-economic"), default="native",
                        help="Explicit development reward experiment; raw native rewards always remain logged")
    parser.add_argument("--rollout-length", type=int, choices=(32, 64), default=32,
                        help="Decisions per worker before an update; adjust updates for matched transition budgets")
    parser.add_argument("--entropy-coefficient", type=float, default=0.01,
                        help="Explicit development PPO entropy bonus; nondefault values require a tunable native build")
    parser.add_argument("--gae-lambda", type=float, default=0.95,
                        help="Explicit development GAE trace weight in [0,1]; changes credit assignment, not rewards")
    parser.add_argument("--credit-trace", action="store_true",
                        help="Log scalar inputs to native GAE after any reward transformation, without changing updates")
    parser.add_argument("--spatial-validation", choices=("reference", "vectorized"), default="vectorized",
                        help="CPU spatial checks; vectorized is the measured default, reference reproduces earlier runs")
    parser.add_argument("--checkpoint-interval", type=int, default=0,
                        help="Save every N total updates at synchronized native resets; 0 disables saves")
    parser.add_argument("--resume", type=Path, help="Restore a development reset checkpoint; updates are additional updates")
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Live development training failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
