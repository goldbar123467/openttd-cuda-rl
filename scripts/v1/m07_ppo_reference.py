#!/usr/bin/env python3
"""Independent scalar PPO oracle and native differential runner for M07."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys
from typing import Any


class M07PpoReferenceError(ValueError):
    """Native PPO output disagrees with the independent scalar oracle."""


def softmax_masked(logits: list[float], mask: list[bool]) -> tuple[list[float], list[float], float]:
    if len(logits) != len(mask) or not any(mask):
        raise M07PpoReferenceError("invalid masked categorical input")
    maximum = max(value for value, legal in zip(logits, mask) if legal)
    exponentials = [math.exp(value - maximum) if legal else 0.0 for value, legal in zip(logits, mask)]
    denominator = math.fsum(exponentials)
    probabilities = [value / denominator for value in exponentials]
    log_probabilities = [math.log(value) if legal else float("-inf") for value, legal in zip(probabilities, mask)]
    entropy = -math.fsum(
        probability * log_probability
        for probability, log_probability, legal in zip(probabilities, log_probabilities, mask)
        if legal
    )
    return probabilities, log_probabilities, entropy


def reference_vectors() -> dict[str, Any]:
    rewards = [[1.0, 0.5], [2.0, -1.0], [3.0, 4.0]]
    values = [[0.2, 0.1], [0.4, -0.2], [0.3, 0.5]]
    next_values = [[0.4, -0.2], [0.3, 0.5], [0.7, 0.8]]
    bootstrap = [[1.0, 1.0], [1.0, 0.0], [0.0, 1.0]]
    continuation = [[1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]
    gamma = 0.9
    gae_lambda = 0.8
    accumulators = [0.0, 0.0]
    advantages = [[0.0, 0.0] for _ in rewards]
    for time in reversed(range(len(rewards))):
        for environment in range(2):
            delta = (
                rewards[time][environment]
                + gamma * bootstrap[time][environment] * next_values[time][environment]
                - values[time][environment]
            )
            accumulators[environment] = (
                delta
                + gamma * gae_lambda * continuation[time][environment] * accumulators[environment]
            )
            advantages[time][environment] = accumulators[environment]
    flat_advantages = [value for row in advantages for value in row]
    flat_returns = [advantage + value for advantage_row, value_row in zip(advantages, values) for advantage, value in zip(advantage_row, value_row)]
    mean = math.fsum(flat_advantages) / len(flat_advantages)
    variance = math.fsum((value - mean) ** 2 for value in flat_advantages) / len(flat_advantages)
    normalized = [(value - mean) / math.sqrt(variance + 1e-8) for value in flat_advantages]

    logits = [[0.2, -0.3, 1.1], [2.0, -1.0, 0.5]]
    masks = [[True, False, True], [True, True, False]]
    actions = [2, 1]
    old_log_probabilities = [-0.4, -2.0]
    ppo_advantages = [1.5, -0.75]
    predicted_values = [0.25, -0.5]
    value_targets = [1.0, -0.25]
    probabilities: list[float] = []
    selected_log_probabilities: list[float] = []
    entropies: list[float] = []
    row_probabilities: list[list[float]] = []
    row_log_probabilities: list[list[float]] = []
    for row_logits, row_mask, action in zip(logits, masks, actions):
        row_probability, row_log_probability, entropy = softmax_masked(row_logits, row_mask)
        row_probabilities.append(row_probability)
        row_log_probabilities.append(row_log_probability)
        probabilities.extend(row_probability)
        selected_log_probabilities.append(row_log_probability[action])
        entropies.append(entropy)

    ratios = [math.exp(new - old) for new, old in zip(selected_log_probabilities, old_log_probabilities)]
    surrogates = []
    selected_gradients = []
    for ratio, advantage in zip(ratios, ppo_advantages):
        clipped = min(max(ratio, 0.8), 1.2)
        first = ratio * advantage
        second = clipped * advantage
        surrogates.append(min(first, second))
        selected_gradients.append(-ratio * advantage / 2.0 if first <= second else 0.0)
    policy_loss = -math.fsum(surrogates) / 2.0
    value_loss = math.fsum((value - target) ** 2 for value, target in zip(predicted_values, value_targets)) / 2.0
    entropy = math.fsum(entropies) / 2.0
    total_loss = policy_loss + 0.5 * value_loss - 0.01 * entropy
    approximate_kl = math.fsum((ratio - 1.0) - math.log(ratio) for ratio in ratios) / 2.0
    clip_fraction = sum(abs(ratio - 1.0) > 0.2 for ratio in ratios) / 2.0

    logit_gradients: list[float] = []
    for row, (row_probability, row_log_probability, row_mask, action, entropy_value, selected_gradient) in enumerate(
        zip(row_probabilities, row_log_probabilities, masks, actions, entropies, selected_gradients)
    ):
        del row
        for index, (probability, log_probability, legal) in enumerate(zip(row_probability, row_log_probability, row_mask)):
            if not legal:
                logit_gradients.append(0.0)
                continue
            policy_gradient = selected_gradient * ((1.0 if index == action else 0.0) - probability)
            entropy_gradient = 0.01 / 2.0 * probability * (log_probability + entropy_value)
            logit_gradients.append(policy_gradient + entropy_gradient)
    value_gradients = [0.5 * 2.0 * (value - target) / 2.0 for value, target in zip(predicted_values, value_targets)]
    adam_gradient = 0.25 - 1.5
    adam_parameter = 0.25 - 0.0003 * adam_gradient / (abs(adam_gradient) + 0.00001)
    return {
        "adam_parameter": adam_parameter,
        "advantages": flat_advantages,
        "approximate_kl": approximate_kl,
        "clip_fraction": clip_fraction,
        "entropy": entropy,
        "logit_gradients": logit_gradients,
        "selected_log_probabilities": selected_log_probabilities,
        "normalized_advantages": normalized,
        "policy_loss": policy_loss,
        "probabilities": probabilities,
        "returns": flat_returns,
        "total_loss": total_loss,
        "value_gradients": value_gradients,
        "value_loss": value_loss,
    }


def compare(actual: Any, expected: Any, path: str = "$", tolerance: float = 1e-12) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise M07PpoReferenceError(f"{path}: object keys differ")
        for key in sorted(expected):
            compare(actual[key], expected[key], f"{path}.{key}", tolerance)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise M07PpoReferenceError(f"{path}: array shape differs")
        for index, (actual_value, expected_value) in enumerate(zip(actual, expected)):
            compare(actual_value, expected_value, f"{path}[{index}]", tolerance)
        return
    if isinstance(expected, float):
        if not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(actual - expected) > tolerance:
            raise M07PpoReferenceError(f"{path}: actual={actual!r} expected={expected!r}")
        return
    if actual != expected:
        raise M07PpoReferenceError(f"{path}: actual={actual!r} expected={expected!r}")


def run_native(executable: pathlib.Path) -> dict[str, Any]:
    if not executable.is_absolute() or not executable.is_file():
        raise M07PpoReferenceError("trainer executable must be an existing absolute file")
    result = subprocess.run(
        [str(executable), "--reference-vectors"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0 or result.stderr:
        raise M07PpoReferenceError(
            f"native reference command failed rc={result.returncode} stderr={result.stderr!r}"
        )
    try:
        value = json.loads(result.stdout, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (json.JSONDecodeError, ValueError) as exc:
        raise M07PpoReferenceError(f"native reference output is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise M07PpoReferenceError("native reference output must be one JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trainer", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        actual = run_native(args.trainer)
        expected = reference_vectors()
        compare(actual, expected)
    except (M07PpoReferenceError, OSError, subprocess.SubprocessError) as exc:
        print(f"M07_PPO_DIFFERENTIAL=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"M07_PPO_DIFFERENTIAL=PASS vectors={len(expected)} tolerance=1e-12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
