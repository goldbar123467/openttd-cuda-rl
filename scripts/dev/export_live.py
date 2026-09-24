#!/usr/bin/env python3
"""Export a locally trained MLP and verify the native ONNX inference boundary."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import onnx
import onnxruntime
import onnxscript
import torch

from local import ROOT, capture_source, source_identity, write_json
sys.path.insert(0, str(ROOT / "scripts/v1"))
from m10_export_model import model_for, graph_shape, M10_COMPATIBILITY
from m09_evaluator_client import EvaluatorClient
from m10_deployment_client import DeploymentClient


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def live_cases(root, package_id):
    record = json.loads((root / "run.json").read_text())
    require(record["status"] == "completed", "Full development evaluation must be completed")
    require(Path(record["package"]).name == package_id, "Development evaluation belongs to another model")
    cases = []
    for summary_path in sorted(root.rglob("episode.json")):
        summary = json.loads(summary_path.read_text())
        require(summary["status"] == "completed", "Incomplete evaluation episode")
        require(summary["template_id"] in {"m02-template-05", "m02-template-06"}, "Only development maps are accepted")
        rows = [json.loads(line) for line in (summary_path.parent / "actions.jsonl").read_text().splitlines()]
        for index in (0, 1, 2, 3, 4, 5, 6, 7, 8, 16, 32, 64, 128, 256, 384, 511):
            if index < len(rows):
                row = rows[index]
                cases.append({"case_id": f"{summary_path.parent.name}-s{index}", "source": "development-live-structured",
                              "structured": row["structured_before"], "spatial": [0.] * 32768,
                              "legal_mask": row["legal"]})
    require(cases, "No development observations were found")
    return cases


def compare(expected, actual, tolerance):
    errors = {}
    for field, rule in (("logits", "policy_logits"), ("probabilities", "masked_probabilities"), ("value", "value")):
        a, b = np.asarray(getattr(expected, field)), np.asarray(getattr(actual, field))
        limit = tolerance[rule]
        require(np.isfinite(b).all() and np.all(np.abs(a - b) <= limit["absolute"] + limit["relative"] * np.abs(a)),
                f"Native/ONNX {field} exceeded the existing M10 tolerance")
        errors[field] = float(np.max(np.abs(a - b)))
    require(expected.action == actual.action, "ONNX greedy action differs from native policy")
    return errors


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = args.package.resolve()
    manifest_bytes = (source / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    record = {"kind": "development-onnx-export", "status": "running", "source": source_identity(),
              "source_package": str(source), "source_model_sha256": digest(source / "model.pt"),
              "exporter": {"torch": torch.__version__, "onnx": onnx.__version__, "onnxscript": onnxscript.__version__},
              "runtime": onnxruntime.__version__, "claim": "local development export; not the historical M10 release gate"}
    write_json(output / "export.json", record)
    clients = []
    try:
        capture_source(output / "source")
        require(hashlib.sha256(manifest_bytes).hexdigest() == source.name, "Native source manifest identity differs")
        require(manifest["model_sha256"] == record["source_model_sha256"], "Native source weights digest differs")
        require(manifest["architecture"] == "structured-mlp-v1", "This first development export supports the structured MLP")
        require(onnxruntime.__version__ == "1.28.0", "Existing native deployment requires ONNX Runtime 1.28.0")
        contract = json.loads((ROOT / "config/v1/m10-model-package-contract.json").read_text())
        registered = next(x for x in contract["models"] if x["architecture_id"] == manifest["architecture"])
        archived = torch.jit.load(str(source / "model.pt"), map_location="cpu")
        state = archived.state_dict()
        model, examples, input_names, dynamic_shapes = model_for(manifest["architecture"])
        model.load_state_dict(state, strict=True)
        model.eval()
        for name in ("model.onnx", "model-repeat.onnx"):
            torch.onnx.export(model, examples, str(output / name), input_names=input_names,
                              output_names=["policy_logits", "value"], opset_version=18,
                              dynamo=True, external_data=False, dynamic_shapes=dynamic_shapes)
        require((output / "model.onnx").read_bytes() == (output / "model-repeat.onnx").read_bytes(), "Repeat exports differ")
        graph = onnx.load(output / "model.onnx", load_external_data=False)
        onnx.checker.check_model(graph, full_check=True)
        require([(x.domain, x.version) for x in graph.opset_import] == [("", 18)], "ONNX opset differs")
        require([{"name": x.name, "dtype": "float32", "shape": graph_shape(x)} for x in graph.graph.input] == registered["inputs"], "ONNX input signature differs")
        require([{"name": x.name, "dtype": "float32", "shape": graph_shape(x)} for x in graph.graph.output] == contract["graph"]["outputs"], "ONNX output signature differs")
        initializers = {x.name: onnx.numpy_helper.to_array(x) for x in graph.graph.initializer}
        require(all(name in initializers and np.array_equal(initializers[name], value.numpy()) for name, value in state.items()),
                "ONNX weights differ from the native source")
        require(not any(x.op_type in {"Dropout", "Gradient", "Momentum", "Adam", "Adagrad"} or
                        x.domain.startswith("ai.onnx.preview.training") for x in graph.graph.node), "Training node in ONNX graph")
        cases = live_cases(args.evaluation.resolve(), source.name)
        reference = EvaluatorClient.start(args.evaluator.resolve(), package=source, sampling_seed=20260923)
        clients.append(reference)
        expected = []
        for offset in range(0, len(cases), 32):
            batch = cases[offset:offset + 32]
            expected.extend(reference.inspect([x["structured"] for x in batch], [x["spatial"] for x in batch],
                                               [x["legal_mask"] for x in batch], deterministic=True))
        stage = output / "package-stage"
        stage.mkdir()
        shutil.copyfile(output / "model.onnx", stage / "model.onnx")
        with (stage / "golden.jsonl").open("wb") as stream:
            for case, prediction in zip(cases, expected, strict=True):
                stream.write(canonical(case | {"native_prediction": dataclasses.asdict(prediction)}) + b"\n")
        evaluation = {"kind": "development-full-episodes", "held_out": False, "status": "completed",
                      "path": str(args.evaluation.resolve()), "run_sha256": digest(args.evaluation / "run.json")}
        (stage / "evaluation.json").write_bytes(canonical(evaluation) + b"\n")
        (stage / "INSTALL.md").write_text("Development policy package. Use only the development native playback build and development maps.\n"
                                         "The structured MLP ignores spatial input; golden spatial arrays are unused zero placeholders.\n")
        package = {"format": contract["package"]["format"], "compatibility_version": 1,
                   "architecture": {"architecture_id": manifest["architecture"], "architecture_version": 1,
                                    "definition_sha256": contract["compatibility"]["architecture"]},
                   "inputs": registered["inputs"], "outputs": contract["graph"]["outputs"],
                   "normalization": "none-frozen-m04-preprocessing", "recurrent_state": "none-v1-feed-forward",
                   "compatibility": {"observation_sha256": contract["compatibility"]["observation"],
                       "action_sha256": contract["compatibility"]["action_and_mask"], "mask_sha256": contract["compatibility"]["action_and_mask"],
                       "reward_sha256": contract["compatibility"]["reward_trajectory"], "m09_sha256": contract["compatibility"]["evaluation"],
                       "m10_sha256": M10_COMPATIBILITY, "onnx_opset": 18, "onnxruntime_version": "1.28.0",
                       "openttd_upstream_commit": "29f808ef0022064e6d9a83c8476d1e0f4686af86", "environment_version": "openttd-rl-v1-m06-environment-1"},
                   "provenance": {"kind": "development", "source_package_id": source.name,
                                  "source_model_sha256": manifest["model_sha256"], "source": record["source"], "exporter": record["exporter"]},
                   "seeds": {"training_seed": manifest["run_seed"]}, "evaluation": evaluation,
                   "files": {name: digest(stage / name) for name in contract["package"]["payload_files"]},
                   "installation": {"training_dependencies": False, "atomic": True}}
        package_id = hashlib.sha256(canonical(package)).hexdigest()
        package["package_id"] = package_id
        (stage / "manifest.json").write_bytes(canonical(package))
        destination = output / package_id
        stage.rename(destination)
        maximum = {key: 0. for key in ("logits", "probabilities", "value")}
        for mode in ("standalone", "ingame"):
            deployed = DeploymentClient.start(args.deployment_evaluator.resolve(), package=destination, sampling_seed=20260923, mode=mode)
            clients.append(deployed)
            for offset in range(0, len(cases), 32):
                batch = cases[offset:offset + 32]
                actual = deployed.inspect([x["structured"] for x in batch], [x["spatial"] for x in batch],
                                          [x["legal_mask"] for x in batch], deterministic=True)
                for old, new in zip(expected[offset:offset + 32], actual, strict=True):
                    for key, error in compare(old, new, contract["tolerances"]).items():
                        maximum[key] = max(maximum[key], error)
            deployed.close()
            clients.remove(deployed)
        reference.close()
        clients.remove(reference)
        require((source / "manifest.json").read_bytes() == manifest_bytes and digest(source / "model.pt") == record["source_model_sha256"], "Export changed native source")
        record.update(status="passed", package=str(destination), package_id=package_id, cases=len(cases),
                      maximum_absolute_errors=maximum, greedy_actions_exact=True, repeat_export_byte_identical=True,
                      deployment_evaluator_sha256=digest(args.deployment_evaluator), native_evaluator_sha256=digest(args.evaluator))
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        for client in clients:
            try:
                client.abort()
            except Exception as exc:
                record.setdefault("cleanup_errors", []).append(str(exc))
        write_json(output / "export.json", record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("package", "evaluation", "evaluator", "deployment-evaluator", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    run(parser.parse_args())
