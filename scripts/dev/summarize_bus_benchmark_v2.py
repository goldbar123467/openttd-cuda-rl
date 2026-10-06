#!/usr/bin/env python3
"""Verify paired native evidence and summarize frozen human-imitation benchmarks."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random
import statistics

from audit_action_inputs_v2 import artifact, checked
from local import capture_source, source_identity, write_json
from run_bus_orders_benchmark_v2 import reuse_case
from service_v2 import summarize
from evaluate_bus_orders_campaign_v2 import MODE, unsupported_order_state

MODELS = ("one-game-1000", "one-game-256", "four-game-256", "seven-game-256")
METRICS = ("passengers", "operating_profit", "cash_result_excluding_financing", "cash_result_before_capital")


def read(path):
    return json.loads(Path(path).read_text())


def csv_file(path, rows):
    if not rows:
        raise ValueError("Cannot export an empty comparison")
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def verify_episode(item, context, model, protocol, policy=None):
    path = Path(checked(item["report"])["path"])
    checked_item = reuse_case(path, item["case"], context, model, protocol["decisions"], protocol["step_ticks"],
                             allow_interface_limit=item.get("outcome") == "terminated-interface", engine=protocol["engine"], policy=policy)
    if checked_item != item:
        raise ValueError("Campaign summary differs from its native episode report")
    report = read(path)
    initial, final = read(path.parent / "initial.json"), read(path.parent / "final.json")
    if item.get("outcome") == "terminated-interface" and (report["interface_limit"] != unsupported_order_state(final)
            or not model or report["summary"]["decisions"] >= protocol["decisions"]):
        raise ValueError("Interface termination lacks the actual unsupported final state")
    expected = read(checked(context["initial"])["path"])
    for key in ("economy", "vehicles", "stations", "depots", "tick", "token"):
        if initial[key] != expected[key]:
            raise ValueError("Initial state differs across paired actors")
    if initial["map"]["roads"] != expected["map"]["roads"]:
        raise ValueError("Initial road layout differs across paired actors")
    transitions = [json.loads(line) for line in (path.parent / "worker/transitions.jsonl").read_text().splitlines()]
    previous_tick, previous_token, previous_economy = initial["tick"], initial["token"], initial["economy"]
    for index, row in enumerate(transitions, 1):
        if (row["decision"] != index or row["tick_before"] != previous_tick or row["state_before"] != previous_token
                or row["before"] != previous_economy or row["company_id"] != initial["company_id"]
                or row["tick_after"] - row["tick_before"] != protocol["step_ticks"]
                or row["action"]["status"] not in ("SUCCESS", "NO_OP")):
            raise ValueError("Native transition identity/accounting chain differs")
        previous_tick, previous_token, previous_economy = row["tick_after"], row["state_after"], row["after"]
    if (previous_tick != final["tick"] or previous_token != final["token"] or previous_economy != final["economy"]
            or summarize(transitions, initial, final) != report["summary"]):
        raise ValueError("Final state or recomputed native financial summary differs")
    decisions = [json.loads(line) for line in (path.parent / "decisions.jsonl").read_text().splitlines()]
    if len(decisions) != len(transitions):
        raise ValueError("Decision/transition evidence counts differ")
    for decision, row in zip(decisions, transitions):
        if (decision["decision"] != row["decision"] or decision["candidate"]["key"] != row["action"]["candidate"]
                or decision["tick"] != row["tick_before"]):
            raise ValueError("Chosen public candidate differs from executed native action")
        if model and (decision["prediction"]["row"] not in decision["prediction"]["legal_rows"]
                      or not 0 <= decision["prediction"]["selected_probability"] <= 1):
            raise ValueError("Executed neural choice differs from exact legal mask")
    routes = sum(not bus["stopped"] and len(bus["orders"]) == 2
                 and len({order["destination"] for order in bus["orders"]}) == 2
                 and all(order["load_mode"] == 3 for order in bus["orders"]) for bus in final["vehicles"])
    if routes != report["valid_running_routes"]:
        raise ValueError("Final route count differs")
    return {"report": artifact(path), "initial": artifact(path.parent / "initial.json"),
            "reset": artifact(path.parent / "worker/reset.json"),
            "final": artifact(path.parent / "final.json"),
            "transitions": artifact(path.parent / "worker/transitions.jsonl"),
            "decisions": artifact(path.parent / "decisions.jsonl"), "verified_decisions": len(transitions)}


def verify_offline_models(offline, protocol, policy):
    if set(offline["models"]) != set(protocol["frozen_actors"]) or offline["financial_features"] != MODE:
        raise ValueError("Offline actors or reader mode differ from the frozen comparison")
    if checked(offline["policy"]) != checked(policy):
        raise ValueError("Offline policy reader differs from the live executable")
    for actor, frozen in protocol["frozen_actors"].items():
        scored = offline["models"][actor]
        expected_run = {"path": str(Path(frozen["run"]) / "run.json"), "sha256": frozen["run_sha256"]}
        if checked(scored["model"]) != checked(frozen["model"]) or checked(scored["run"]) != checked(expected_run):
            raise ValueError("Offline model/run differs from the frozen gameplay actor")
    if {row["model"] for row in offline["results"]} != set(protocol["frozen_actors"]) or len(offline["results"]) != len(protocol["frozen_actors"]):
        raise ValueError("Offline result actors repeat or differ")


def percentile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = int(index)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (index - lower)


def clustered_difference(rows, metric, *, repeats=5000, seed=20261005):
    """Resample map seeds, retaining every paired dimension/mode within a seed."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["map_seed"]].append(row[metric])
    keys = sorted(groups)
    if len(keys) < 2:
        raise ValueError("Uncertainty requires multiple independent seed clusters")
    generator = random.Random(seed)
    replicates = []
    for _ in range(repeats):
        draws = generator.choices(keys, k=len(keys))
        values = [value for key in draws for value in groups[key]]
        replicates.append(statistics.mean(values))
    return {"paired_mean_difference": statistics.mean(row[metric] for row in rows),
            "cluster_bootstrap_95_percent_interval": [percentile(replicates, .025), percentile(replicates, .975)],
            "paired_cases": len(rows), "independent_map_seed_clusters": len(keys), "repeats": repeats, "bootstrap_seed": seed}


def live_summary(rows):
    return {"episodes": len(rows), "completed_full_budget": sum(row["decisions"] == 512 for row in rows),
            "any_delivery": sum(row["passengers"] > 0 for row in rows),
            "positive_operating_profit": sum(row["operating_profit"] > 0 for row in rows),
            "positive_cash_after_capital": sum(row["cash_result_excluding_financing"] > 0 for row in rows),
            "sustained_service": sum(row["service_in_all_final_three_windows"] for row in rows),
            "sustained_positive_cash_service": sum(row["positive_cash_service_in_all_final_three_windows"] for row in rows),
            "any_valid_running_route": sum(row["valid_running_routes"] > 0 for row in rows),
            "bankruptcies": sum(row["bankruptcy"] for row in rows),
            "invalid_actions": sum(row["invalid_actions"] for row in rows),
            "interface_terminations": sum(row["outcome"] == "terminated-interface" for row in rows),
            "mean_buses": statistics.mean(row["buses"] for row in rows),
            **{f"mean_{key}": statistics.mean(row[key] for row in rows) for key in METRICS}}


def prefix_metrics(row, count):
    """Compare finances/cargo over identical simulated horizons, including failures."""
    root = Path(row["report_path"]).parent
    initial = read(root / "initial.json")
    final = read(root / "final.json")
    transitions = [json.loads(line) for line in (root / "worker/transitions.jsonl").read_text().splitlines()][:count]
    if len(transitions) != count or not count:
        raise ValueError("Paired prefix has missing native decisions")
    partial = {**final, "tick": transitions[-1]["tick_after"], "economy": transitions[-1]["after"],
               "terminal": transitions[-1]["terminal"]}
    values = summarize(transitions, initial, partial)
    return {key: values[key] for key in METRICS}


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol_ref, offline_ref, batch_ref = [artifact(path) for path in (args.protocol, args.offline, args.batch)]
    protocol, offline, batch = [read(ref["path"]) for ref in (protocol_ref, offline_ref, batch_ref)]
    if offline["status"] != "completed" or not offline["inputs_unchanged"] or batch["status"] != "completed":
        raise ValueError("Comparison inputs are unfinished or failed")
    if checked(batch["protocol"]) != checked(protocol_ref):
        raise ValueError("Live campaign used another protocol")
    verify_offline_models(offline, protocol, batch["policy"])
    training_protocol = artifact(args.protocol.parent / "training-protocol.json")
    if training_protocol["sha256"] != protocol["training_protocol_sha256"]:
        raise ValueError("Frozen training protocol changed")
    new_run_ref = artifact(Path(protocol["frozen_actors"]["seven-game-256"]["run"]) / "run.json")
    new_run = read(new_run_ref["path"])
    record = {"status": "running", "source": source_identity(), "protocol": protocol_ref,
              "offline_report": offline_ref, "batch_report": batch_ref, "policy": checked(batch["policy"]), "training_run": False,
              "training_protocol": training_protocol, "training_report": new_run_ref,
              "training": {"elapsed_seconds": new_run["elapsed_seconds"],
                           **{key: value for key, value in new_run["result"].items() if key not in ("initial", "final")},
                           "initial": {key: value for key, value in new_run["result"]["initial"].items() if key != "examples"},
                           "final": {key: value for key, value in new_run["result"]["final"].items() if key != "examples"}},
              "offline": {}, "gameplay": {}, "paired": {}, "scripted_comparisons": {}, "native_verification": []}
    try:
        record["source_capture"] = capture_source(output / "source-provenance")
        if args.choice_diagnostics or args.insertion_structure or args.insertion_run:
            if not (args.choice_diagnostics and args.insertion_structure and args.insertion_run):
                raise ValueError("Supply every requested insertion diagnostic for the evidence package")
            choice_ref, structure_ref = artifact(args.choice_diagnostics), artifact(args.insertion_structure)
            choices, structure = read(choice_ref["path"]), read(structure_ref["path"])
            if choices["status"] != "completed" or structure["status"] != "completed" or structure["summary"]["examples"] != 43:
                raise ValueError("Requested input diagnostics are unfinished")
            trials = []
            for path in args.insertion_run:
                reference = artifact(path)
                trial = read(reference["path"])
                if (trial["status"] != "completed" or trial["examples"] != 43
                        or trial["kind"] != "native-human-insertion-memorization-diagnostic"
                        or checked(trial["source_training_run"]) != checked(new_run_ref)):
                    raise ValueError("Insertion-only trial did not use the frozen training corpus")
                trials.append({"report": reference, "epochs": trial["epochs"], "examples": 43,
                               "elapsed_seconds": trial["elapsed_seconds"], "final_loss": trial["result"]["final"]["loss"],
                               "unique_exact": trial["permutation_audit"]["unique_exact"],
                               "permuted_unique_exact": trial["permutation_audit"]["permuted_unique_exact"],
                               "permutation_max_probability_error": trial["permutation_audit"]["maximum_probability_error"],
                               "finite_gradients": trial["result"]["finite_gradients"],
                               "exact_legal_masks": trial["result"]["exact_legal_masks"],
                               "model": checked(trial["model"])})
            record["diagnostics"] = {"choices": choice_ref, "choice_summary": choices["summary"],
                                     "insertion_structure": structure_ref, "insertion_structure_summary": structure["summary"],
                                     "insertion_trials": trials}
        offline_rows, operations = [], []
        for result in offline["results"]:
            model = result["model"]
            summaries = {}
            for corpus, data in result["corpora"].items():
                summary = data["summary"]
                summaries[corpus] = summary
                offline_rows.append({"model": model, "corpus": corpus, **summary["overall"],
                                     "permutation_max_probability_error": summary["permutation_max_probability_error"]})
                for operation, metrics in summary["by_operation"].items():
                    operations.append({"model": model, "corpus": corpus, "operation": operation, **metrics})
            test_count = sum(summaries[key]["overall"]["examples"] for key in ("test-nine", "test-ten"))
            test_exact = sum(summaries[key]["overall"]["unique_exact_rows"] for key in ("test-nine", "test-ten"))
            record["offline"][model] = {"corpora": summaries, "combined_test": {"exact": test_exact, "total": test_count,
                                                                         "accuracy": test_exact / test_count}}
        csv_file(output / "offline.csv", offline_rows)
        csv_file(output / "offline-operations.csv", operations)
        cases = {case["case_id"]: case for case in protocol["cases"]}
        if set(batch["actors"]) != set(protocol["frozen_actors"]) | {protocol["scripted_actor"]}:
            raise ValueError("Live actors differ from the planned comparison")
        rows, evidence = [], []
        for actor, data in batch["actors"].items():
            if data["status"] != "completed" or len(data["episodes"]) != len(cases):
                raise ValueError("Actor has missing episodes")
            if {item["case"]["case_id"] for item in data["episodes"]} != cases.keys():
                raise ValueError("Actor case identities repeat or differ")
            model = checked(protocol["frozen_actors"][actor]["model"]) if actor in MODELS else None
            if data["model"] != model:
                raise ValueError("Actor weights differ from the frozen model")
            for item in data["episodes"]:
                case = item["case"]
                if case != cases[case["case_id"]]:
                    raise ValueError("Episode seed/mode/world differs")
                context = protocol["contexts"][case["world_id"] - 1]
                proof = verify_episode(item, context, model, protocol, batch["policy"])
                evidence.append({"actor": actor, "case_id": case["case_id"], **proof})
                summary = item["summary"]
                final = read(proof["final"]["path"])
                rows.append({"actor": actor, "case_id": case["case_id"], "world_id": case["world_id"], "mode": case["mode"],
                             "map_seed": case["world"]["seed"], "width": case["world"]["width"], "height": case["world"]["height"],
                             "outcome": item.get("outcome", "completed"), "report_path": proof["report"]["path"],
                             **{key: value for key, value in summary.items() if key not in ("windows", "action_counts")},
                             "valid_running_routes": item["valid_running_routes"], "final_cash": final["economy"]["balance"],
                             "final_loan": final["economy"]["loan"], "final_save": item["final_save"]["path"],
                             "final_save_sha256": item["final_save"]["sha256"],
                             **{f"actions_{family}": summary["action_counts"].get(family, 0) for family in
                                ("WAIT", "BUY_BUS", "SET_ROUTE", "START_VEHICLE", "MANAGE_LOAN", "SELL_VEHICLE")}})
            record["gameplay"][actor] = {mode: live_summary([row for row in rows if row["actor"] == actor and row["mode"] == mode])
                                        for mode in ("greedy", "sampled")}
            record["gameplay"][actor]["all"] = live_summary([row for row in rows if row["actor"] == actor])
            print(json.dumps({"actor_verified": actor, "episodes": 50}), flush=True)
        csv_file(output / "gameplay.csv", rows)
        record["native_verification"] = evidence
        by_case = {(row["actor"], row["case_id"]): row for row in rows}
        paired_rows = []
        for comparison in (*MODELS[:-1], protocol["scripted_actor"]):
            for mode in ("greedy", "sampled", "all"):
                paired = []
                for case in cases.values():
                    if mode != "all" and case["mode"] != mode:
                        continue
                    new, old = by_case[("seven-game-256", case["case_id"])], by_case[(comparison, case["case_id"])]
                    count = min(new["decisions"], old["decisions"])
                    new_metrics, old_metrics = prefix_metrics(new, count), prefix_metrics(old, count)
                    row = {"comparison": comparison, "mode": case["mode"], "case_id": case["case_id"],
                           "map_seed": case["world"]["seed"], "matched_decisions": count,
                           **{metric: new_metrics[metric] - old_metrics[metric] for metric in METRICS}}
                    paired.append(row)
                    if mode == "all":
                        paired_rows.append(row)
                record["paired"][comparison + ":" + mode] = {metric: clustered_difference(paired, metric) for metric in METRICS}
        csv_file(output / "paired-differences.csv", paired_rows)
        scripted_pairs = []
        for actor in MODELS:
            for mode in ("greedy", "sampled", "all"):
                paired = []
                for case in cases.values():
                    if mode != "all" and case["mode"] != mode:
                        continue
                    neural = by_case[(actor, case["case_id"])]
                    baseline = by_case[(protocol["scripted_actor"], case["case_id"])]
                    count = min(neural["decisions"], baseline["decisions"])
                    neural_metrics, baseline_metrics = prefix_metrics(neural, count), prefix_metrics(baseline, count)
                    row = {"actor": actor, "mode": case["mode"], "case_id": case["case_id"],
                           "map_seed": case["world"]["seed"], "matched_decisions": count,
                           **{metric: neural_metrics[metric] - baseline_metrics[metric] for metric in METRICS}}
                    paired.append(row)
                    if mode == "all":
                        scripted_pairs.append(row)
                record["scripted_comparisons"][actor + ":" + mode] = {metric: clustered_difference(paired, metric) for metric in METRICS}
        csv_file(output / "scripted-paired-differences.csv", scripted_pairs)
        record["verification"] = {"episodes": len(rows), "decisions": sum(row["decisions"] for row in rows),
                                  "simulation_ticks": sum(row["simulation_ticks"] for row in rows),
                                  "final_saves": len(rows), "immutable_inputs_unchanged": True,
                                  "full_budget_episodes": sum(row["decisions"] == protocol["decisions"] for row in rows),
                                  "interface_terminations": sum(row["outcome"] == "terminated-interface" for row in rows),
                                  "native_accounting_chains": "passed", "training_updates_during_evaluation": 0}
        for reference in (protocol_ref, offline_ref, batch_ref, protocol["engine"], batch["policy"]):
            checked(reference)
        for model in protocol["frozen_actors"].values():
            checked(model["model"])
            if artifact(Path(model["run"]) / "run.json")["sha256"] != model["run_sha256"]:
                raise ValueError("Frozen training report changed")
        checked(training_protocol)
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "results.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--offline", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--choice-diagnostics", type=Path)
    parser.add_argument("--insertion-structure", type=Path)
    parser.add_argument("--insertion-run", type=Path, action="append", default=[])
    run(parser.parse_args())
