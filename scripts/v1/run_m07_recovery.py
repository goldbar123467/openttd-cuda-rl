#!/usr/bin/env python3
"""Exact native trainer service interruption/recovery and isolation campaign."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import pathlib
import sys
from typing import Any

import m07_trainer_client


class M07RecoveryError(RuntimeError):
    """The completed-update recovery boundary was not exact."""


RUN_SEED = 2_026_080_107
ROLLOUT_LENGTH = 8
ENVIRONMENT_COUNT = 4
MINIBATCH_SIZE = 8
OPTIMIZATION_EPOCHS = 2


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M07RecoveryError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def inputs(generation: int) -> tuple[list[list[float]], list[list[int]], list[int]]:
    observations: list[list[float]] = []
    masks: list[list[int]] = []
    contexts: list[int] = []
    for time_index in range(ROLLOUT_LENGTH):
        for environment_id in range(ENVIRONMENT_COUNT):
            context = (time_index * 3 + environment_id + generation) % 2
            observation = [0.0] * 256
            observation[0] = -1.0 if context == 0 else 1.0
            observation[1] = 1.0
            observation[2] = environment_id / ENVIRONMENT_COUNT
            observation[3] = generation / 8
            observations.append(observation)
            masks.append([1, 1] + [0] * 39)
            contexts.append(context)
    return observations, masks, contexts


def collect(client: m07_trainer_client.TrainerClient, generation: int) -> tuple[list[m07_trainer_client.Transition], list[int]]:
    observations, masks, contexts = inputs(generation)
    actions = client.act(observations, masks)
    transitions = [
        m07_trainer_client.Transition(
            observation=observation,
            legal_mask=mask,
            action=action.action,
            old_log_probability=action.log_probability,
            old_value=action.value,
            reward=1.0 if action.action == context else -1.0,
            next_value=0.0,
            bootstrap=False,
            continuation=False,
        )
        for observation, mask, context, action in zip(observations, masks, contexts, actions)
    ]
    return transitions, [action.action for action in actions]


def checkpoint(
    client: m07_trainer_client.TrainerClient,
    root: pathlib.Path,
    parent: str,
) -> tuple[str, pathlib.Path]:
    return client.checkpoint(
        root,
        run_name="m07-recovery-campaign",
        repository_commit="recovery-fixture",
        source_build_identity="m06-fixture",
        parent_checkpoint=parent,
        development_evaluation_json="{}",
    )


def equal_metrics(left: m07_trainer_client.UpdateResult, right: m07_trainer_client.UpdateResult) -> bool:
    for field in dataclasses.fields(left):
        left_value = getattr(left, field.name)
        right_value = getattr(right, field.name)
        if isinstance(left_value, float):
            if not math.isfinite(left_value) or left_value != right_value:
                return False
        elif left_value != right_value:
            return False
    return True


def run(executable: pathlib.Path, artifact_root: pathlib.Path) -> dict[str, Any]:
    executable = executable.resolve()
    artifact_root = artifact_root.resolve()
    require(executable.is_file(), "trainer executable is missing")
    require(not artifact_root.exists(), "artifact root already exists")
    artifact_root.mkdir(parents=True)
    uninterrupted = m07_trainer_client.TrainerClient.start(
        executable,
        run_seed=RUN_SEED,
        rollout_length=ROLLOUT_LENGTH,
        environment_count=ENVIRONMENT_COUNT,
        minibatch_size=MINIBATCH_SIZE,
        optimization_epochs=OPTIMIZATION_EPOCHS,
        diagnostic_root=artifact_root / "diagnostics-uninterrupted",
    )
    resumed: m07_trainer_client.TrainerClient | None = None
    try:
        first_rollout, first_actions = collect(uninterrupted, 1)
        first_update = uninterrupted.update(first_rollout)
        first_id, first_path = checkpoint(uninterrupted, artifact_root / "boundary", "")
        resumed = m07_trainer_client.TrainerClient.start(
            executable,
            resume=first_path,
            diagnostic_root=artifact_root / "diagnostics-resumed",
        )

        uninterrupted_rollout, uninterrupted_actions = collect(uninterrupted, 2)
        resumed_rollout, resumed_actions = collect(resumed, 2)
        require(uninterrupted_actions == resumed_actions, "action RNG repeated, skipped, or changed after recovery")
        for left, right in zip(uninterrupted_rollout, resumed_rollout):
            require(left == right, "rollout values changed after recovery")
        uninterrupted_update = uninterrupted.update(uninterrupted_rollout)
        resumed_update = resumed.update(resumed_rollout)
        require(equal_metrics(uninterrupted_update, resumed_update), "interrupted and uninterrupted update metrics differ")
        uninterrupted_id, _ = checkpoint(uninterrupted, artifact_root / "uninterrupted", first_id)
        resumed_id, _ = checkpoint(resumed, artifact_root / "resumed", first_id)
        require(uninterrupted_id == resumed_id, "interrupted and uninterrupted checkpoint states differ")

        observations, masks, _contexts = inputs(3)
        first_greedy = uninterrupted.act(observations, masks, deterministic=True)
        second_greedy = uninterrupted.act(observations, masks, deterministic=True)
        require(first_greedy == second_greedy, "deterministic evaluation changed outputs")
        after_evaluation_id, _ = checkpoint(uninterrupted, artifact_root / "after-evaluation", first_id)
        require(after_evaluation_id == uninterrupted_id, "evaluation mutated checkpointed trainer state")

        all_mask_rejected = False
        try:
            uninterrupted.act([[0.0] * 256], [[0] * 41])
        except m07_trainer_client.M07TrainerClientError as exc:
            all_mask_rejected = "all-illegal" in str(exc)
        require(all_mask_rejected, "service accepted an all-illegal action mask")
        require(len(uninterrupted.act([[0.0] * 256], [[1] + [0] * 40], deterministic=True)) == 1,
            "service did not recover after a rejected request")
        uninterrupted.close()
        resumed.close()

        numerical_root = artifact_root / "numerical-failure"
        numerical = m07_trainer_client.TrainerClient.start(
            executable,
            run_seed=RUN_SEED,
            rollout_length=ROLLOUT_LENGTH,
            environment_count=ENVIRONMENT_COUNT,
            minibatch_size=MINIBATCH_SIZE,
            optimization_epochs=OPTIMIZATION_EPOCHS,
            diagnostic_root=numerical_root,
        )
        numerical_rejected = False
        try:
            observation = [0.0] * 256
            observation[0] = math.nan
            numerical.act([observation], [[1] + [0] * 40], deterministic=True)
        except m07_trainer_client.M07TrainerClientError as exc:
            numerical_rejected = "nonfinite" in str(exc)
        finally:
            numerical.abort()
        require(numerical_rejected, "service accepted a nonfinite observation")
        diagnostics = sorted(numerical_root.glob("diagnostic-*/diagnostic.json"))
        require(len(diagnostics) == 1, "numerical failure did not publish exactly one diagnostic")
        require(
            not any(path.name in {"model.pt", "optimizer.pt", "checkpoint.header"} for path in numerical_root.rglob("*")),
            "numerical failure published a normal checkpoint payload",
        )
    except Exception:
        uninterrupted.abort()
        if resumed is not None:
            resumed.abort()
        raise
    result = {
        "schema_version": "openttd-rl-v1-m07-recovery-report-1",
        "status": "PASS",
        "configuration": {
            "environment_count": ENVIRONMENT_COUNT,
            "minibatch_size": MINIBATCH_SIZE,
            "optimization_epochs": OPTIMIZATION_EPOCHS,
            "rollout_length": ROLLOUT_LENGTH,
            "run_seed": RUN_SEED,
        },
        "first_actions": first_actions,
        "first_checkpoint_id": first_id,
        "first_update": dataclasses.asdict(first_update),
        "recovered_actions": resumed_actions,
        "recovered_checkpoint_id": resumed_id,
        "recovered_update": dataclasses.asdict(resumed_update),
        "uninterrupted_checkpoint_id": uninterrupted_id,
        "uninterrupted_update": dataclasses.asdict(uninterrupted_update),
        "numerical_failure": {
            "diagnostic": str(diagnostics[0].relative_to(artifact_root)),
            "normal_checkpoint_published": False,
            "service_terminated": True,
        },
    }
    result["report_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    (artifact_root / "recovery-report.json").write_bytes(canonical_bytes(result) + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trainer", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.trainer, args.artifact_root)
    except Exception as exc:
        print(f"M07_RECOVERY=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        f"M07_RECOVERY=PASS boundary={result['first_checkpoint_id']} "
        f"recovered={result['recovered_checkpoint_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
