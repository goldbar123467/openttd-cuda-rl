#!/usr/bin/env python3
"""Run immutable bus-control cases concurrently, retaining completed prior cases."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import time

from audit_action_inputs_v2 import artifact, checked
from evaluate_bus_orders_campaign_v2 import episode, MODE, SCHEMA
from imitation_warm_start_v2 import checked_imitation_run
from local import capture_source, source_identity, write_json


def reuse_case(path, case, context, model, decisions, ticks, *, allow_interface_limit=False, engine=None, policy=None):
    """Accept a matching saved episode; interface failures require explicit opt-in."""
    report = json.loads(path.read_text())
    if engine is not None:
        reset = json.loads((path.parent / "worker/reset.json").read_text())
        if reset["executable_sha256"] != checked(engine)["sha256"]:
            raise ValueError("Prior native engine differs from the frozen executable")
    if policy is not None and report.get("policy") is not None and checked(report["policy"]) != checked(policy):
        raise ValueError("Prior policy reader differs from the frozen executable")
    interface_limit = allow_interface_limit and report.get("status") == "terminated-interface" and bool(report.get("interface_limit"))
    if (report.get("status") != "completed" and not interface_limit or report["case"] != case
            or report["source_save"] != checked(context["save"])
            or report.get("model") != model or report["training_run"]
            or report["decisions_budget"] != decisions or report["step_ticks"] != ticks):
        raise ValueError("Prior episode does not match the frozen case/model/budget")
    summary = report["summary"]
    if ((summary["decisions"] != decisions and not summary["bankruptcy"] and not interface_limit)
            or summary["simulation_ticks"] != summary["decisions"] * ticks
            or summary["invalid_actions"]):
        raise ValueError("Prior episode has an incomplete or invalid native budget")
    checked(report["final_save"])
    for checkpoint in report["checkpoints"]:
        checked(checkpoint)
    if (case["case_id"] in (1, 2) or interface_limit) and report.get("saved_game_roundtrip") != "passed":
        raise ValueError("Prior episode lacks required native saved-game roundtrip")
    result = {"case": case, "report": artifact(path), "summary": summary,
              "final_save": report["final_save"], "valid_running_routes": report["valid_running_routes"]}
    if interface_limit:
        result["outcome"] = "terminated-interface"
    return result


def reuse_source(source, protocol, policy):
    """Bind older per-actor records to their frozen protocol and reader provenance."""
    references = [artifact(source)]
    data = json.loads(source.read_text())
    if checked(data["protocol"]) != checked(protocol):
        raise ValueError("Prior actor report used another frozen protocol")
    reader = data.get("policy")
    if reader is None:
        # Earlier actor records stored the reader in the enclosing batch record.
        parent = source.parent.parent / "report.json"
        enclosing = json.loads(parent.read_text())
        if enclosing.get("status") not in ("completed", "failed") or enclosing["actors"][data["actor"]] != data:
            raise ValueError("Prior actor lacks a finished matching parent reader record")
        references.append(artifact(parent))
        reader = enclosing["policy"]
        if checked(enclosing["protocol"]) != checked(protocol):
            raise ValueError("Prior parent batch used another frozen protocol")
    if checked(reader) != checked(policy):
        raise ValueError("Prior actor policy reader differs from the frozen executable")
    return data, references


def execute(engine, policy, model, output, case, context, decisions, allow_interface_limits=False):
    episode(engine, policy, model, output, case, context, decisions=decisions,
            verify_save=case["case_id"] in (1, 2), capture_interface_limit=allow_interface_limits)
    return output / "run.json"


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    protocol_ref = artifact(args.protocol)
    protocol = json.loads(Path(protocol_ref["path"]).read_text())
    engine = Path(checked(protocol["engine"])["path"])
    policy = args.policy.resolve(strict=True)
    actors = {}
    for name, frozen in protocol["frozen_actors"].items():
        run_path = Path(frozen["run"])
        if artifact(run_path / "run.json")["sha256"] != frozen["run_sha256"]:
            raise ValueError("Frozen training run changed")
        imitation, _ = checked_imitation_run(run_path, observation_schema=SCHEMA, financial_features=MODE)
        if imitation["model"] != frozen["model"]:
            raise ValueError("Frozen model archive changed")
        actors[name] = checked(imitation["model"])
    actors[protocol["scripted_actor"]] = None
    record = {"status": "running", "protocol": protocol_ref, "policy": artifact(policy),
              "source": source_identity(), "workers": args.workers, "training_run": False,
              "reused_completed_cases": [], "failures": [], "actors": {},
              "reuse_sources": [],
              "allow_interface_terminations": args.allow_interface_limits,
              "protocol_deviation": "Unsupported actual order states terminate as explicit interface failures with native saves; no mask/model change" if args.allow_interface_limits else None}
    try:
        record["source_capture"] = capture_source(output / "source-provenance")
        previous = {}
        for source in args.reuse:
            data, references = reuse_source(source, protocol_ref, record["policy"])
            record["reuse_sources"].extend(references)
            for item in data.get("episodes", []):
                key = (data["actor"], item["case"]["case_id"])
                if key in previous:
                    raise ValueError("Duplicate previously completed actor/case")
                checked(item["report"])
                previous[key] = Path(item["report"]["path"])
        jobs = []
        for actor, model in actors.items():
            root = output / actor
            root.mkdir()
            actor_report = {"status": "running", "actor": actor, "model": model,
                            "protocol": protocol_ref, "policy": record["policy"], "training_run": False,
                            "source": record["source"], "source_capture": record["source_capture"], "episodes": []}
            record["actors"][actor] = actor_report
            for case in protocol["cases"]:
                context = protocol["contexts"][case["world_id"] - 1]
                prior = previous.get((actor, case["case_id"]))
                if prior:
                    item = reuse_case(prior, case, context, model, protocol["decisions"], protocol["step_ticks"],
                                      allow_interface_limit=args.allow_interface_limits, engine=protocol["engine"], policy=record["policy"])
                    actor_report["episodes"].append(item)
                    record["reused_completed_cases"].append({"actor": actor, "case": case["case_id"], "report": item["report"]})
                else:
                    jobs.append((actor, model, root / f"game-{case['case_id']:02d}", case, context))
            write_json(root / "report.json", actor_report)
        write_json(output / "report.json", record)
        jobs.sort(key=lambda row: (row[3]["case_id"], row[0]))
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            pending = {pool.submit(execute, engine, policy, model, directory, case, context, protocol["decisions"], args.allow_interface_limits):
                       (actor, model, directory, case, context) for actor, model, directory, case, context in jobs}
            for future in as_completed(pending):
                actor, model, directory, case, context = pending[future]
                actor_report = record["actors"][actor]
                try:
                    path = future.result()
                    item = reuse_case(path, case, context, model, protocol["decisions"], protocol["step_ticks"],
                                      allow_interface_limit=args.allow_interface_limits, engine=protocol["engine"], policy=record["policy"])
                    actor_report["episodes"].append(item)
                    actor_report["episodes"].sort(key=lambda row: row["case"]["case_id"])
                    print(json.dumps({"actor": actor, "completed": len(actor_report["episodes"]), "case": case["case_id"],
                                      "passengers": item["summary"]["passengers"],
                                      "operating_profit": item["summary"]["operating_profit"]}), flush=True)
                except BaseException as error:
                    failure = {"actor": actor, "case": case, "directory": str(directory), "error": repr(error)}
                    record["failures"].append(failure)
                    print(json.dumps({"failure": failure}), flush=True)
                write_json(output / actor / "report.json", actor_report)
                write_json(output / "report.json", record)
        checked(protocol_ref)
        checked(record["policy"])
        for reference in record["reuse_sources"]:
            checked(reference)
        for actor, model in actors.items():
            actor_report = record["actors"][actor]
            if len(actor_report["episodes"]) != len(protocol["cases"]):
                actor_report["status"] = "failed"
            else:
                actor_report["status"] = "completed"
            if model:
                checked(model)
            write_json(output / actor / "report.json", actor_report)
        if record["failures"] or any(row["status"] != "completed" for row in record["actors"].values()):
            raise ValueError("Benchmark has failed or missing episodes; preserve and repair before comparison")
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "report.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse", type=Path, action="append", default=[])
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=8)
    parser.add_argument("--allow-interface-limits", action="store_true")
    run(parser.parse_args())
