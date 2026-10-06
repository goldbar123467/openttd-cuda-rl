#!/usr/bin/env python3
"""Complete-episode development baselines and saved-policy diagnostics.

Uses the ordinary 512-action reset, never the held-out M09 evaluation entrypoint.
The engine's independently checked lifetime reward counters own economic metrics.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import cProfile
import dataclasses
import json
from pathlib import Path
import platform
import multiprocessing
import random
import sys
import time

from local import ROOT, positive, source_identity, write_json
import bridge_validation
from stage_timing import StageTimings

sys.path.insert(0, str(ROOT / "scripts/v1"))
import m09_evaluator_client
import m10_deployment_client
import run_m07_cpu_ppo as m07
import run_m08_live_architectures as m08
import run_m09_evaluation as m09
import validate_m06_reward_contract


FLEET_SIZES = {"one-bus": 1, "two-bus": 2, "four-bus": 4, "eight-bus": 8}
POLICIES = ("wait", "random", "scripted", *FLEET_SIZES, "greedy", "sampled")


def package_snapshot(path, backend):
    if backend == "native":
        return m09.package_snapshot(path)
    if backend != "onnx" or not path.is_dir() or path.is_symlink():
        raise ValueError("Invalid inference backend or ONNX package path")
    files = sorted(path.iterdir())
    if [p.name for p in files] != ["INSTALL.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx"] or any(
            p.is_symlink() or not p.is_file() for p in files):
        raise ValueError("ONNX package inventory differs")
    return {p.name: m09.sha256_file(p) for p in files}


def service_action(observation: dict, legal: list[int], target_buses: int) -> int:
    """Build a fixed fleet using only the same public observation and mask."""
    for action in (1, 3, *range(4, 16)):
        if legal[action]:
            return action
    if round(observation["structured"]["data"][6] * 8) < target_buses and legal[16]:
        return 16
    for action in range(17, 33):
        if legal[action]:
            return action
    return 0


def one_bus_action(observation: dict, legal: list[int]) -> int:
    return service_action(observation, legal, 1)


def economic_window(rows: list[dict]) -> dict:
    return {"first_action": rows[0]["step"], "last_action": rows[-1]["step"],
            "passengers": sum(row["raw"]["delivered_passengers_delta"] for row in rows),
            "operating_profit": sum(row["raw"]["operating_profit_delta"] for row in rows),
            "capital_spend": sum(row["raw"]["capital_spend"] for row in rows)}


def episode(*, engine: Path, template: Path, output: Path, reward: dict,
            policy: str, seed: int, evaluator: Path | None, package: Path | None,
            timeout: float = 60, backend: str = "native", evaluation_split: str | None = None,
            retain_spatial_inputs: bool = False, stage_timing: bool = False) -> dict:
    if template.stem in ("m02-template-07", "m02-template-08") and evaluation_split != "final-evaluation":
        raise ValueError("Final cases require the dedicated registered evaluation runner")
    scenario = json.loads(template.read_text())
    actual_split = scenario["split"]
    if actual_split == "final-evaluation":
        if evaluation_split != "final-evaluation":
            raise ValueError("Final cases require the dedicated registered evaluation runner")
    elif actual_split not in ("training", "development") or (evaluation_split is not None and actual_split != evaluation_split):
        raise ValueError("Scenario does not belong to the requested evaluation split")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    status = {"status": "running", "policy": policy, "sampling_seed": seed,
              "script_target_buses": FLEET_SIZES.get(policy),
              "template_id": template.stem, "scenario": scenario,
              "inference_device": "cpu" if policy in ("greedy", "sampled") else None,
              "inference_backend": backend if policy in ("greedy", "sampled") else None}
    write_json(output / "episode.json", status)
    environment = None
    client = None
    rows = []
    try:
        with StageTimings(output / "timing.jsonl" if stage_timing else None) as timing:
            with timing.measure("environment_start"):
                if actual_split == "final-evaluation":
                    # The ordinary native reset owns the 512-action budget. M09 reset
                    # overrides deliberately allow only the old 64/128/256 matrix.
                    environment = m07.start_environment(engine, [template], output, reward, 0, 0, timeout, "final")
                else:
                    environment = m07.start_environment(engine, [template], output, reward, 0, 0, timeout, "development")
            with timing.measure("initial_snapshot"):
                initial = environment.controller.snapshot()
            if actual_split == "final-evaluation" and (initial["company"]["balance"] != 100_000 or
                    environment.controller.action_horizon != 512 or environment.controller.tick_horizon != 65_536):
                raise ValueError("Registered final cash/action/tick budget differs from native reset")
            with timing.measure("initial_write"):
                write_json(output / "initial.json", initial)
            rng = random.Random(seed)
            with timing.measure("package_before"):
                package_before = package_snapshot(package, backend) if package is not None else None
            with timing.measure("policy_start"):
                if policy in ("greedy", "sampled"):
                    if backend == "native":
                        client = m09_evaluator_client.EvaluatorClient.start(evaluator, package=package, sampling_seed=seed)
                    else:
                        client = m10_deployment_client.DeploymentClient.start(evaluator, package=package, sampling_seed=seed, mode="ingame")
            with (output / "actions.jsonl").open("w") as trace:
                for step in range(1, environment.controller.action_horizon + 1):
                    with timing.measure("legal_mask", step=step):
                        legal = m07.legal_mask(environment.mask)
                        prediction = None
                    if client is not None:
                        with timing.measure("policy_inputs", step=step):
                            structured_input = m07.structured(environment.observation)
                            spatial_input = m08.spatial(environment.observation)
                        with timing.measure("policy_request", step=step):
                            prediction = client.inspect([structured_input], [spatial_input], [legal],
                                                        deterministic=policy == "greedy")[0]
                        action = prediction.action
                    elif policy == "wait":
                        action = 0
                    elif policy == "random":
                        action = rng.choice([i for i, valid in enumerate(legal) if valid])
                    elif policy == "scripted":
                        action = m09.scripted_action(environment)
                        legal = m07.legal_mask(environment.mask)
                    elif policy in FLEET_SIZES:
                        action = service_action(environment.observation, legal, FLEET_SIZES[policy])
                    else:
                        raise ValueError(f"Unknown policy: {policy}")
                    if not legal[action]:
                        raise RuntimeError(f"Policy selected masked action {action}")
                    with timing.measure("trace_inputs", step=step):
                        before = m07.structured(environment.observation)
                        spatial_before = m08.spatial(environment.observation) if retain_spatial_inputs and client is not None else None
                    with timing.measure("game_step", step=step):
                        result = environment.controller.step(action)
                    if not result["termination"]["trainable"]:
                        raise RuntimeError(f"Untrainable transition: {result['termination']}")
                    environment.episode_length += 1
                    environment.episode_return += result["reward"]["scalar"]
                    with timing.measure("observe", step=step):
                        environment.observation = environment.controller.observe()
                    with timing.measure("trace_assemble", step=step):
                        row = {"step": step, "action": action, "legal": legal, "structured_before": before,
                               "prediction": dataclasses.asdict(prediction) if prediction else None,
                               "outcome": result["action_outcome"], "raw": result["reward"]["raw"],
                               "reward": result["reward"]["scalar"], "source": result["reward"]["source"],
                               "snapshot": result["snapshot"], "termination": result["termination"],
                               "buses": round(environment.observation["structured"]["data"][6] * 8),
                               "routes": round(environment.observation["structured"]["data"][9] * 8)}
                        if spatial_before is not None:
                            row["spatial_before"] = spatial_before
                    with timing.measure("trace_serialize", step=step):
                        encoded_row = json.dumps(row, allow_nan=False) + "\n"
                    with timing.measure("trace_write", step=step):
                        trace.write(encoded_row)
                    with timing.measure("trace_flush", step=step):
                        trace.flush()
                    rows.append(row)
                    if step % 128 == 0:
                        window = economic_window(rows[-128:])
                        label = "FINAL_EPISODE" if actual_split == "final-evaluation" else "DEV_EPISODE"
                        print(f"{label} policy={policy} template={template.stem} seed={seed} "
                              f"step={step} window_passengers={window['passengers']} "
                              f"window_profit={window['operating_profit']}", flush=True)
                    if result["termination"]["reason"] != "NONE":
                        break
                    with timing.measure("legal_actions_request", step=step):
                        environment.mask = environment.controller.mask()
            if result["termination"]["reason"] == "NONE":
                raise RuntimeError("Episode ended without an engine termination")
            total = economic_window(rows)
            windows = [economic_window(rows[i:i + 128]) for i in range(0, len(rows), 128)]
            source = rows[-1]["source"]["post"]
            capital = total["capital_spend"]
            profit = total["operating_profit"]
            first_delivery = next((row["step"] for row in rows if row["raw"]["delivered_passengers_delta"] > 0), None)
            first_running = next((row["step"] for row in rows if row["source"]["post"]["primary_bus_count"] >
                                  row["source"]["post"]["stopped_primary_bus_count"]), None)
            status.update(status="completed", actions=len(rows), return_=environment.episode_return,
                          termination=result["termination"], bankruptcy=result["termination"]["reason"] == "BANKRUPTCY",
                          passengers=total["passengers"], operating_profit=profit,
                          operating_income=source["operating_income_total"], operating_expenses=source["operating_expenses_total"],
                          capital_spend=capital, operating_profit_less_capital=profit - capital,
                          final_balance=result["snapshot"]["company"]["balance"],
                          balance_change=result["snapshot"]["company"]["balance"] - initial["company"]["balance"],
                          invalid_actions=sum(row["raw"]["native_rejected"] for row in rows),
                          vehicle_losses=sum(row["raw"]["vehicle_loss_count"] for row in rows),
                          idle_bus_ticks=sum(row["raw"]["idle_bus_ticks"] for row in rows),
                          first_delivery_action=first_delivery, first_running_action=first_running,
                          final_buses=rows[-1]["buses"], final_routes=rows[-1]["routes"],
                          action_counts=dict(sorted(Counter(row["action"] for row in rows).items())), windows=windows,
                          service_in_all_final_three_windows=len(windows) == 4 and all(
                              w["passengers"] > 0 and w["operating_profit"] > 0 for w in windows[-3:]))
            with timing.measure("environment_close"):
                environment.controller.close(timeout)
            environment = None
            if client is not None:
                with timing.measure("policy_close"):
                    package_id, state_hash = client.close(timeout)
                client = None
                with timing.measure("package_after"):
                    if package_id != package.name or package_snapshot(package, backend) != package_before:
                        raise RuntimeError("Evaluation package identity changed")
                status.update(package_id=package_id, model_state_sha256=state_hash)
            return status
    except BaseException as exc:
        status.update(status="failed", error=str(exc), completed_actions=len(rows))
        raise
    finally:
        if environment is not None:
            environment.controller.abort()
        if client is not None:
            client.abort()
        status["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "episode.json", status)


def evaluate_job(job):
    options, profile, validation = job
    bridge_validation.configure(validation)
    if not profile:
        return episode(**options)
    profiler = cProfile.Profile()
    try:
        return profiler.runcall(episode, **options)
    finally:
        if options["output"].is_dir():
            profiler.dump_stats(str(options["output"] / "profile.pstats"))


def run(args) -> None:
    training, development = m07.partition_templates(ROOT, args.instance_dir.resolve())
    templates = development if args.split == "development" else training
    if args.templates:
        requested = set(args.templates)
        templates = [p for p in templates if p.stem in requested]
        if {p.stem for p in templates} != requested:
            raise ValueError("Requested templates must belong to the selected non-final split")
    engine = args.openttd.resolve()
    package = args.package.resolve() if args.package else None
    evaluator = args.evaluator.resolve() if args.evaluator else None
    if not engine.is_file():
        raise ValueError("OpenTTD executable missing")
    if any(p in ("greedy", "sampled") for p in args.policies):
        if package is None or evaluator is None or not evaluator.is_file():
            raise ValueError("Neural evaluation requires --package and --evaluator")
    reward = validate_m06_reward_contract.validate(ROOT / "config/v1/m06-reward-trajectory-contract.json",
                    ROOT / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "complete-episode-development-evaluation", "status": "running",
              "source": source_identity(), "platform": platform.platform(), "python": sys.version,
              "engine_sha256": m09.sha256_file(engine), "split": args.split, "final_evaluation_accessed": False,
              "evaluator_sha256": m09.sha256_file(evaluator) if evaluator else None,
              "package": str(package) if package else None,
              "package_hashes": package_snapshot(package, args.backend) if package else None,
              "inference_backend": args.backend,
              "hypothesis": args.hypothesis, "action_horizon": 512, "ticks_per_action": 128,
              "criteria": "Report full-episode deliveries, lifetime operating profit, net capital cost, invalid actions, "
                          "bankruptcy, and delivery with positive profit in each of the final three 128-action windows. "
                          "These are development diagnostics; no held-out/generalization claim.",
              "policies": args.policies, "sampling_seeds": args.seeds,
              "deterministic_baselines_repeated": False, "workers": args.workers,
              "executor": args.executor, "profile": args.profile,
              "stage_timing": getattr(args, "stage_timing", False),
              "bridge_validation": args.bridge_validation, "episodes": []}
    jobs = [(policy, template, seed) for policy in args.policies for template in templates
            for seed in (args.seeds if policy in ("random", "sampled") else args.seeds[:1])]
    write_json(output / "run.json", record)
    jobs = [(dict(engine=engine, template=template, reward=reward, policy=policy, seed=seed,
                  evaluator=evaluator, package=package, timeout=args.timeout, backend=args.backend, evaluation_split=args.split,
                  output=output / f"{policy}-{template.stem}-s{seed}",
                  retain_spatial_inputs=getattr(args, "retain_spatial_inputs", False),
                  stage_timing=getattr(args, "stage_timing", False)), args.profile, args.bridge_validation)
            for policy, template, seed in jobs]
    try:
        executor = ProcessPoolExecutor if args.executor == "process" else ThreadPoolExecutor
        extra = {"mp_context": multiprocessing.get_context("spawn")} if args.executor == "process" else {}
        with executor(max_workers=args.workers, **extra) as pool:
            for result in pool.map(evaluate_job, jobs):
                record["episodes"].append(result)
                write_json(output / "run.json", record)
        record["status"] = "completed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "run.json", record)
    print(f"Complete episode results: {output}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--instance-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--backend", choices=("native", "onnx"), default="native",
                        help="CPU inference through LibTorch or the native in-game ONNX adapter")
    parser.add_argument("--policies", nargs="+", choices=POLICIES, default=["wait", "random", "scripted"])
    parser.add_argument("--seeds", nargs="+", type=positive, default=[20260923, 20260924, 20260925])
    parser.add_argument("--split", choices=("training", "development"), default="development")
    parser.add_argument("--templates", nargs="+")
    parser.add_argument("--workers", type=positive, choices=range(1, 5), default=2)
    parser.add_argument("--executor", choices=("thread", "process"), default="process")
    parser.add_argument("--retain-spatial-inputs", action="store_true",
                        help="Retain full CNN inputs for device replay (increases trace storage)")
    parser.add_argument("--stage-timing", action="store_true",
                        help="Write separate per-episode stage wall times; does not time GPU kernels")
    parser.add_argument("--profile", action="store_true", help="Save per-episode cProfile data; affects timing")
    parser.add_argument("--bridge-validation", choices=("reference", "fast"), default="reference")
    parser.add_argument("--timeout", type=positive, default=60)
    parser.add_argument("--hypothesis", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Development evaluation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
