#!/usr/bin/env python3
"""Run the frozen M11 normal-game neural playback acceptance gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import shutil
import struct
import subprocess
import sys
from typing import Any

import m10_deployment_client
import run_m02_reset_oracle
import validate_m07_ppo_contract
import validate_m11_playback_contract


class M11PlaybackGateError(RuntimeError):
    """The M11 playback gate failed closed."""


M11_COMPATIBILITY = "3f331f7852b0174714de30b8ab6015178d7e01d4691832f8af2085d32bb01e42"
M10_COMPATIBILITY = "e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6"
ACCEPTED_PACKAGE = "0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9"
ACCEPTED_MODEL = "10df689ccc6d1cb7f2e98f05f0474f72577cd9328a4589e3b1c7167bcbf08b5b"
ACTION_COUNT = 41


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M11PlaybackGateError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def write_canonical(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected an object in {path}")
    return value


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    require(path.is_file(), f"missing action log: {path}")
    payload = path.read_bytes()
    require(payload.endswith(b"\n") and not payload.endswith(b"\n\n") and b"\r" not in payload, f"non-canonical JSONL framing: {path}")
    lines = payload.splitlines()
    result = [json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))) for line in lines]

    def sorted_objects(value: Any) -> bool:
        if isinstance(value, dict):
            return list(value) == sorted(value) and all(sorted_objects(item) for item in value.values())
        if isinstance(value, list):
            return all(sorted_objects(item) for item in value)
        return True

    # nlohmann::json and Python use different shortest-round-trip spellings for
    # a few IEEE-754 values, so byte reserialization is not a valid canonicality
    # test across languages. The native format contract is sorted objects,
    # compact one-record-per-line JSON, finite values, and LF framing.
    require(all(sorted_objects(item) for item in result), f"non-canonical JSON object ordering: {path}")
    require(all(b" " not in line and b"\t" not in line for line in lines), f"non-compact JSONL: {path}")
    return result


def repository_identity(root: pathlib.Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()
    clean = not subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, text=True, capture_output=True
    ).stdout
    require(len(commit) == 40 and clean, "G11 must run from a clean committed repository")
    return commit, clean


def validate_package(package: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    require(package.is_absolute() and package.is_dir() and not package.is_symlink(), "accepted package is missing")
    require(package.name == ACCEPTED_PACKAGE == contract["accepted_package"]["package_id"], "accepted package ID drifted")
    inventory = sorted(item.name for item in package.iterdir())
    require(inventory == ["INSTALL.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx"], "accepted package inventory drifted")
    manifest = load_json(package / "manifest.json")
    require(manifest["package_id"] == package.name, "manifest package identity drifted")
    semantic = dict(manifest)
    semantic.pop("package_id")
    require(hashlib.sha256(canonical_bytes(semantic)).hexdigest() == package.name, "package content address is invalid")
    require(manifest["compatibility"]["m10_sha256"] == M10_COMPATIBILITY, "package M10 compatibility drifted")
    require(manifest["architecture"]["architecture_id"] == contract["accepted_package"]["architecture_id"], "package architecture drifted")
    require(sha256_file(package / "model.onnx") == ACCEPTED_MODEL == contract["accepted_package"]["model_sha256"], "accepted model digest drifted")
    for name, digest in manifest["files"].items():
        require(sha256_file(package / name) == digest, f"package payload digest drifted: {name}")
    return manifest


def playback_config(
    *, package: pathlib.Path, scenario: pathlib.Path, run_root: pathlib.Path,
    mode: str, seed: int, interval: int, maximum_actions: int,
    window: bool = False, exit_when_complete: bool = True,
) -> dict[str, Any]:
    return {
        "acceptance": {"exit_when_complete": exit_when_complete, "maximum_actions": maximum_actions},
        "contract_sha256": M11_COMPATIBILITY,
        "controls": {"agent_step_button": True, "native_pause_button": True, "start_agent_paused": False},
        "inference": {"interval_ticks": interval, "mode": mode, "sampling_seed": seed},
        "inspection": {
            "debug_overlay": window,
            "report_path": str((run_root / "inspection.json").resolve()),
            "window": window,
        },
        "logging": {
            "actions": True,
            "maximum_records": max(1, maximum_actions),
            "path": str((run_root / "actions.jsonl").resolve()),
        },
        "package_path": str(package.resolve()),
        "scenario_instance": str(scenario.resolve()),
        "schema_version": "openttd-rl-v1-m11-playback-config-1",
    }


def run_playback(
    *, runtime: pathlib.Path, run_root: pathlib.Path, config: dict[str, Any] | None,
    timeout: float, visible: bool = False, config_path: pathlib.Path | None = None,
    extra_environment: dict[str, str] | None = None, expect_success: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    run_root.mkdir(parents=True, exist_ok=False)
    (run_root / "openttd.cfg").write_text("\n", encoding="utf-8")
    if config_path is None:
        config_path = run_root / "playback.json"
    if config is not None:
        write_canonical(config_path, config)
    command = [
        str(runtime / "openttd"), "-X", "-s", "null", "-m", "null", "-I", "OpenGFX", "-Q", "-x",
        "-c", str(run_root / "openttd.cfg"), "-A", str(config_path),
    ]
    environment = os.environ.copy()
    if visible:
        command[1:1] = ["-v", "sdl", "-b", "32bpp-anim", "-r", "800x600"]
        environment.update({"SDL_AUDIODRIVER": "dummy", "SDL_VIDEODRIVER": "dummy"})
    else:
        command[1:1] = ["-v", "null:ticks=200000", "-b", "null"]
    if extra_environment:
        environment.update(extra_environment)
    result = subprocess.run(command, cwd=run_root, env=environment, capture_output=True, timeout=timeout)
    if expect_success:
        require(result.returncode == 0, f"playback failed rc={result.returncode}: {result.stderr.decode(errors='replace')[-2000:]}")
    else:
        require(result.returncode != 0, "invalid playback input was accepted")
    return result


def assert_complete(run_root: pathlib.Path, count: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = load_json(run_root / "inspection.json")
    records = load_jsonl(run_root / "actions.jsonl")
    require(report["status"] == "COMPLETE" and report["failure"] is None, "playback did not complete cleanly")
    require(report["action_count"] == count == len(records), "playback action count drifted")
    require(report["latest"] == records[-1], "inspection state differs from the latest structured action record")
    require([item["transition_ordinal"] for item in records] == list(range(count)), "action ordinals are not contiguous")
    require(all(len(item["legal_mask"]) == ACTION_COUNT and item["legal_mask"][item["current_action"]["index"]] == 1 for item in records), "controller selected an illegal action")
    return report, records


def png_dimensions(path: pathlib.Path) -> tuple[int, int]:
    payload = path.read_bytes()
    require(len(payload) > 4096 and payload[:8] == b"\x89PNG\r\n\x1a\n" and payload[12:16] == b"IHDR", "visible evidence is not a substantive PNG")
    return struct.unpack(">II", payload[16:24])


def clean_playback_campaign(args: argparse.Namespace, runtime: pathlib.Path) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    results: list[dict[str, Any]] = []
    records_by_template: dict[str, list[dict[str, Any]]] = {}
    for number in (7, 8):
        template_id = f"m02-template-{number:02d}"
        scenario = args.templates / f"{template_id}.json"
        run_root = args.artifact_root / "playback" / template_id
        config = playback_config(
            package=args.package, scenario=scenario, run_root=run_root, mode="greedy",
            seed=2026110101, interval=128, maximum_actions=24, window=number == 7,
        )
        run_playback(runtime=runtime, run_root=run_root, config=config, timeout=args.timeout, visible=number == 7)
        report, records = assert_complete(run_root, 24)
        state = report["latest"]["reward_relevant_state"]
        families = {item["current_action"]["family"] for item in records}
        require({"BUILD_BUS_STOP", "BUILD_ROAD_CONNECTOR", "BUILD_ROAD_DEPOT", "BUY_BUS", "ASSIGN_ROUTE", "RUN_BUS"} <= families, f"{template_id} did not exercise the complete bus lifecycle")
        require(state["primary_bus_count"] > 0 and state["delivered_passengers"] > 0 and state["income"] > 0, f"{template_id} did not reach positive service income")
        results.append({
            "action_count": len(records), "action_log_sha256": sha256_file(run_root / "actions.jsonl"),
            "delivered_passengers": state["delivered_passengers"], "income": state["income"],
            "inspection_report_sha256": sha256_file(run_root / "inspection.json"), "template_id": template_id,
        })
        records_by_template[template_id] = records
    screenshot = args.artifact_root / "playback/m02-template-07/screenshot/m11-playback.png"
    require(png_dimensions(screenshot) == (800, 600), "visible playback screenshot dimensions drifted")
    visible = {"path": str(screenshot.relative_to(args.artifact_root)), "sha256": sha256_file(screenshot), "width": 800, "height": 600}
    return results, visible, records_by_template


def determinism_campaign(args: argparse.Namespace, runtime: pathlib.Path, accepted: list[dict[str, Any]]) -> dict[str, Any]:
    scenario = args.templates / "m02-template-07.json"
    greedy_root = args.artifact_root / "determinism/greedy-repeat"
    config = playback_config(package=args.package, scenario=scenario, run_root=greedy_root, mode="greedy", seed=99, interval=128, maximum_actions=24)
    run_playback(runtime=runtime, run_root=greedy_root, config=config, timeout=args.timeout)
    _, greedy = assert_complete(greedy_root, 24)
    require(greedy == accepted, "greedy normal-game playback is not exactly reproducible")

    stochastic: dict[int, list[dict[str, Any]]] = {}
    for seed, suffix in ((2026110201, "seed-a"), (2026110201, "seed-a-repeat"), (2026110202, "seed-b")):
        run_root = args.artifact_root / "determinism" / suffix
        config = playback_config(package=args.package, scenario=scenario, run_root=run_root, mode="seeded-stochastic", seed=seed, interval=128, maximum_actions=24)
        run_playback(runtime=runtime, run_root=run_root, config=config, timeout=args.timeout)
        _, records = assert_complete(run_root, 24)
        stochastic.setdefault(seed, records)
        if suffix.endswith("repeat"):
            require(records == stochastic[seed], "same-seed stochastic playback is not exactly reproducible")
    actions_a = [item["current_action"]["index"] for item in stochastic[2026110201]]
    actions_b = [item["current_action"]["index"] for item in stochastic[2026110202]]
    require(actions_a != actions_b, "different stochastic seeds did not diverge")
    return {"different_seed_diverged": True, "greedy_repeat_exact": True, "same_seed_repeat_exact": True}


def interval_campaign(args: argparse.Namespace, runtime: pathlib.Path) -> list[dict[str, Any]]:
    results = []
    scenario = args.templates / "m02-template-08.json"
    for interval in range(128, 1025, 128):
        run_root = args.artifact_root / "intervals" / str(interval)
        config = playback_config(package=args.package, scenario=scenario, run_root=run_root, mode="greedy", seed=7, interval=interval, maximum_actions=2)
        run_playback(runtime=runtime, run_root=run_root, config=config, timeout=args.timeout)
        _, records = assert_complete(run_root, 2)
        require([item["tick"] for item in records] == [0, interval], f"inference interval {interval} was not exact")
        results.append({"interval_ticks": interval, "observed_ticks": [0, interval]})
    return results


def startup_rejection(args: argparse.Namespace, runtime: pathlib.Path, label: str, config: dict[str, Any] | None, path: pathlib.Path | None = None) -> None:
    run_playback(
        runtime=runtime, run_root=args.artifact_root / "rejections" / label,
        config=config, config_path=path, timeout=args.timeout, expect_success=False,
    )


def rejection_campaign(args: argparse.Namespace, runtime: pathlib.Path) -> list[str]:
    scenario = args.templates / "m02-template-07.json"
    missing = args.artifact_root / "rejections/missing-config/absent.json"
    startup_rejection(args, runtime, "missing-config", None, missing)
    startup_rejection(args, runtime, "invalid-config", {})

    missing_root = args.artifact_root / "mutations/missing-package" / ACCEPTED_PACKAGE
    config = playback_config(package=missing_root, scenario=scenario, run_root=args.artifact_root / "rejections/missing-package", mode="greedy", seed=1, interval=128, maximum_actions=1)
    startup_rejection(args, runtime, "missing-package", config)

    for label, mutation in (("incompatible-package", "manifest"), ("corrupt-model", "model")):
        package = args.artifact_root / "mutations" / label / ACCEPTED_PACKAGE
        shutil.copytree(args.package, package)
        if mutation == "manifest":
            manifest = load_json(package / "manifest.json")
            manifest["compatibility"]["m10_sha256"] = "0" * 64
            write_canonical(package / "manifest.json", manifest)
        else:
            (package / "model.onnx").write_bytes(b"corrupt")
        run_root = args.artifact_root / "rejections" / label
        config = playback_config(package=package, scenario=scenario, run_root=run_root, mode="greedy", seed=1, interval=128, maximum_actions=1)
        startup_rejection(args, runtime, label, config)

    run_root = args.artifact_root / "rejections/runtime-output-failure"
    config = playback_config(package=args.package, scenario=scenario, run_root=run_root, mode="greedy", seed=1, interval=128, maximum_actions=24, exit_when_complete=False)
    run_playback(
        runtime=runtime, run_root=run_root, config=config, timeout=args.timeout,
        extra_environment={"OPENTTD_RL_M11_FAULT_INJECT_AFTER_ACTION": "1"},
    )
    report = load_json(run_root / "inspection.json")
    records = load_jsonl(run_root / "actions.jsonl")
    require(report["status"] == "FAILED" and report["failure"] and report["action_count"] == 1, "runtime inference failure did not disable the controller")
    require(len(records) == 1 and report["latest"] == records[0], "runtime failure performed a fallback action")
    return ["missing-config", "invalid-config", "missing-package", "incompatible-package", "corrupt-model", "runtime-output-failure"]


def close_enough(expected: float, observed: float, absolute: float, relative: float) -> bool:
    return math.isfinite(observed) and abs(expected - observed) <= absolute + relative * abs(expected)


def golden_equivalence(args: argparse.Namespace, package_contract: dict[str, Any]) -> dict[str, Any]:
    cases = [json.loads(line) for line in (args.package / "golden.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(cases) == 12, "golden.jsonl must contain the frozen twelve cases")
    tolerances = package_contract["tolerances"]
    maximums = {"logit": 0.0, "probability": 0.0, "value": 0.0}
    for mode in ("standalone", "ingame"):
        client = m10_deployment_client.DeploymentClient.start(
            args.deployment_evaluator, package=args.package, sampling_seed=2026110301, mode=mode
        )
        try:
            observed = client.inspect(
                [item["structured"] for item in cases], [item["spatial"] for item in cases],
                [item["legal_mask"] for item in cases], deterministic=True,
            )
            package_id, model_sha = client.close(args.timeout)
        except Exception:
            client.abort()
            raise
        require(package_id == ACCEPTED_PACKAGE and model_sha == ACCEPTED_MODEL, f"{mode} evaluator identity drifted")
        for case, result in zip(cases, observed, strict=True):
            require(result.action == case["greedy_action"] and case["legal_mask"][result.action] == 1, f"{mode} golden action drifted")
            for expected, actual in zip(case["policy_logits"], result.logits, strict=True):
                require(close_enough(expected, actual, **tolerances["policy_logits"]), f"{mode} golden logits exceeded tolerance")
                maximums["logit"] = max(maximums["logit"], abs(expected - actual))
            for expected, actual in zip(case["masked_probabilities"], result.probabilities, strict=True):
                require(close_enough(expected, actual, **tolerances["masked_probabilities"]), f"{mode} golden probabilities exceeded tolerance")
                maximums["probability"] = max(maximums["probability"], abs(expected - actual))
            require(close_enough(case["value"], result.value, **tolerances["value"]), f"{mode} golden value exceeded tolerance")
            maximums["value"] = max(maximums["value"], abs(case["value"] - result.value))
    return {"case_count": len(cases), "modes": ["standalone", "ingame"], "maximum_absolute_errors": maximums}


def dependency_boundary(openttd: pathlib.Path, evaluator: pathlib.Path) -> dict[str, Any]:
    records: dict[str, list[str]] = {}
    for label, executable in (("openttd", openttd), ("deployment-evaluator", evaluator)):
        output = subprocess.run(["ldd", str(executable)], check=True, text=True, capture_output=True).stdout
        lower = output.lower()
        # LibTorch, Python, CUDA, optimizers, and trainers are forbidden in normal inference.
        forbidden = ["libtorch", "libc10", "libpython", "libcuda", "libcudart", "optimizer", "trainer"]
        require(not any(item in lower for item in forbidden), f"{label} links a forbidden training/runtime dependency")
        require("libonnxruntime.so.1" in output and "libcrypto.so.3" in output, f"{label} lacks the pinned inference/integrity libraries")
        records[label] = output.splitlines()
    return {"forbidden_absent": ["LibTorch", "Python runtime", "CUDA", "optimizer", "trainer"], "ldd": records}


def run(args: argparse.Namespace) -> dict[str, Any]:
    require(args.artifact_root.is_absolute() and not args.artifact_root.exists(), "artifact root must be a new absolute path")
    commit, clean = repository_identity(args.repository_root)
    contract = validate_m11_playback_contract.validate(args.contract, args.contract_schema)
    require(contract["identity"]["compatibility_sha256"] == M11_COMPATIBILITY, "M11 contract drifted")
    validate_package(args.package, contract)
    package_contract = validate_m07_ppo_contract.load_strict_json(args.package_contract)
    require(package_contract["identity"]["compatibility_sha256"] == M10_COMPATIBILITY, "M10 contract drifted")
    for number in (7, 8):
        require((args.templates / f"m02-template-{number:02d}.json").is_file(), "retained M02 playback template is missing")

    args.artifact_root.mkdir(parents=True)
    runtime = args.artifact_root / "runtime"
    runtime_assets = run_m02_reset_oracle.stage_runtime(args.openttd, args.opengfx_tar, runtime)
    dependencies = dependency_boundary(runtime / "openttd", args.deployment_evaluator)
    golden = golden_equivalence(args, package_contract)
    playbacks, visible, records = clean_playback_campaign(args, runtime)
    determinism = determinism_campaign(args, runtime, records["m02-template-07"])
    intervals = interval_campaign(args, runtime)
    rejections = rejection_campaign(args, runtime)
    require(rejections == contract["failure_policy"]["required_rejections"], "failure rejection inventory drifted")

    report: dict[str, Any] = {
        "contract_sha256": M11_COMPATIBILITY,
        "dependency_boundary": dependencies,
        "determinism": determinism,
        "executable_sha256": sha256_file(runtime / "openttd"),
        "failure_rejections": rejections,
        "golden_equivalence": golden,
        "inference_intervals": intervals,
        "package_id": ACCEPTED_PACKAGE,
        "playbacks": playbacks,
        "repository_clean": clean,
        "repository_commit": commit,
        "runtime_assets_sha256": hashlib.sha256(canonical_bytes(runtime_assets)).hexdigest(),
        "schema_version": "openttd-rl-v1-m11-playback-gate-report-1",
        "status": "PASS",
        "visible_evidence": visible,
    }
    report["report_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    write_canonical(args.artifact_root / "m11-playback-gate-report.json", report)
    print(
        f"M11_PLAYBACK_GATE=PASS playbacks={len(playbacks)} golden={golden['case_count']} "
        f"intervals={len(intervals)} rejections={len(rejections)} report_sha256={report['report_sha256']}",
        flush=True,
    )
    return report


def absolute_file(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_file():
        raise argparse.ArgumentTypeError("must be an existing absolute file")
    return path


def absolute_directory(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise argparse.ArgumentTypeError("must be an existing absolute directory")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=absolute_directory, required=True)
    parser.add_argument("--contract", type=absolute_file, required=True)
    parser.add_argument("--contract-schema", type=absolute_file, required=True)
    parser.add_argument("--package-contract", type=absolute_file, required=True)
    parser.add_argument("--openttd", type=absolute_file, required=True)
    parser.add_argument("--opengfx-tar", type=absolute_file, required=True)
    parser.add_argument("--package", type=absolute_directory, required=True)
    parser.add_argument("--templates", type=absolute_directory, required=True)
    parser.add_argument("--deployment-evaluator", type=absolute_file, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    try:
        require(1 <= args.timeout <= 3600, "timeout must be in 1..3600 seconds")
        run(args)
    except Exception as error:
        print(f"M11_PLAYBACK_GATE=FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
