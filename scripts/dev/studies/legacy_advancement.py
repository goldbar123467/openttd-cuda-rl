"""Recompute the retained nine-game entropy study's original advancement rule.

This is an offline migration of the retained experiment.py decision, not a new
selection protocol. Its training-map probe and mixed historical guide controls
are explicitly preserved; prospective studies must use the new full-map protocol.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local import capture_source, source_identity, write_json
from service_v2 import summarize

METRICS = ("passengers", "operating_profit", "cash_result_excluding_financing")


def aggregate(cases):
    return {**{"mean_" + key: statistics.mean(c["summary"][key] for c in cases) for key in METRICS},
            "episodes": len(cases),
            "sustained_service": sum(c["summary"]["service_in_all_final_three_windows"] for c in cases),
            "invalid_actions": sum(c["summary"]["invalid_actions"] for c in cases),
            "bankruptcies": sum(c["summary"]["bankruptcy"] for c in cases)}


def decide(cases, candidate, controls, maps, seeds, training_map):
    if len(maps) != 2 or len(set(maps)) != 2 or len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError("Historical rule requires two maps and three action seeds")
    if len(set(controls)) != len(controls) or "uniform" not in controls or candidate in controls:
        raise ValueError("Duplicate or missing historical controls")
    expected = {(name, "development", "sampled", s, m) for name in [candidate, *controls] for s in seeds for m in maps}
    expected |= {(candidate, "development", "greedy", seeds[0], m) for m in maps}
    expected.add((candidate, "training", "greedy", seeds[0], training_map))
    keys = [(c["controller"], c["split"], c["mode"], c["sampling_seed"], c["map_seed"]) for c in cases]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("Missing, duplicate or unregistered study case")
    for case in cases:
        if case["execution_status"] not in ("passed", "failed"):
            raise ValueError("Unknown case execution status")
        if case["execution_status"] == "passed":
            summary = case["summary"]
            if summary["decisions"] != 512 or any(not math.isfinite(summary[key]) for key in METRICS):
                raise ValueError("Completed case is partial or nonfinite")
        elif case["controller"] != candidate:
            raise ValueError("Historical rule requires complete retained controls")
    groups = {name: [c for c in cases if c["controller"] == name and c["mode"] == "sampled"]
              for name in [candidate, *controls]}
    groups["development-greedy"] = [c for c in cases if c["controller"] == candidate and c["split"] == "development" and c["mode"] == "greedy"]
    groups["training-greedy"] = [c for c in cases if c["controller"] == candidate and c["split"] == "training"]
    summaries = {name: aggregate(group) for name, group in groups.items() if all(c["execution_status"] == "passed" for c in group)}
    new_cases = [c for c in cases if c["controller"] == candidate]
    checks = {"all_nine_complete": len(new_cases) == 9 and all(c["execution_status"] == "passed" for c in new_cases)}
    paired = {}
    if checks["all_nine_complete"]:
        for label, count in ((candidate, 6), ("development-greedy", 2), ("training-greedy", 1)):
            summary = summaries[label]
            checks[label + "_service"] = summary["sustained_service"] == count
            checks[label + "_zero_invalid_bankrupt"] = summary["invalid_actions"] == summary["bankruptcies"] == 0
        for ref in controls:
            paired[ref] = {}
            for metric in METRICS:
                differences = [statistics.mean(c["summary"][metric] for c in groups[candidate] if c["sampling_seed"] == s)
                               - statistics.mean(c["summary"][metric] for c in groups[ref] if c["sampling_seed"] == s) for s in seeds]
                mean = statistics.mean(differences)
                # Preserve the original df=2 interval, including its arithmetic.
                margin = math.sqrt(2 * .95**2 / (1 - .95**2)) * statistics.stdev(differences) / math.sqrt(3)
                paired[ref][metric] = {"seed_differences": differences, "mean": mean,
                                      "approximate_95_percent_t_interval": [mean - margin, mean + margin]}
                if ref != "uniform":
                    checks[f"{metric}_at_least_{ref}"] = mean >= 0
                elif metric != "passengers":
                    checks[f"{metric}_exceeds_uniform"] = mean > 0
    return {"summaries": summaries, "paired_differences": paired, "checks": checks,
            "advance_to_replication": all(checks.values())}


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    capture_source(output / "source")
    report = {"status": "running", "source": source_identity(), "inputs_sha256": {},
              "claim": "Reproduce the historical registered decision, not validate its mixed-guide controls or infer generalization"}
    inputs = report["inputs_sha256"]
    def read(path):
        path = path.resolve()
        if not path.exists() and path.suffix == ".jsonl":
            path = Path(str(path) + ".gz")
        data = path.read_bytes()
        inputs[str(path)] = hashlib.sha256(data).hexdigest()
        return gzip.decompress(data) if path.suffix == ".gz" else data
    try:
        root = args.study.resolve()
        registration_bytes = read(root / "registration.json")
        registration = json.loads(registration_bytes)
        previous = json.loads(read(root / "comparison.json"))
        if previous["status"] != "completed" or not previous["all_scheduled_evaluations_finished"]:
            raise ValueError("Study has unfinished scheduled cases")
        if hashlib.sha256(registration_bytes).hexdigest() != previous["registration_sha256"]:
            raise ValueError("Study registration changed")
        if hashlib.sha256(read(root / "orchestrator.py")).hexdigest() != registration["orchestrator_sha256"]:
            raise ValueError("Historical driver changed")
        # The original nine-game training probe is textual in this registration.
        # Refuse unrelated registrations instead of guessing another map/rule.
        if registration["evaluation"]["cases"] != "Two greedy and six sampled development cases plus one greedy training-map case 1871197196":
            raise ValueError("Unsupported legacy evaluation registration")
        cases = []
        guide_versions = {}
        for case in previous["cases"]:
            if case["execution_status"] != "passed":
                cases.append(case)
                continue
            path = Path(case["case"])
            run_bytes, trace_bytes = read(path / "run.json"), read(path / "worker/transitions.jsonl")
            if hashlib.sha256(run_bytes).hexdigest() != case["run_sha256"] or hashlib.sha256(trace_bytes).hexdigest() != case["trace_sha256"]:
                raise ValueError("Historical case input hash changed")
            run, reset = json.loads(run_bytes), json.loads(read(path / "worker/reset.json"))
            trace = [json.loads(line) for line in trace_bytes.splitlines()]
            if (reset["split"] != case["split"] or reset["map_seed"] != case["map_seed"] or
                    run["status"] not in ("completed", "passed") or len(trace) != 512 or
                    not (run["final_observation"]["terminal"] or run["final_observation"]["truncated"]) or
                    any(t["decision"] != i + 1 or t["tick_after"] - t["tick_before"] != 128 or
                        (i and t["tick_before"] != trace[i - 1]["tick_after"]) for i, t in enumerate(trace))):
                raise ValueError("Historical case split/budget/clock invalid")
            summary = summarize(trace, {"economy": trace[0]["before"], "tick": trace[0]["tick_before"]}, run["final_observation"])
            if summary != case["summary"]:
                raise ValueError("Independent native economics differ")
            guide_versions.setdefault(case["controller"], set()).add(run["guidance"])
            cases.append({**case, "summary": summary})
        result = decide(cases, args.candidate, registration["controls"], registration["evaluation"]["development_maps"],
                        registration["evaluation"]["action_seeds"], 1871197196)
        for key, value in result.items():
            if value != previous[key]:
                raise ValueError("Recomputed historical decision differs: " + key)
        # Ensure inputs remained stable during this read-only report.
        if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha for path, sha in inputs.items()):
            raise ValueError("Study inputs changed during audit")
        report.update(status="passed", cases=len(cases), **result,
                      observed_guide_versions={k: sorted(v) for k, v in guide_versions.items()})
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "verification.json", report)
    print(json.dumps({"status": report["status"], "cases": report["cases"], "advance_to_replication": report["advance_to_replication"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
