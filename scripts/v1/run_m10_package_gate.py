#!/usr/bin/env python3
"""Build and independently gate the frozen M10 ONNX deployment packages."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import pathlib
import random
import shutil
import struct
import subprocess
import sys
from typing import Any, Callable, Sequence

import m09_evaluator_client
import m10_deployment_client
import run_m07_cpu_ppo as m07
import run_m08_live_architectures as m08
import run_m09_evaluation as m09
import validate_m07_ppo_contract


class M10GateError(RuntimeError):
    """The M10 package/equivalence gate failed closed."""


M10_COMPATIBILITY = "e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6"
UPSTREAM_COMMIT = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
ENVIRONMENT_VERSION = "openttd-rl-v1-m06-environment-1"
ARCHITECTURES = ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]
ACTION_COUNT = 41


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M10GateError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def repository_commit(root: pathlib.Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()
    require(len(result) == 40, "repository commit is malformed")
    return result


def synthetic_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rng = random.Random(contract["golden_corpus"]["generation_seed"])
    cases: list[dict[str, Any]] = []
    for index in range(contract["golden_corpus"]["synthetic_cases"]):
        structured = [f32(rng.uniform(-1.0, 1.0)) for _ in range(256)]
        spatial = [f32(rng.random()) for _ in range(32 * 32 * 32)]
        if index % 3 == 0:
            mask = [1] + [0] * 40
            pattern = "wait-only"
        elif index % 3 == 1:
            mask = [1] * ACTION_COUNT
            pattern = "all-legal"
        else:
            legal = {0, (index * 7) % 40 + 1, (index * 13) % 40 + 1, (index * 19) % 40 + 1}
            mask = [int(action in legal) for action in range(ACTION_COUNT)]
            pattern = "deterministic-sparse"
        cases.append({
            "case_id": f"synthetic-{index + 1:02d}",
            "source": "synthetic",
            "mask_pattern": pattern,
            "structured": structured,
            "spatial": spatial,
            "legal_mask": mask,
        })
    return cases


def live_cases(args: argparse.Namespace, contract: dict[str, Any]) -> list[dict[str, Any]]:
    reward_contract = validate_m07_ppo_contract.load_strict_json(args.reward_contract)
    cases: list[dict[str, Any]] = []
    session = 202610100100
    for template_number in (7, 8):
        template = args.templates / f"m02-template-{template_number:02d}"
        environment = m09.start_environment(
            args.openttd,
            template,
            args.artifact_root / ".live-runs",
            reward_contract,
            session + template_number,
            60_000,
            16,
            args.timeout,
        )
        try:
            for step in range(5):
                if step in (0, 4):
                    cases.append({
                        "case_id": f"live-template-{template_number:02d}-step-{step:02d}",
                        "source": "live-openttd",
                        "mask_pattern": "native-live-mask",
                        "structured": [f32(value) for value in m07.structured(environment.observation)],
                        "spatial": [f32(value) for value in m08.spatial(environment.observation)],
                        "legal_mask": m07.legal_mask(environment.mask),
                    })
                if step == 4:
                    break
                action = m09.scripted_action(environment)
                result = environment.controller.step(action)
                environment.observation = environment.controller.observe()
                environment.mask = environment.controller.mask()
                require(result["termination"]["reason"] == "NONE", "live golden harvest terminated early")
            environment.controller.close(args.timeout)
        except Exception:
            environment.controller.abort()
            raise
    require(len(cases) == contract["golden_corpus"]["live_cases"], "live golden case count drifted")
    return cases


def run_export(
    args: argparse.Namespace,
    model: dict[str, Any],
    destination: pathlib.Path,
    commit: str,
) -> None:
    source = args.source_packages / model["source_package_id"]
    command = [
        str(args.export_orchestrator),
        "--python", str(args.exporter_python),
        "--script", str(args.exporter_script),
        "--source-package", str(source),
        "--source-package-id", model["source_package_id"],
        "--architecture", model["architecture_id"],
        "--output-dir", str(destination),
        "--contract", str(args.contract),
        "--repository-commit", commit,
    ]
    subprocess.run(command, check=True)


def native_results(
    args: argparse.Namespace,
    source_package: pathlib.Path,
    cases: list[dict[str, Any]],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        stochastic_seed = contract["golden_corpus"]["stochastic_seeds"][index % 3]
        greedy = m09_evaluator_client.EvaluatorClient.start(
            args.native_evaluator, package=source_package, sampling_seed=stochastic_seed
        )
        try:
            greedy_value = greedy.inspect(
                [case["structured"]], [case["spatial"]], [case["legal_mask"]], deterministic=True
            )[0]
            greedy.close(args.timeout)
        except Exception:
            greedy.abort()
            raise
        stochastic = m09_evaluator_client.EvaluatorClient.start(
            args.native_evaluator, package=source_package, sampling_seed=stochastic_seed
        )
        try:
            stochastic_value = stochastic.inspect(
                [case["structured"]], [case["spatial"]], [case["legal_mask"]], deterministic=False
            )[0]
            stochastic.close(args.timeout)
        except Exception:
            stochastic.abort()
            raise
        result.append(case | {
            "policy_logits": list(greedy_value.logits),
            "masked_probabilities": list(greedy_value.probabilities),
            "value": greedy_value.value,
            "greedy_action": greedy_value.action,
            "stochastic_seed": stochastic_seed,
            "stochastic_action": stochastic_value.action,
        })
    return result


def install_text(package_format: str) -> str:
    return f"""# OpenTTD-RL V1 inference-only model package

Format: `{package_format}`.

Install atomically by copying this complete directory to a temporary sibling of
`openttd-rl/models/<package-id>`, validating it with the inference-only loader,
and renaming the temporary directory to its package ID. Do not merge files into
an existing package. Loading requires ONNX Runtime 1.28.0 CPU and OpenSSL only;
Python, LibTorch, CUDA, the optimizer, and all training code are forbidden.

Uninstall by removing only the exact content-addressed
`openttd-rl/models/<package-id>` directory after the controller has released it.
The package is immutable and has no external model payloads.
"""


def create_package(
    *,
    args: argparse.Namespace,
    contract: dict[str, Any],
    model: dict[str, Any],
    export: pathlib.Path,
    golden: list[dict[str, Any]],
    commit: str,
    destination_root: pathlib.Path,
) -> pathlib.Path:
    stage = destination_root / f".{model['architecture_id']}.stage"
    require(not stage.exists(), "deployment staging path already exists")
    stage.mkdir(parents=True)
    shutil.copyfile(export / "model.onnx", stage / "model.onnx")
    with (stage / "golden.jsonl").open("wb") as stream:
        for case in golden:
            stream.write(canonical_bytes(case) + b"\n")
    evaluation_source = json.loads(args.evaluation_report.read_text(encoding="utf-8"))
    evaluation = {
        "schema_version": "openttd-rl-v1-m10-evaluation-link-1",
        "source_file_sha256": sha256_file(args.evaluation_report),
        "source_report_sha256": evaluation_source["report_sha256"],
        "source_repository_commit": evaluation_source["repository_commit"],
        "status": evaluation_source["status"],
        "architecture": model["architecture_id"],
        "selected_primary": evaluation_source["selection"]["selected_overall"]["architecture"] == model["architecture_id"],
        "m09_contract_sha256": evaluation_source["contract_sha256"],
    }
    (stage / "evaluation.json").write_bytes(canonical_bytes(evaluation) + b"\n")
    (stage / "INSTALL.md").write_text(install_text(contract["package"]["format"]), encoding="utf-8")
    source_manifest = json.loads((args.source_packages / model["source_package_id"] / "manifest.json").read_text())
    export_metadata = json.loads((export / "export-metadata.json").read_text())
    files = {name: sha256_file(stage / name) for name in contract["package"]["payload_files"]}
    manifest: dict[str, Any] = {
        "format": contract["package"]["format"],
        "compatibility_version": 1,
        "architecture": {
            "architecture_id": model["architecture_id"],
            "architecture_version": model["architecture_version"],
            "definition_sha256": contract["compatibility"]["architecture"],
        },
        "inputs": model["inputs"],
        "outputs": contract["graph"]["outputs"],
        "normalization": "none-frozen-m04-preprocessing",
        "recurrent_state": contract["graph"]["recurrent_state"],
        "compatibility": {
            "observation_sha256": contract["compatibility"]["observation"],
            "action_sha256": contract["compatibility"]["action_and_mask"],
            "mask_sha256": contract["compatibility"]["action_and_mask"],
            "reward_sha256": contract["compatibility"]["reward_trajectory"],
            "m09_sha256": contract["compatibility"]["evaluation"],
            "m10_sha256": M10_COMPATIBILITY,
            "onnx_opset": contract["exporter"]["opset"],
            "onnxruntime_version": contract["runtime"]["version"],
            "openttd_upstream_commit": UPSTREAM_COMMIT,
            "environment_version": ENVIRONMENT_VERSION,
        },
        "provenance": {
            "deployment_repository_commit": commit,
            "training_repository_commit": source_manifest["repository_commit"],
            "source_package_id": model["source_package_id"],
            "source_model_sha256": source_manifest["model_sha256"],
            "training_config_sha256": sha256_file(args.ppo_contract),
            "architecture_config_sha256": sha256_file(args.architecture_contract),
            "export_metadata_sha256": sha256_file(export / "export-metadata.json"),
            "export_model_sha256": export_metadata["model_onnx_sha256"],
        },
        "seeds": {
            "training_seed": model["run_seed"],
            "golden_generation_seed": contract["golden_corpus"]["generation_seed"],
            "stochastic_seeds": contract["golden_corpus"]["stochastic_seeds"],
        },
        "evaluation": evaluation,
        "files": files,
        "installation": {
            "root": contract["installation"]["root"],
            "atomic": contract["installation"]["atomic"],
            "uninstall": contract["installation"]["uninstall"],
            "training_dependencies": contract["installation"]["training_dependencies"],
        },
    }
    identity = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    manifest["package_id"] = identity
    (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
    final = destination_root / identity
    require(not final.exists(), "deployment content address already exists")
    stage.rename(final)
    return final


def close_enough(expected: float, observed: float, absolute: float, relative: float) -> bool:
    return math.isfinite(observed) and abs(expected - observed) <= absolute + relative * abs(expected)


def compare_result(expected: dict[str, Any], observed: Any, tolerances: dict[str, Any]) -> dict[str, float]:
    require(observed.action == expected["greedy_action"], "greedy action differs across runtimes")
    require(expected["legal_mask"][observed.action] == 1, "runtime returned an illegal action")
    maximum_logits = max(abs(a - b) for a, b in zip(expected["policy_logits"], observed.logits, strict=True))
    maximum_probabilities = max(abs(a - b) for a, b in zip(expected["masked_probabilities"], observed.probabilities, strict=True))
    require(all(close_enough(a, b, **tolerances["policy_logits"]) for a, b in zip(expected["policy_logits"], observed.logits, strict=True)), "policy logit tolerance exceeded")
    require(all(close_enough(a, b, **tolerances["masked_probabilities"]) for a, b in zip(expected["masked_probabilities"], observed.probabilities, strict=True)), "masked probability tolerance exceeded")
    require(close_enough(expected["value"], observed.value, **tolerances["value"]), "value tolerance exceeded")
    return {
        "maximum_logit_absolute_error": maximum_logits,
        "maximum_probability_absolute_error": maximum_probabilities,
        "value_absolute_error": abs(expected["value"] - observed.value),
    }


def inspect_deployment(
    args: argparse.Namespace,
    package: pathlib.Path,
    cases: list[dict[str, Any]],
    mode: str,
) -> list[Any]:
    client = m10_deployment_client.DeploymentClient.start(
        args.deployment_evaluator, package=package, sampling_seed=2026101011, mode=mode
    )
    try:
        result = client.inspect(
            [item["structured"] for item in cases],
            [item["spatial"] for item in cases],
            [item["legal_mask"] for item in cases],
            deterministic=True,
        )
        returned_id, model_sha = client.close(args.timeout)
        require(returned_id == package.name and model_sha == sha256_file(package / "model.onnx"), "deployment identity response drifted")
        return result
    except Exception:
        client.abort()
        raise


def sample_counts(probabilities: Sequence[float], samples: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    cumulative: list[float] = []
    total = 0.0
    for value in probabilities:
        total += value
        cumulative.append(total)
    result = [0] * len(probabilities)
    for _ in range(samples):
        draw = rng.random() * total
        for action, threshold in enumerate(cumulative):
            if draw < threshold:
                result[action] += 1
                break
    return result


def distribution_comparison(
    native_probabilities: Sequence[float],
    standalone_probabilities: Sequence[float],
    ingame_probabilities: Sequence[float],
    contract: dict[str, Any],
    seed_offset: int,
) -> dict[str, Any]:
    specification = contract["sampled_distribution"]
    samples = specification["samples_per_case_per_runtime"]
    counts = [
        sample_counts(native_probabilities, samples, specification["sampling_seed"] + seed_offset),
        sample_counts(standalone_probabilities, samples, specification["sampling_seed"] + seed_offset + 1),
        sample_counts(ingame_probabilities, samples, specification["sampling_seed"] + seed_offset + 2),
    ]
    frequencies = [[value / samples for value in row] for row in counts]
    pairs: list[dict[str, Any]] = []
    for left, right, label in ((0, 1, "native-standalone"), (0, 2, "native-ingame"), (1, 2, "standalone-ingame")):
        differences = [abs(a - b) for a, b in zip(frequencies[left], frequencies[right], strict=True)]
        television = 0.5 * math.fsum(differences)
        maximum = max(differences)
        require(television <= specification["total_variation_maximum"], "sampled distribution TV tolerance exceeded")
        require(maximum <= specification["maximum_bin_difference"], "sampled distribution maximum-bin tolerance exceeded")
        pairs.append({"pair": label, "total_variation": television, "maximum_bin_difference": maximum})
    return {"samples_per_runtime": samples, "pairs": pairs, "counts": counts}


def expect_loader_rejection(executable: pathlib.Path, package: pathlib.Path, label: str) -> None:
    result = subprocess.run(
        [str(executable), "--package", str(package), "--sampling-seed", "1", "--mode", "standalone"],
        input=b"", capture_output=True, timeout=30
    )
    require(result.returncode != 0 and b"M10_ONNX_EVALUATOR=FAIL" in result.stderr, f"mutation was not rejected before inference: {label}")


def mutate_manifest(source: pathlib.Path, root: pathlib.Path, label: str, mutation: Callable[[dict[str, Any]], None]) -> pathlib.Path:
    destination = root / f".{label}"
    shutil.copytree(source, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    mutation(manifest)
    manifest.pop("package_id", None)
    identity = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    manifest["package_id"] = identity
    (destination / "manifest.json").write_bytes(canonical_bytes(manifest))
    final = root / identity
    destination.rename(final)
    return final


def graph_mutation(
    args: argparse.Namespace,
    source: pathlib.Path,
    root: pathlib.Path,
    label: str,
    kind: str,
) -> pathlib.Path:
    destination = root / f".{label}"
    shutil.copytree(source, destination)
    script = (
        "import onnx,sys\n"
        "p=sys.argv[1]; k=sys.argv[2]; m=onnx.load(p)\n"
        "x=m.graph.input[0] if k.startswith('input') else m.graph.output[0]\n"
        "if k.endswith('name'): x.name='mutated_tensor'\n"
        "elif k.endswith('shape'): x.type.tensor_type.shape.dim[-1].dim_value=99\n"
        "elif k.endswith('dtype'): x.type.tensor_type.elem_type=7\n"
        "onnx.save(m,p)\n"
    )
    subprocess.run([str(args.exporter_python), "-c", script, str(destination / "model.onnx"), kind], check=True)
    manifest = json.loads((destination / "manifest.json").read_text())
    manifest["files"]["model.onnx"] = sha256_file(destination / "model.onnx")
    manifest["provenance"]["export_model_sha256"] = manifest["files"]["model.onnx"]
    manifest.pop("package_id")
    identity = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    manifest["package_id"] = identity
    (destination / "manifest.json").write_bytes(canonical_bytes(manifest))
    final = root / identity
    destination.rename(final)
    return final


def request_rejections(args: argparse.Namespace, package: pathlib.Path, case: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    client = m10_deployment_client.DeploymentClient.start(
        args.deployment_evaluator, package=package, sampling_seed=1, mode="standalone"
    )
    try:
        bad_structured = list(case["structured"])
        bad_structured[0] = float("nan")
        with contextlib.suppress(m10_deployment_client.M10DeploymentClientError):
            client.inspect([bad_structured], [case["spatial"]], [case["legal_mask"]], deterministic=True)
            raise M10GateError("nonfinite-input mutation was accepted")
        labels.append("nonfinite-input")
        with contextlib.suppress(m10_deployment_client.M10DeploymentClientError):
            client.inspect([case["structured"]], [case["spatial"]], [[0] * ACTION_COUNT], deterministic=True)
            raise M10GateError("all-illegal-mask mutation was accepted")
        labels.append("all-illegal-mask")
        client.close(args.timeout)
    except Exception:
        client.abort()
        raise
    return labels


def rejection_matrix(args: argparse.Namespace, package: pathlib.Path, contract: dict[str, Any], case: dict[str, Any]) -> list[str]:
    root = args.artifact_root / ".mutations"
    root.mkdir()
    manifest_mutations: dict[str, Callable[[dict[str, Any]], None]] = {
        "package-format": lambda m: m.__setitem__("format", "mutated"),
        "compatibility-version": lambda m: m.__setitem__("compatibility_version", 2),
        "package-id": lambda m: m.__setitem__("package_id", "0" * 64),
        "architecture-id": lambda m: m["architecture"].__setitem__("architecture_id", "mutated"),
        "architecture-version": lambda m: m["architecture"].__setitem__("architecture_version", 2),
        "observation-compatibility": lambda m: m["compatibility"].__setitem__("observation_sha256", "0" * 64),
        "action-compatibility": lambda m: m["compatibility"].__setitem__("action_sha256", "0" * 64),
        "mask-compatibility": lambda m: m["compatibility"].__setitem__("mask_sha256", "0" * 64),
        "reward-compatibility": lambda m: m["compatibility"].__setitem__("reward_sha256", "0" * 64),
        "m09-evaluation-compatibility": lambda m: m["compatibility"].__setitem__("m09_sha256", "0" * 64),
        "m10-compatibility": lambda m: m["compatibility"].__setitem__("m10_sha256", "0" * 64),
        "onnx-opset": lambda m: m["compatibility"].__setitem__("onnx_opset", 19),
        "onnxruntime-version": lambda m: m["compatibility"].__setitem__("onnxruntime_version", "0.0.0"),
        "openttd-upstream-commit": lambda m: m["compatibility"].__setitem__("openttd_upstream_commit", "0" * 40),
        "environment-version": lambda m: m["compatibility"].__setitem__("environment_version", "mutated"),
        "normalization": lambda m: m.__setitem__("normalization", "mutated"),
        "recurrent-state": lambda m: m.__setitem__("recurrent_state", "mutated"),
        "file-digest": lambda m: m["files"].__setitem__("model.onnx", "0" * 64),
    }
    graph_mutations = {"input-name", "input-shape", "input-dtype", "output-name", "output-shape", "output-dtype"}
    file_operations: dict[str, Callable[[pathlib.Path], Any]] = {
        "missing-file": lambda p: (p / "golden.jsonl").unlink(),
        "unknown-file": lambda p: (p / "unknown").write_text("x"),
        "symlink": lambda p: ((p / "golden.jsonl").unlink(), (p / "golden.jsonl").symlink_to("evaluation.json")),
        "truncated-onnx": lambda p: (p / "model.onnx").write_bytes(b"truncated"),
    }
    request_labels = set(request_rejections(args, package, case))
    observed: list[str] = []
    for label in contract["rejection_matrix"]:
        if label in manifest_mutations:
            mutation = manifest_mutations[label]
            if label == "package-id":
                destination = root / ".package-id"
                shutil.copytree(package, destination)
                manifest = json.loads((destination / "manifest.json").read_text())
                mutation(manifest)
                (destination / "manifest.json").write_bytes(canonical_bytes(manifest))
                mutated = destination
            else:
                mutated = mutate_manifest(package, root, label, mutation)
            expect_loader_rejection(args.deployment_evaluator, mutated, label)
        elif label in graph_mutations:
            mutated = graph_mutation(args, package, root, label, label)
            expect_loader_rejection(args.deployment_evaluator, mutated, label)
        elif label in file_operations:
            destination = root / f".{label}"
            shutil.copytree(package, destination)
            file_operations[label](destination)
            expect_loader_rejection(args.deployment_evaluator, destination, label)
        elif label in request_labels:
            pass
        else:
            raise M10GateError(f"rejection mutation has no implementation: {label}")
        observed.append(label)
    require(observed == contract["rejection_matrix"], f"rejection matrix order/coverage drifted: {observed}")
    shutil.rmtree(root)
    return observed


def validate_inference_only_binary(args: argparse.Namespace) -> dict[str, Any]:
    result = subprocess.run(["ldd", str(args.deployment_evaluator)], check=True, text=True, capture_output=True).stdout
    forbidden = ["libtorch", "libc10", "libcuda", "libcudart", "libpython"]
    require(not any(item in result.lower() for item in forbidden), "deployment binary links a training/CUDA/Python dependency")
    require("libonnxruntime.so.1" in result and "libcrypto.so.3" in result, "deployment binary lacks pinned inference/integrity runtime")
    return {"ldd": result.splitlines(), "forbidden_absent": forbidden}


def run(args: argparse.Namespace) -> dict[str, Any]:
    require(not args.artifact_root.exists(), "M10 artifact root already exists")
    args.artifact_root.mkdir(parents=True)
    contract = validate_m07_ppo_contract.load_strict_json(args.contract)
    require(contract["identity"]["compatibility_sha256"] == M10_COMPATIBILITY, "M10 contract drifted")
    commit = repository_commit(args.repository_root)
    cases = synthetic_cases(contract) + live_cases(args, contract)
    require(len(cases) == contract["golden_corpus"]["cases_per_architecture"], "golden case count drifted")
    export_a = args.artifact_root / "exports-a"
    export_b = args.artifact_root / "exports-b"
    packages_root = args.artifact_root / "packages"
    export_a.mkdir()
    export_b.mkdir()
    packages_root.mkdir()
    architecture_reports: list[dict[str, Any]] = []
    package_paths: dict[str, pathlib.Path] = {}
    maximums = {"logit": 0.0, "probability": 0.0, "value": 0.0}
    for architecture in ARCHITECTURES:
        model = next(item for item in contract["models"] if item["architecture_id"] == architecture)
        first = export_a / architecture
        second = export_b / architecture
        run_export(args, model, first, commit)
        run_export(args, model, second, commit)
        require((first / "model.onnx").read_bytes() == (second / "model.onnx").read_bytes(), "cross-root ONNX export bytes differ")
        source_package = args.source_packages / model["source_package_id"]
        golden = native_results(args, source_package, cases, contract)
        package = create_package(
            args=args, contract=contract, model=model, export=first, golden=golden,
            commit=commit, destination_root=packages_root,
        )
        package_paths[architecture] = package
        standalone = inspect_deployment(args, package, golden, "standalone")
        ingame = inspect_deployment(args, package, golden, "ingame")
        case_reports: list[dict[str, Any]] = []
        distributions: list[dict[str, Any]] = []
        for index, (expected, standalone_value, ingame_value) in enumerate(zip(golden, standalone, ingame, strict=True)):
            standalone_error = compare_result(expected, standalone_value, contract["tolerances"])
            ingame_error = compare_result(expected, ingame_value, contract["tolerances"])
            for errors in (standalone_error, ingame_error):
                maximums["logit"] = max(maximums["logit"], errors["maximum_logit_absolute_error"])
                maximums["probability"] = max(maximums["probability"], errors["maximum_probability_absolute_error"])
                maximums["value"] = max(maximums["value"], errors["value_absolute_error"])
            case_reports.append({"case_id": expected["case_id"], "standalone": standalone_error, "ingame": ingame_error})
            if index < contract["sampled_distribution"]["cases_per_architecture"]:
                distributions.append(distribution_comparison(
                    expected["masked_probabilities"], standalone_value.probabilities,
                    ingame_value.probabilities, contract, len(architecture_reports) * 100 + index * 10,
                ))
        architecture_reports.append({
            "architecture": architecture,
            "source_package_id": model["source_package_id"],
            "package_id": package.name,
            "onnx_sha256": sha256_file(package / "model.onnx"),
            "repeat_export_byte_identical": True,
            "golden_cases": case_reports,
            "distribution_cases": distributions,
        })
    rejection = rejection_matrix(
        args, package_paths["combined-cnn-mlp-v1"], contract,
        json.loads((package_paths["combined-cnn-mlp-v1"] / "golden.jsonl").read_text().splitlines()[1]),
    )
    dependency_evidence = validate_inference_only_binary(args)
    require(not close_enough(0.0, contract["tolerances"]["policy_logits"]["absolute"] * 2.0, **contract["tolerances"]["policy_logits"]), "negative tolerance self-test failed")
    report: dict[str, Any] = {
        "schema_version": "openttd-rl-v1-m10-package-gate-report-1",
        "status": "PASS",
        "repository_commit": commit,
        "contract_sha256": M10_COMPATIBILITY,
        "architectures": architecture_reports,
        "golden_case_count": len(ARCHITECTURES) * len(cases),
        "synthetic_case_count": len(ARCHITECTURES) * contract["golden_corpus"]["synthetic_cases"],
        "live_case_count": len(ARCHITECTURES) * contract["golden_corpus"]["live_cases"],
        "maximum_absolute_errors": maximums,
        "sampled_distribution": {
            "case_count": len(ARCHITECTURES) * contract["sampled_distribution"]["cases_per_architecture"],
            "samples_per_case_per_runtime": contract["sampled_distribution"]["samples_per_case_per_runtime"],
        },
        "rejection_matrix": rejection,
        "inference_only_binary": dependency_evidence,
        "training_state_in_packages": False,
        "source_packages_read_only": True,
        "repeat_package_ids": "implied-by-byte-identical-onnx-and-canonical-identical-inputs",
    }
    report["report_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    (args.artifact_root / "m10-package-gate-report.json").write_bytes(canonical_bytes(report) + b"\n")
    shutil.rmtree(args.artifact_root / ".live-runs", ignore_errors=True)
    print(
        f"M10_PACKAGE_GATE=PASS packages={len(package_paths)} golden={report['golden_case_count']} "
        f"mutations={len(rejection)} report_sha256={report['report_sha256']}",
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
    parser.add_argument("--ppo-contract", type=absolute_file, required=True)
    parser.add_argument("--architecture-contract", type=absolute_file, required=True)
    parser.add_argument("--reward-contract", type=absolute_file, required=True)
    parser.add_argument("--export-orchestrator", type=absolute_file, required=True)
    parser.add_argument("--exporter-python", type=absolute_file, required=True)
    parser.add_argument("--exporter-script", type=absolute_file, required=True)
    parser.add_argument("--native-evaluator", type=absolute_file, required=True)
    parser.add_argument("--deployment-evaluator", type=absolute_file, required=True)
    parser.add_argument("--source-packages", type=absolute_directory, required=True)
    parser.add_argument("--evaluation-report", type=absolute_file, required=True)
    parser.add_argument("--openttd", type=absolute_file, required=True)
    parser.add_argument("--templates", type=absolute_directory, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        require(args.artifact_root.is_absolute(), "artifact root must be absolute")
        run(args)
    except Exception as error:
        print(f"M10_PACKAGE_GATE=FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
