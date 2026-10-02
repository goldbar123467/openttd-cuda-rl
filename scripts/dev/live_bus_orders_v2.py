#!/usr/bin/env python3
"""Bounded unforced neural continuations from two disclosed human bus contexts."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

from audit_action_inputs_v2 import artifact, checked
from audit_bus_orders_v2 import MODES, SCHEMA, check_replay, route_status
from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient, checked_tensors
from live_v2 import LiveV2
from live_v2_artifacts import archive_tensors
from local import capture_source, host, source_identity, write_json
from service_v2 import summarize

CONTEXTS = {
    20: {"target_vehicle": 1, "expected_route": [1, 0],
         "supplied": "Human-built connecting roads, depot and two stations; no buses. Policy chooses purchase, route, loading and start."},
    35: {"target_vehicle": 2, "expected_route": [1, 2],
         "supplied": "Human-built roads/depot/three stations, running bus 1 with its human-configured full-load route, and human-purchased stopped bus 2 without orders. Policy chooses bus 2 copy/edit/loading/start."},
}
BOOTSTRAP_MAP_SEED = 1630856436


def public_exact(state):
    """Use only the public live order serialization, matching replay audit shape."""
    if "exact_orders" in state:
        return state
    return {**state, "exact_orders": [{"vehicle_id": v["id"], "orders": v["orders"]} for v in state["vehicles"]]}


def operation(candidate):
    if candidate["family"] != "SET_ROUTE":
        return candidate["family"]
    parameters = candidate["parameters"]
    opcode = parameters[2] & 255
    if opcode == 2:
        return "FULL_LOAD_ANY" if parameters[3] == 3 else "SET_LOAD_" + str(parameters[3])
    return {1: "INSERT_ORDER", 3: "COPY_ORDERS", 4: "DELETE_ORDER"}.get(opcode, "UNKNOWN_ORDER")


def run_context(args, replay, model, output, line, mode, financial_features):
    output.mkdir(parents=True, exist_ok=False)
    context = CONTEXTS[line]
    initial_save = replay / f"before-command-{line}.sav"
    before_path = replay / "samples" / f"command-{line}-observation.json"
    before = json.loads(before_path.read_text())
    record = {"kind": "live-bus-orders-context", "status": "running", "mode": mode, "seed": args.seed,
              "device": args.device, "financial_features": financial_features, "observation_schema_id": SCHEMA,
              "context": context, "source_command_line": line, "initial_save": artifact(initial_save),
              "initial_observation": artifact(before_path), "maximum_decisions": args.decisions, "step_ticks": args.ticks,
              "map_initialization": {"bootstrap_map_seed": BOOTSTRAP_MAP_SEED, "bootstrap_split": "development",
                                     "played_map": "Restored verified human context save; bootstrap generated map is discarded before any policy observation"},
              "guidance": "none; exact complete native legal mask", "recurrent_state": "reset before each decision, matching independent imitation examples",
              "claim": "Unforced continuation of a training-recording context with supplied infrastructure; no construction learning or held-out generalization claim",
              "economics_scope": "Whole company, including the supplied human-controlled source bus in the second context; cargo_count is a final vehicle snapshot, not delivered cargo attribution",
              "starts": [], "route_ready_decisions": []}
    game, policy = None, None
    started = time.monotonic()
    try:
        policy = PolicyClient(args.policy.resolve(), output / "policy.log", args.device, args.seed, mode=mode,
                              weights=Path(model["path"]), financial_features=financial_features)
        policy.check_financial_features()
        game = LiveV2(args.openttd, output / "worker", seed=BOOTSTRAP_MAP_SEED, decisions=args.decisions, ticks=args.ticks,
                      split="development", observation_mode="orders-v1", initial_save=initial_save)
        initial = game.request("OBSERVE")["observation"]
        for key in ("vehicles", "stations", "depots", "economy", "tick"):
            if initial[key] != before[key]:
                raise ValueError("Loaded supplied context differs from native replay: " + key)
        if initial["map"]["roads"] != before["map"]["roads"]:
            raise ValueError("Loaded supplied roads differ from native replay")
        write_json(output / "initial.json", initial)
        transitions, actions = [], []
        with (output / "predictions.jsonl").open("x") as predictions:
            for decision in range(args.decisions):
                state = game.request("OBSERVE")["observation"]
                current = route_status(public_exact(state), context["target_vehicle"])
                if current["route"] == context["expected_route"] and current["both_endpoints_full_load_any"]:
                    record["route_ready_decisions"].append(decision)
                response = game.request("TENSORS")
                observation_path, candidate_path, candidates, mask = checked_tensors(response, state, observation_mode="orders-v1")
                policy.request("RESET")
                inference_start = time.monotonic_ns()
                prediction = policy.request(f"{observation_path}\t{candidate_path}")
                elapsed = time.monotonic_ns() - inference_start
                probabilities = prediction["probabilities"]
                if (prediction["row"] not in candidates or len(probabilities) != 4096 or
                        any(not math.isfinite(p) or p < 0 or p > 1 for p in probabilities) or
                        abs(sum(probabilities) - 1) > 1e-5 or any(p != 0 for p, legal in zip(probabilities, mask) if not legal)):
                    raise ValueError("Native policy selected outside exact legal distribution")
                selected = candidates[prediction["row"]]
                public_candidate = next(c for c in state["candidates"] if c["key"] == selected["stable_key"])
                selected_operation = operation(public_candidate)
                if selected_operation == "START_VEHICLE":
                    vehicle = public_candidate["parameters"][1]
                    start = {"decision": decision + 1, **route_status(public_exact(state), vehicle)}
                    start["is_target_bus"] = vehicle == context["target_vehicle"]
                    start["exact_expected_route"] = start["is_target_bus"] and start["route"] == context["expected_route"]
                    record["starts"].append(start)
                predictions.write(json.dumps({"decision": decision + 1, "token": state["token"], "prediction": prediction,
                                               "candidate": public_candidate, "operation": selected_operation,
                                               "inference_elapsed_ns": elapsed}) + "\n")
                predictions.flush()
                result = game.request("ACT", token=state["token"], candidate=selected["stable_key"])
                if result["status"] != "OK" or result["action"]["status"] not in ("SUCCESS", "NO_OP"):
                    raise RuntimeError("Legal neural candidate failed during live execution")
                transition = game.request("STEP")["transition"]
                if transition["tick_after"] - transition["tick_before"] != args.ticks:
                    raise RuntimeError("Live simulation tick budget differs")
                transitions.append(transition)
                actions.append(selected_operation)
                if transition["terminal"]:
                    break
        final = game.request("OBSERVE")["observation"]
        write_json(output / "final.json", final)
        game.close(); game = None
        policy.close(); policy = None
        archive_tensors(output / "worker")
        record["summary"] = summarize(transitions, initial, final)
        record["operation_counts"] = dict(Counter(actions))
        record["target_final"] = route_status(public_exact(final), context["target_vehicle"])
        record["all_final_routes"] = [route_status(public_exact(final), v["id"]) for v in final["vehicles"]]
        record["target_started_with_exact_full_load_route"] = any(x["exact_expected_route"] and x["both_endpoints_full_load_any"] for x in record["starts"])
        record["target_final_exact_full_load_route"] = record["target_final"]["route"] == context["expected_route"] and record["target_final"]["both_endpoints_full_load_any"]
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        if game:
            game.abort()
        if policy:
            policy.abort()
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "run.json", record)
    return record


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not 1 <= args.decisions <= 64 or not 1 <= args.ticks <= 128:
        raise ValueError("Bus exercise is bounded to 1..64 decisions and 1..128 ticks")
    record = {"kind": "live-bus-orders-exercise", "status": "running", "source": source_identity(), "runtime": host(),
              "device": args.device, "seed": args.seed, "configuration": vars(args).copy(), "runs": [],
              "claim": "Supplied human-recording contexts, unforced neural continuations, greedy and sampled reported separately; no tuning on these outcomes"}
    record["configuration"] = {key: str(value) if isinstance(value, Path) else value for key, value in record["configuration"].items()}
    started = time.monotonic()
    try:
        record["source_capture"] = capture_source(output / "source")
        imitation, _ = checked_imitation_run(args.imitation_run, observation_schema=SCHEMA)
        financial_features = imitation["financial_features"]
        if financial_features not in MODES:
            raise ValueError("Bus exercise requires a versioned orders preprocessing model")
        record["financial_features"] = financial_features
        model = checked(imitation["model"])
        replay_ref = checked(imitation["dataset"]["replay_validation"])
        replay = Path(replay_ref["path"]).parent
        check_replay(replay)
        replay_report = json.loads(Path(replay_ref["path"]).read_text())
        recording = replay_report["source_recording"]
        recording_metadata = Path(recording.get("runtime_copy", recording["path"])) / "recording.json"
        record["loaded_recording"] = {"metadata": artifact(recording_metadata),
                                      "original_map_seed": json.loads(recording_metadata.read_text(encoding="utf-8-sig"))["seed"],
                                      "bootstrap_map_seed": BOOTSTRAP_MAP_SEED, "policy_sampling_seed": args.seed}
        record["artifacts"] = [model, replay_ref, artifact(args.imitation_run / "run.json"), artifact(args.policy), artifact(args.openttd)]
        record["artifacts"].append(record["loaded_recording"]["metadata"])
        for line in CONTEXTS:
            for mode in ("greedy", "sampled"):
                context_output = output / f"line-{line}-{mode}"
                result = run_context(args, replay, model, context_output, line, mode, financial_features)
                record["runs"].append({"report": artifact(context_output / "run.json"), "source_command_line": line,
                    "mode": mode, "summary": result["summary"], "operation_counts": result["operation_counts"],
                    "target_started_with_exact_full_load_route": result["target_started_with_exact_full_load_route"],
                    "target_final_exact_full_load_route": result["target_final_exact_full_load_route"], "target_final": result["target_final"]})
                write_json(output / "report.json", record)
                print(json.dumps(record["runs"][-1]), flush=True)
        for reference in record["artifacts"]:
            checked(reference)
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
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--imitation-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cuda:0")
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--decisions", type=int, default=24)
    parser.add_argument("--ticks", type=int, default=128)
    run(parser.parse_args())
