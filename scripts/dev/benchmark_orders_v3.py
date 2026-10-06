#!/usr/bin/env python3
"""Add one frozen v3 actor to the unchanged October 5 fifty-case protocol."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import statistics
import time

from audit_action_inputs_v2 import artifact, checked
from evaluate_bus_orders_campaign_v2 import episode
from imitation_warm_start_v2 import checked_imitation_run
from local import capture_source, source_identity, write_json
from run_bus_orders_benchmark_v2 import reuse_case
from summarize_bus_benchmark_v2 import verify_episode


def first_route_from_journal(path):
    first_id = None
    with path.open() as stream:
        for line in stream:
            entry = json.loads(line)
            state = entry.get("response", {}).get("observation")
            if not state:
                continue
            buses = state["vehicles"]
            if first_id is None and buses:
                first_id = min(bus["id"] for bus in buses)
            bus = next((bus for bus in buses if bus["id"] == first_id), None)
            if bus is not None and not bus["stopped"]:
                orders = bus["orders"]
                return {"vehicle_id": first_id, "started": True,
                        "valid": len(orders) == 2 and len({order["destination"] for order in orders}) == 2 and
                        all(order["load_mode"] == 3 for order in orders), "orders": orders}
    return {"vehicle_id": first_id, "started": False, "valid": False}


def execute(engine, policy, model, output, case, context, decisions):
    episode(engine, policy, model, output, case, context, decisions=decisions,
            verify_save=case["case_id"] in (1, 2), capture_interface_limit=True,
            financial_features="signed-log-orders-v3")
    return output / "run.json"


def grouped(items):
    result = {}
    for mode in ("greedy", "sampled"):
        rows = [item for item in items if item["case"]["mode"] == mode]
        profits = [item["summary"]["operating_profit"] for item in rows]
        result[mode] = {"attempts": len(rows), "full_budgets": sum(item["summary"]["decisions"] == 512 for item in rows),
                        "interface_terminations": sum(item.get("outcome") == "terminated-interface" for item in rows),
                        "first_bus_started": sum(item["first_route"]["started"] for item in rows),
                        "first_route_valid": sum(item["first_route"]["valid"] for item in rows),
                        "delivering_attempts": sum(item["summary"]["passengers"] > 0 for item in rows),
                        "mean_passengers": statistics.mean(item["summary"]["passengers"] for item in rows) if rows else None,
                        "mean_operating_profit": statistics.mean(profits) if rows else None,
                        "total_operating_profit": sum(profits),
                        "positive_operating_profit": sum(value > 0 for value in profits)}
    return result


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    protocol_ref, gate_ref = artifact(args.protocol), artifact(args.fit_audit)
    protocol, gate = [json.loads(Path(ref["path"]).read_text()) for ref in (protocol_ref, gate_ref)]
    imitation, _ = checked_imitation_run(args.imitation_run, observation_schema="v2-m15-public-development-orders-v1",
                                        financial_features="signed-log-orders-v3")
    model, policy = checked(imitation["model"]), artifact(args.policy)
    train = gate["corpora"]["training"]
    if (gate["status"] != "completed" or checked(gate["model"]) != model or
            train["adjacent_duplicate_predictions"] > 4 or train["insertion_states"] != 43):
        raise ValueError("The frozen v3 actor did not pass the preregistered duplicate gate; stop without refitting")
    if protocol["episodes_per_actor"] != 50 or len(protocol["cases"]) != 50 or protocol["decisions"] != 512 or protocol["step_ticks"] != 128:
        raise ValueError("Expected the unchanged fifty-case, 512x128 frozen protocol")
    baseline_ref = artifact(args.v2_batch)
    baseline = json.loads(Path(baseline_ref["path"]).read_text())
    if baseline["status"] != "completed" or checked(baseline["protocol"]) != protocol_ref:
        raise ValueError("V2 baseline must bind the same frozen protocol")
    original = baseline["actors"]["seven-game-256"]["episodes"]
    if [row["case"] for row in original] != protocol["cases"]:
        raise ValueError("V2 baseline cases differ from the original protocol")
    report = {"kind": "orders-v3-frozen-benchmark", "status": "running", "protocol": protocol_ref,
              "v3_run": artifact(args.imitation_run / "run.json"), "model": model, "policy": policy,
              "fit_gate": gate_ref, "v2_batch": baseline_ref, "source": source_identity(),
              "workers": args.workers, "training_run": False, "episodes": [], "failures": [],
              "first_route_definition": "The first purchased bus's first departure has exactly two distinct stops, both Full Load Any; never starting counts as invalid.",
              "supplied": "Frozen native initial saves with roads, two stops and a depot; no buses.",
              "comparison_scope": "All 50 attempted cases per actor; greedy and sampled separate, eight development seeds repeated over dimensions."}
    started = time.monotonic()
    try:
        report["source_capture"] = capture_source(root / "source")
        engine = Path(checked(protocol["engine"])["path"])
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {}
            for case in protocol["cases"]:
                context = protocol["contexts"][case["world_id"] - 1]
                directory = root / f"game-{case['case_id']:02d}"
                futures[pool.submit(execute, engine, args.policy.resolve(), model, directory, case, context, protocol["decisions"])] = case, context
            for future in as_completed(futures):
                case, context = futures[future]
                try:
                    path = future.result()
                    item = reuse_case(path, case, context, model, protocol["decisions"], protocol["step_ticks"],
                                      allow_interface_limit=True, engine=protocol["engine"], policy=policy)
                    evidence = verify_episode(item, context, model, protocol, policy)
                    native = json.loads(path.read_text())
                    item.update(first_route=native["first_route"], verification=evidence)
                    reconstructed = first_route_from_journal(path.parent / "worker/requests.jsonl")
                    if any(reconstructed[key] != item["first_route"][key] for key in ("vehicle_id", "started", "valid")):
                        raise ValueError("Recorded first departure differs from native public journal")
                    report["episodes"].append(item)
                    report["episodes"].sort(key=lambda row: row["case"]["case_id"])
                    print(json.dumps({"completed": len(report["episodes"]), "case": case["case_id"],
                                      "mode": case["mode"], "first_route_valid": item["first_route"]["valid"],
                                      "passengers": item["summary"]["passengers"],
                                      "operating_profit": item["summary"]["operating_profit"]}), flush=True)
                except BaseException as error:
                    report["failures"].append({"case": case, "error": repr(error)})
                write_json(root / "report.json", report)
        v2 = []
        for item in original:
            context = protocol["contexts"][item["case"]["world_id"] - 1]
            verify_episode(item, context, baseline["actors"]["seven-game-256"]["model"], protocol, baseline["policy"])
            path = Path(item["report"]["path"]).parent
            v2.append({**item, "first_route": first_route_from_journal(path / "worker/requests.jsonl")})
        report.update(v2_episodes=v2, v2_summary=grouped(v2), v3_summary=grouped(report["episodes"]))
        for ref in (protocol_ref, gate_ref, model, policy, baseline_ref):
            checked(ref)
        if report["failures"] or len(report["episodes"]) != 50:
            raise ValueError("Retained incomplete benchmark attempts; inspect explicit failures")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(root / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("protocol", "fit-audit", "imitation-run", "policy", "v2-batch", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    print(json.dumps(run(args)["v3_summary"], indent=2))
