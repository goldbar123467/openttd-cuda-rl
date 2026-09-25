"""Reproduce retained V1 t intervals and V2 native summaries with richer reports."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local import capture_source, source_identity, write_json
import report_learning
import report_v2_learning
import report_credit_experiment
from studies.evidence_v2 import Inputs


def verify_credit(path, root, inputs):
    old = inputs.json(path)
    arguments = {"reference": [], "candidate": [], "default_equivalence": [], "axis": old["axis"],
                 "output": root / "credit", "bootstrap_iterations": 10000}
    for name, expected in old["input_sha256"].items():
        source = Path(name)
        data = inputs.json(source)
        if inputs.sha256[str(source.resolve())] != expected:
            raise ValueError("Retained credit-study input changed")
        if source.name == "verification.json":
            arguments["default_equivalence"].append(source)
        elif "episodes" in data:
            policies = {r["policy"] for r in data["episodes"]}
            if {"wait", "random", "scripted"} <= policies:
                # Historical baseline batches also contain neural smoke cases
                # and therefore a package; they are not a study model arm.
                arguments["baseline"] = source.parent
            elif policies == {"one-bus"}:
                arguments["one_bus"] = source.parent
            elif policies == {"greedy", "sampled"} and data.get("package"):
                _, training = report_credit_experiment.training_for(data)
                settings = report_credit_experiment.settings(training)
                label = next((k for k in ("reference", "candidate") if settings == old["matched_settings"][0][k]), None)
                if label is None:
                    raise ValueError("Credit study input does not match either registered configuration")
                arguments[label].append(source.parent)
            else:
                raise ValueError("Unrecognized retained credit evaluation role")
    with (root / "credit.log").open("x") as log, contextlib.redirect_stdout(log):
        report_credit_experiment.run(SimpleNamespace(**arguments))
    new = inputs.json(root / "credit/comparison.json")
    checks = {}
    for key in ("summaries", "paired_differences", "matched_settings"):
        checks["credit_exact_" + key] = new[key] == old[key]
        if not checks["credit_exact_" + key]:
            raise ValueError("Historical credit report changed: " + key)
    return checks


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    record = {"status": "running", "source": source_identity(), "checks": {}}
    inputs = Inputs()
    try:
        old = inputs.json(args.v1_comparison)
        paths = list(map(Path, old["inputs"]))
        if len(paths) != 8 or "paired_training_seed_differences" not in old:
            raise ValueError("Migration check requires the original matched three-seed V1 comparison")
        with (root / "v1.log").open("x") as log, contextlib.redirect_stdout(log):
            report_learning.run(SimpleNamespace(baseline=paths[0], one_bus=paths[1], old_policy=paths[2:5],
                                                new_policy=paths[5:8], output=root / "v1", bootstrap_iterations=10000))
        new = inputs.json(root / "v1/comparison.json")
        for key in ("summaries", "training_seed_statistics", "paired_training_seed_differences"):
            record["checks"]["v1_exact_" + key] = new[key] == old[key]
            if not record["checks"]["v1_exact_" + key]:
                raise ValueError("Historical V1 output changed: " + key)
        before, after = old["matched_training_except_reward"], new["matched_training_except_reward"]
        if any(after.get(k) != v for k, v in before.items()):
            raise ValueError("Historical matched training setting changed")
        record["additional_explicit_v1_settings"] = {k: v for k, v in after.items() if k not in before}
        if getattr(args, "credit_comparison", None):
            record["checks"].update(verify_credit(args.credit_comparison, root, inputs))
        study = inputs.json(args.v2_comparison)
        cases = [c for c in study["cases"] if c["controller"] in (args.candidate, "uniform") and c["split"] == "development"]
        if not cases or any(c["execution_status"] != "passed" for c in cases):
            raise ValueError("Migration check needs completed retained candidate and uniform development cases")
        for case in cases:
            path = Path(case["case"])
            if (hashlib.sha256(inputs.read(path / "run.json")).hexdigest() != case["run_sha256"] or
                    hashlib.sha256(inputs.read(path / "worker/transitions.jsonl")).hexdigest() != case["trace_sha256"]):
                raise ValueError("Retained V2 case changed from the original study")
        with (root / "v2.log").open("x") as log, contextlib.redirect_stdout(log):
            report_v2_learning.run(SimpleNamespace(runs=[Path(c["case"]) for c in cases], output=root / "v2",
                                                   legacy_sampled_controls=True, bootstrap_iterations=10000))
        new2 = inputs.json(root / "v2/comparison.json")
        originals = {c["case"]: c["summary"] for c in cases}
        record["checks"]["v2_exact_native_summaries"] = all(e["summary"] == originals[e["source"]] for e in new2["episodes"])
        if not record["checks"]["v2_exact_native_summaries"]:
            raise ValueError("Historical V2 native summary changed")
        inputs.unchanged()
        record.update(status="passed", v1_episodes=sum(len(v) for v in new["episodes"].values()),
                      v2_episodes=len(new2["episodes"]), v2_unpaired=new2["unpaired_groups"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        record["inputs_sha256"] = inputs.sha256
        write_json(root / "verification.json", record)
    print(json.dumps({k: v for k, v in record.items() if k not in ("source", "inputs_sha256")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-comparison", type=Path, required=True)
    parser.add_argument("--v2-comparison", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--credit-comparison", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
