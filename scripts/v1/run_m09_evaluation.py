#!/usr/bin/env python3
"""Run the frozen M09 final suite with the optimizer-free evaluator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import random
import statistics
import subprocess
import sys
from typing import Any

import m03_bridge_protocol as protocol
import m09_evaluator_client
import run_m06_reward_trajectory
import run_m07_cpu_ppo as m07
import run_m08_live_architectures as m08
import validate_m06_reward_contract
import validate_m07_ppo_contract
import validate_m09_evaluation_contract


class M09EvaluationError(RuntimeError):
    """Final evaluation failed closed or violated its preregistration."""


M09_COMPATIBILITY_SHA256 = "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e"
M09_OPENTTD_SHA256 = "8e61a1325090240cf084ad0a9d82376bf11082564bb0eb17ac4a1c8033158a0c"
ARCHITECTURES = ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]
T_CRITICAL_95_DF2 = 4.302652729911275
NUMERIC_METRICS = [
    "survival", "bankruptcy", "final_balance", "net_profit", "operating_profit",
    "passenger_deliveries", "route_profit", "profitable_vehicles", "infrastructure_cost",
    "roi", "coverage", "invalid_actions", "action_efficiency",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M09EvaluationError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_snapshot(path: pathlib.Path) -> dict[str, str]:
    require(path.is_dir() and not path.is_symlink(), f"model package is not a regular directory: {path}")
    files = sorted(item for item in path.rglob("*") if item.is_file())
    require([item.relative_to(path).as_posix() for item in files] == ["manifest.json", "model.pt"], "model package inventory drifted")
    return {item.relative_to(path).as_posix(): sha256_file(item) for item in files}


def load_training_manifest(path: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    manifest = validate_m07_ppo_contract.load_strict_json(path)
    require(manifest.get("schema_version") == "openttd-rl-v1-m09-training-campaign-1", "training manifest schema drifted")
    identity = dict(manifest)
    observed = identity.pop("manifest_sha256", None)
    require(observed == hashlib.sha256(canonical_bytes(identity)).hexdigest(), "training manifest semantic identity drifted")
    require(manifest.get("status") == "PASS" and manifest.get("final_evaluation_accessed") is False, "training did not remain final-blind")
    budget = contract["training_budget"]
    require(manifest.get("budget") == budget, "training budget differs from preregistration")
    runs = manifest.get("runs", [])
    expected = {(architecture, seed) for architecture in budget["architectures"] for seed in budget["run_seeds"]}
    require({(item.get("architecture"), item.get("run_seed")) for item in runs} == expected, "matched architecture/seed matrix is incomplete")
    require(all(item.get("accepted_samples") == budget["accepted_samples_per_run"] for item in runs), "accepted-sample budget is unfair")
    return manifest


def development_selection(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    selected_runs: list[dict[str, Any]] = []
    for architecture in ARCHITECTURES:
        candidates = [item for item in manifest["runs"] if item["architecture"] == architecture]
        eligible = [item for item in candidates if item["development"]["reliably_profitable"]]
        best = max(eligible or candidates, key=lambda item: (
            item["development"]["mean_operating_profit"],
            item["development"]["mean_passenger_deliveries"],
            item["development"]["mean_final_balance"],
            -item["development"]["mean_invalid_actions"],
            -item["run_seed"],
        ))
        selected[architecture] = {"package": best["package"], "run_seed": best["run_seed"]}
        selected_runs.append(best)
    require(selected == manifest["selected_on_development"], "recorded development selection is not reproducible")
    eligible = [item for item in selected_runs if item["development"]["reliably_profitable"]]
    best_overall = max(eligible or selected_runs, key=lambda item: (
        item["development"]["mean_operating_profit"],
        item["development"]["mean_passenger_deliveries"],
        item["development"]["mean_final_balance"],
        -item["development"]["mean_invalid_actions"],
        -item["run_seed"],
    ))
    return selected, best_overall


def start_environment(
    executable: pathlib.Path,
    template: pathlib.Path,
    run_root: pathlib.Path,
    reward_contract: dict[str, Any],
    session: int,
    starting_balance: int,
    action_horizon: int,
    timeout: float,
) -> m07.Environment:
    worker = protocol.WorkerProcess.start(executable=executable, instance=template, run_root=run_root, timeout=timeout)
    controller = run_m06_reward_trajectory.Controller(
        worker, session, reward_contract, template, f"m09-final-{session}"
    )
    try:
        controller.reset_evaluation(
            evaluation_contract_sha256=M09_COMPATIBILITY_SHA256,
            starting_balance=starting_balance,
            action_horizon=action_horizon,
        )
        return m07.Environment(0, 0, template, controller, controller.observe(), controller.mask())
    except Exception:
        controller.abort()
        raise


def scripted_action(environment: m07.Environment) -> int:
    mask = environment.controller.mask(include_source=True)
    environment.mask = mask
    source = mask["source_projection"]
    legal = mask["legal"]
    if legal[1]:
        return 1
    if legal[3]:
        return 3
    for stop in source["stops"]:
        index = 4 + stop["town_slot"] * 4 + stop["expected_direction"]
        if legal[index]:
            return index
    depot_index = 12 + source["depot"]["expected_direction"]
    if legal[depot_index]:
        return depot_index
    if legal[16]:
        return 16
    if legal[17]:
        return 17
    if legal[25]:
        return 25
    return 0


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
        "survival": result["termination"]["reason"] != "BANKRUPTCY",
        "bankruptcy": result["termination"]["reason"] == "BANKRUPTCY",
        "final_balance": company["balance"],
        "net_profit": company["balance"] - starting_balance,
        "operating_profit": operating_profit,
        "passenger_deliveries": company["delivered_passengers"],
        "route_profit": operating_profit,
        "profitable_vehicles": int(vehicles == 1 and operating_profit > 0),
        "infrastructure_cost": capital_spend,
        "roi": operating_profit / capital_spend if capital_spend else None,
        "station_rating": None,
        "coverage": sum(value > 0 for value in catchment) / len(catchment),
        "invalid_actions": invalid_actions,
        "action_efficiency": non_wait_actions / environment.episode_length,
        "actions": environment.episode_length,
        "return": environment.episode_return,
        "termination_reason": result["termination"]["reason"],
    }


def run_episode(
    *,
    executable: pathlib.Path,
    evaluator: pathlib.Path,
    template: pathlib.Path,
    run_root: pathlib.Path,
    reward_contract: dict[str, Any],
    policy: dict[str, Any],
    policy_mode: str,
    sampling_seed: int,
    starting_balance: int,
    action_horizon: int,
    session: int,
    timeout: float,
) -> dict[str, Any]:
    environment = start_environment(
        executable, template, run_root, reward_contract, session, starting_balance, action_horizon, timeout
    )
    client: m09_evaluator_client.EvaluatorClient | None = None
    package_before: dict[str, str] | None = None
    state_sha256: str | None = None
    rng = random.Random(sampling_seed)
    if policy["kind"] == "learned":
        package = pathlib.Path(policy["package_path"])
        package_before = package_snapshot(package)
        client = m09_evaluator_client.EvaluatorClient.start(
            evaluator, package=package, sampling_seed=sampling_seed
        )
    capital_spend = 0
    invalid_actions = 0
    non_wait_actions = 0
    try:
        for _step in range(action_horizon):
            legal = m07.legal_mask(environment.mask)
            if policy["kind"] == "learned":
                require(client is not None, "learned policy evaluator was not started")
                action = client.act(
                    [m07.structured(environment.observation)],
                    [m08.spatial(environment.observation)],
                    [legal],
                    deterministic=policy_mode == "greedy",
                )[0].action
            elif policy["kind"] == "random":
                action = rng.choice([index for index, value in enumerate(legal) if value])
            elif policy["kind"] == "trivial":
                action = 0
            elif policy["kind"] == "existing-scripted":
                action = scripted_action(environment)
                legal = m07.legal_mask(environment.mask)
            else:  # pragma: no cover - guarded by construction
                raise M09EvaluationError(f"unknown policy kind {policy['kind']}")
            require(legal[action] == 1, f"{policy['id']} selected an illegal action")
            result = environment.controller.step(action)
            raw = result["reward"]["raw"]
            capital_spend += raw["capital_spend"]
            invalid_actions += raw["native_rejected"]
            non_wait_actions += action != 0 and not raw["native_rejected"]
            environment.episode_return += float(result["reward"]["scalar"])
            environment.episode_length += 1
            environment.observation = environment.controller.observe()
            if result["termination"]["reason"] != "NONE":
                break
            environment.mask = environment.controller.mask()
        require(environment.episode_length <= action_horizon, "episode exceeded preregistered horizon")
        metrics = episode_metrics(
            environment,
            result,
            capital_spend=capital_spend,
            invalid_actions=invalid_actions,
            non_wait_actions=non_wait_actions,
            starting_balance=starting_balance,
        )
        environment.controller.close(timeout)
        if client is not None:
            package_id, state_sha256 = client.close(timeout)
            require(package_id == policy["package_id"], "native evaluator returned the wrong package identity")
            require(package_snapshot(pathlib.Path(policy["package_path"])) == package_before, "evaluation mutated package files")
        return metrics | {"model_state_sha256": state_sha256}
    except Exception:
        environment.controller.abort()
        if client is not None:
            client.abort()
        raise


def mean(values: list[float]) -> float:
    require(bool(values), "cannot average an empty metric")
    return math.fsum(values) / len(values)


def seed_statistics(episodes: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    seed_means: list[dict[str, Any]] = []
    for seed in sorted({item["run_seed"] for item in episodes}):
        raw = [item["metrics"][metric] for item in episodes if item["run_seed"] == seed]
        values = [float(value) for value in raw if value is not None]
        seed_means.append({"run_seed": seed, "value": mean(values) if values else None})
    values = [item["value"] for item in seed_means if item["value"] is not None]
    if len(values) != 3:
        return {"seed_means": seed_means, "status": "NOT_APPLICABLE", "reason": "metric unavailable for one or more training seeds"}
    sample_sd = statistics.stdev(values)
    center = mean(values)
    margin = T_CRITICAL_95_DF2 * sample_sd / math.sqrt(3)
    return {
        "seed_means": seed_means,
        "status": "REPORTED",
        "mean": center,
        "sample_standard_deviation": sample_sd,
        "minimum": min(values),
        "maximum": max(values),
        "confidence_interval_95": [center - margin, center + margin],
    }


def summarize(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        metric: mean([float(item["metrics"][metric]) for item in episodes if item["metrics"][metric] is not None])
        if any(item["metrics"][metric] is not None for item in episodes) else None
        for metric in NUMERIC_METRICS
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    executable = args.openttd.resolve()
    evaluator = args.evaluator.resolve()
    instance_dir = args.instance_dir.resolve()
    artifact_root = args.artifact_root.resolve()
    training_root = args.training_root.resolve()
    require(not artifact_root.exists(), "evaluation artifact root already exists")
    require(executable.is_file() and sha256_file(executable) == M09_OPENTTD_SHA256, "M09 OpenTTD executable identity drifted")
    require(evaluator.is_file(), "optimizer-free evaluator executable is missing")
    contract = validate_m09_evaluation_contract.validate(
        root / "config/v1/m09-evaluation-contract.json",
        root / "docs/project/schema/v1-m09-evaluation-contract.schema.json",
    )
    require(contract["identity"]["compatibility_sha256"] == M09_COMPATIBILITY_SHA256, "evaluation contract drifted")
    reward_contract = validate_m06_reward_contract.validate(
        root / "config/v1/m06-reward-trajectory-contract.json",
        root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json",
    )
    training = load_training_manifest(training_root / "training-manifest.json", contract)
    selected_by_architecture, selected_overall = development_selection(training)
    require(selected_overall["development"]["reliably_profitable"], "no development-eligible policy may enter final evaluation")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True).stdout
    require(status == "", "accepted final evaluation requires a clean committed repository")
    repository_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    run_by_package = {item["package"]["id"]: item for item in training["runs"]}
    package_snapshots: dict[str, dict[str, str]] = {}
    for package_id, item in run_by_package.items():
        package_path = training_root / item["package"]["path"]
        manifest = validate_m07_ppo_contract.load_strict_json(package_path / "manifest.json")
        require(package_path.name == package_id and manifest["model_sha256"] == sha256_file(package_path / "model.pt"), "evaluation package content address drifted")
        require(manifest["architecture"] == item["architecture"] and manifest["run_seed"] == item["run_seed"], "package provenance differs from training run")
        package_snapshots[package_id] = package_snapshot(package_path)
    final_templates = [instance_dir / f"{name}.json" for name in contract["partitions"]["final_evaluation"]]
    require(all(path.is_file() for path in final_templates), "frozen final templates are missing")
    artifact_root.mkdir(parents=True)
    episodes: list[dict[str, Any]] = []
    session = 90_000_000

    def evaluate_one(
        suite: str,
        policy: dict[str, Any],
        template: pathlib.Path,
        policy_mode: str,
        sampling_seed: int,
        starting_balance: int,
        action_horizon: int,
    ) -> None:
        nonlocal session
        session += 1
        episode_id = f"{suite}-{policy['id']}-{template.stem}-b{starting_balance}-h{action_horizon}-s{sampling_seed}"
        metrics = run_episode(
            executable=executable,
            evaluator=evaluator,
            template=template,
            run_root=artifact_root / "workers" / episode_id,
            reward_contract=reward_contract,
            policy=policy,
            policy_mode=policy_mode,
            sampling_seed=sampling_seed,
            starting_balance=starting_balance,
            action_horizon=action_horizon,
            session=session,
            timeout=args.timeout,
        )
        item = {
            "episode_id": episode_id,
            "suite": suite,
            "policy_id": policy["id"],
            "policy_kind": policy["kind"],
            "architecture": policy.get("architecture"),
            "run_seed": policy.get("run_seed"),
            "package_id": policy.get("package_id"),
            "template_id": template.stem,
            "template_sha256": sha256_file(template),
            "policy_mode": policy_mode,
            "sampling_seed": sampling_seed,
            "starting_balance": starting_balance,
            "action_horizon": action_horizon,
            "metrics": metrics,
        }
        episodes.append(item)
        print(
            f"M09_EPISODE suite={suite} policy={policy['id']} template={template.stem} "
            f"profit={metrics['operating_profit']} passengers={metrics['passenger_deliveries']}",
            flush=True,
        )

    learned: list[dict[str, Any]] = []
    for item in training["runs"]:
        learned.append({
            "id": f"{item['architecture']}-seed-{item['run_seed']}",
            "kind": "learned",
            "architecture": item["architecture"],
            "run_seed": item["run_seed"],
            "package_id": item["package"]["id"],
            "package_path": str((training_root / item["package"]["path"]).resolve()),
        })
    primary = contract["evaluation_suite"]["primary"]
    for policy in learned:
        for template in final_templates:
            evaluate_one("primary", policy, template, "greedy", 0, primary["starting_balance"], primary["action_horizon"])

    baselines = [
        {"id": "seeded-random-legal-v1", "kind": "random"},
        {"id": "wait-only-trivial-v1", "kind": "trivial"},
        {"id": "m05-scripted-bus-v1", "kind": "existing-scripted"},
    ]
    for policy_index, policy in enumerate(baselines):
        for template_index, template in enumerate(final_templates):
            seed = 2_026_090_920 + policy_index * 10 + template_index
            evaluate_one("baseline", policy, template, "greedy" if policy["kind"] != "random" else "seeded-random", seed, primary["starting_balance"], primary["action_horizon"])

    selected_policy = next(item for item in learned if item["package_id"] == selected_overall["package"]["id"])
    stochastic = contract["evaluation_suite"]["stochastic"]
    for sampling_seed in stochastic["sampling_seeds"]:
        for template in final_templates:
            evaluate_one("stochastic", selected_policy, template, "stochastic", sampling_seed, stochastic["starting_balance"], stochastic["action_horizon"])
    robustness = contract["evaluation_suite"]["robustness"]
    for starting_balance in robustness["starting_balances"]:
        for action_horizon in robustness["action_horizons"]:
            for template in final_templates:
                evaluate_one("robustness", selected_policy, template, "greedy", 0, starting_balance, action_horizon)

    require(all(package_snapshot(training_root / item["package"]["path"]) == package_snapshots[item["package"]["id"]] for item in training["runs"]), "final evaluation mutated a package")
    state_by_package: dict[str, set[str]] = {}
    for item in episodes:
        if item["package_id"] is not None:
            state_by_package.setdefault(item["package_id"], set()).add(item["metrics"]["model_state_sha256"])
    require(all(len(values) == 1 for values in state_by_package.values()), "in-memory model state changed across episodes")
    primary_learned = [item for item in episodes if item["suite"] == "primary"]
    architecture_statistics = {
        architecture: {
            metric: seed_statistics([item for item in primary_learned if item["architecture"] == architecture], metric)
            for metric in NUMERIC_METRICS
        }
        for architecture in ARCHITECTURES
    }
    baseline_summaries = {
        policy["id"]: summarize([item for item in episodes if item["suite"] == "baseline" and item["policy_id"] == policy["id"]])
        for policy in baselines
    }
    selected_primary = [item for item in primary_learned if item["package_id"] == selected_policy["package_id"]]
    selected_summary = summarize(selected_primary)
    superiority = all(
        selected_summary[metric] > baseline_summaries[baseline][metric]
        for metric in ("operating_profit", "passenger_deliveries")
        for baseline in ("seeded-random-legal-v1", "wait-only-trivial-v1")
    )
    reliable = all(
        item["metrics"]["survival"]
        and item["metrics"]["operating_profit"] > 0
        and item["metrics"]["passenger_deliveries"] > 0
        and item["metrics"]["final_balance"] > 0
        for item in selected_primary
    )
    raw_path = artifact_root / "raw-episodes.jsonl"
    with raw_path.open("xb") as stream:
        for item in episodes:
            stream.write(canonical_bytes(item) + b"\n")
    result = {
        "schema_version": "openttd-rl-v1-m09-final-evaluation-1",
        "status": "PASS" if superiority and reliable else "FAIL",
        "contract_sha256": M09_COMPATIBILITY_SHA256,
        "repository_commit": repository_commit,
        "training_manifest_sha256": training["manifest_sha256"],
        "runtime": {
            "openttd_executable_sha256": sha256_file(executable),
            "evaluator_executable_sha256": sha256_file(evaluator),
            "optimizer_dependency": False,
            "model_state": "read-only-verified",
        },
        "selection": {
            "split": "development",
            "final_results_used": False,
            "selected_by_architecture": selected_by_architecture,
            "selected_overall": {"architecture": selected_overall["architecture"], "run_seed": selected_overall["run_seed"], "package": selected_overall["package"]},
        },
        "episode_count": len(episodes),
        "raw_episodes": {"path": raw_path.name, "sha256": sha256_file(raw_path)},
        "metric_registry": contract["metrics"],
        "baseline_registry": contract["baselines"],
        "training_reward_by_run": [
            {
                "architecture": item["architecture"],
                "run_seed": item["run_seed"],
                "mean_rollout_reward": item["training_mean_reward"],
                "quality_metric": False,
            }
            for item in training["runs"]
        ],
        "baseline_summaries": baseline_summaries,
        "selected_primary_summary": selected_summary,
        "architecture_statistics": architecture_statistics,
        "stochastic_summary": summarize([item for item in episodes if item["suite"] == "stochastic"]),
        "robustness": {
            "summary": summarize([item for item in episodes if item["suite"] == "robustness"]),
            "failure_cases": [item["episode_id"] for item in episodes if item["suite"] == "robustness" and (not item["metrics"]["survival"] or item["metrics"]["operating_profit"] <= 0 or item["metrics"]["passenger_deliveries"] <= 0)],
        },
        "claims": {
            "baseline_superiority": superiority,
            "reliable_profitability": reliable,
            "architecture_superiority": False,
            "architecture_disposition": "No architecture-superiority claim: all three matched training-seed distributions and intervals are reported; final selection was development-only.",
            "training_reward_used_as_quality_metric": False,
        },
        "package_read_only": {
            "file_snapshots_sha256": {package_id: hashlib.sha256(canonical_bytes(value)).hexdigest() for package_id, value in package_snapshots.items()},
            "state_sha256": {package_id: next(iter(values)) for package_id, values in state_by_package.items()},
        },
    }
    result["report_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    report_path = artifact_root / "final-evaluation-report.json"
    report_path.write_bytes(canonical_bytes(result) + b"\n")
    require(result["status"] == "PASS", "G09 superiority/reliable-profitability threshold was not met")
    print(
        f"M09_EVALUATION=PASS episodes={len(episodes)} policy={selected_policy['id']} "
        f"profit={selected_summary['operating_profit']:.3f} passengers={selected_summary['passenger_deliveries']:.3f}",
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--evaluator", type=pathlib.Path, required=True)
    parser.add_argument("--instance-dir", type=pathlib.Path, required=True)
    parser.add_argument("--training-root", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print(f"M09_EVALUATION=FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
