#!/usr/bin/env python3
"""Paired native bus-control episodes with supplied infrastructure and game saves."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

from audit_action_inputs_v2 import artifact, checked
from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient, checked_tensors
from live_bus_orders_v2 import operation
from live_v2 import LiveV2, reset_manifest
from live_v2_artifacts import archive_tensors
from local import ROOT, capture_source, source_identity, write_json
from service_v2 import ServicePolicy, summarize

SCHEMA = "v2-m15-public-development-orders-v1"
MODE = "signed-log-orders-v2"


def archive_metadata(worker):
    """Keep complete native evidence losslessly without retaining large plain JSON."""
    records = []
    for path in sorted((worker / "artifacts").glob("tensors-*.json")):
        data = path.read_bytes()
        destination = path.with_suffix(path.suffix + ".gz")
        with destination.open("xb") as stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, compresslevel=1, mtime=0) as compressed:
                compressed.write(data)
        with gzip.open(destination, "rb") as stream:
            if stream.read() != data:
                raise ValueError("Native metadata archive differs")
        records.append({"original": str(path), "sha256": hashlib.sha256(data).hexdigest(), "archive": artifact(destination)})
        path.unlink()
    write_json(worker / "metadata-archives.json", records)


class CompactJournal:
    """Keep requests and public response summaries; native transitions remain complete."""
    def __init__(self, stream):
        self.stream = stream

    def write(self, text):
        entry = json.loads(text)
        if entry["kind"] == "response" and "observation" in entry["response"]:
            response = entry["response"]
            observation = response["observation"]
            entry["full_response_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            response["observation"] = {key: observation[key] for key in
                ("token", "tick", "economy", "vehicles", "stations", "depots", "terminal", "truncated")}
            response["candidate_count"] = len(observation["candidates"])
        self.stream.write(json.dumps(entry) + "\n")

    def flush(self):
        self.stream.flush()

    def close(self):
        self.stream.close()


def factory(world):
    return lambda executable, baseset, seed, split: reset_manifest(
        executable, baseset, seed, split, width=world["width"], height=world["height"])


def game(engine, output, world, *, initial_save=None, decisions=512, ticks=128):
    client = LiveV2(engine, output, seed=world["seed"], split="development", decisions=decisions,
                    ticks=ticks, observation_mode="orders-v1", initial_save=initial_save, _reset_factory=factory(world))
    client.events = CompactJournal(client.events)
    return client


def checkpoint(client):
    response = client.request("CHECKPOINT")
    if response["status"] != "OK":
        raise ValueError("Native game checkpoint rejected")
    path = Path(response["checkpoint"]["file"]).resolve(strict=True)
    if not path.is_relative_to(client.output / "artifacts") or path.suffix != ".sav":
        raise ValueError("Native checkpoint escaped its isolated artifact directory")
    return {**artifact(path), "tick": response["checkpoint"]["tick"]}


def step(client, state, candidate, *, ticks=128):
    result = client.request("ACT", token=state["token"], candidate=candidate["key"])
    if result["status"] != "OK" or result["action"]["status"] not in ("SUCCESS", "NO_OP"):
        raise RuntimeError("Exposed legal action failed")
    transition = client.request("STEP")["transition"]
    if transition["tick_after"] - transition["tick_before"] != ticks:
        raise RuntimeError("Native step did not advance the declared tick budget")
    return transition


def setup(engine, output, world):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "world": world,
              "claim": "Public scripted infrastructure only; no buses or neural decisions supplied"}
    client = None
    try:
        client = game(engine, output / "worker", world, ticks=1)
        report["infrastructure_step_ticks"] = 1
        initial = client.request("OBSERVE")["observation"]
        write_json(output / "generated-initial.json", initial)
        policy = ServicePolicy(initial, planner="graph", minimum_length=8, site_checks=True)
        write_json(output / "plan.json", policy.plan)
        # Reserve the initially legal depot/station sites before road work changes
        # the bounded candidate inventory or town growth occupies those tiles.
        priority = {"BUILD_ROAD_DEPOT": 0, "BUILD_BUS_STOP": 1, "BUILD_ROAD_PATH": 2}
        remaining = sorted(policy.plan["actions"], key=lambda row: priority[row[0]])
        for _ in range(512):
            if not remaining:
                break
            state = client.request("OBSERVE")["observation"]
            inventory = {(row["family"], tuple(row["parameters"][1:4])): row for row in state["candidates"]}
            index = next((index for index, (family, parameters) in enumerate(remaining)
                          if (family, tuple(parameters)) in inventory), None)
            if index is None:
                candidate = next(row for row in state["candidates"] if row["family"] == "WAIT")
            else:
                family, parameters = remaining[index]
                candidate = inventory[(family, tuple(parameters))]
                del remaining[index]
            transition = step(client, state, candidate, ticks=1)
            if transition["terminal"]:
                raise RuntimeError("Infrastructure setup terminated")
        final = client.request("OBSERVE")["observation"]
        write_json(output / "setup-final.json", final)
        report["remaining_actions"] = remaining
        if remaining or len(final["stations"]) != 2 or len(final["depots"]) != 1 or final["vehicles"]:
            raise RuntimeError("Supplied infrastructure did not complete under native legality")
        write_json(output / "initial.json", final)
        report.update(status="completed", save=checkpoint(client), initial=artifact(output / "initial.json"))
        client.close()
        client = None
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        if client:
            client.abort()
        write_json(output / "report.json", report)
    return report


def scripted(state):
    inventory = {(row["family"], tuple(row["parameters"][1:4])): row for row in state["candidates"]}
    if not state["vehicles"]:
        return next(row for row in state["candidates"] if row["family"] == "BUY_BUS")
    if len(state["vehicles"]) != 1:
        raise ValueError("Scripted one-bus baseline acquired another vehicle")
    bus = state["vehicles"][0]
    destinations = sorted(station["id"] for station in state["stations"])
    if len(bus["orders"]) < 2:
        index = len(bus["orders"])
        return inventory[("SET_ROUTE", (bus["id"], 1 | index << 8 | 0x61 << 16, destinations[index]))]
    for order in bus["orders"]:
        if order["load_mode"] != 3:
            return inventory[("SET_ROUTE", (bus["id"], 2 | order["index"] << 8 | 3 << 16, 3))]
    if bus["stopped"]:
        return inventory[("START_VEHICLE", (bus["id"], 0, 0))]
    if state["economy"]["balance"] >= 20000 and state["economy"]["loan"] >= 10000:
        payment = inventory.get(("MANAGE_LOAN", (2, 10000, 0)))
        if payment:
            return payment
    return next(row for row in state["candidates"] if row["family"] == "WAIT")


def roundtrip(engine, output, world, save, expected):
    client = game(engine, output, world, initial_save=Path(save["path"]), decisions=1)
    try:
        actual = client.request("OBSERVE")["observation"]
        for name in ("economy", "vehicles", "stations", "depots", "tick", "token"):
            if actual[name] != expected[name]:
                raise ValueError("Saved-game roundtrip differs: " + name)
        if actual["map"]["roads"] != expected["map"]["roads"]:
            raise ValueError("Saved-game roundtrip roads differ")
        client.close()
        client = None
    finally:
        if client:
            client.abort()


def unsupported_order_state(state):
    """Describe unsupported actual state without altering actions or tensor inputs."""
    failures = []
    for bus in state["vehicles"]:
        orders = bus["orders"]
        if bus["orders_shared"] or len(orders) > 4 or any(
                order["type"] != 1 or order["raw_type"] not in (0x21, 0x61)
                or len(order["serialized"]) != 11 or order["serialized"][4] != 254
                or order["serialized"][9:] != [255, 255] for order in orders):
            failures.append({"vehicle_id": bus["id"], "orders_shared": bus["orders_shared"], "orders": orders})
    return failures


def episode(engine, policy_path, model, output, case, context, *, decisions=512, verify_save=False, capture_interface_limit=False):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "case": case, "source_save": checked(context["save"]),
              "engine": artifact(engine), "policy": artifact(policy_path) if model is not None else None,
              "guidance": "none; complete native legal mask", "decisions_budget": decisions, "step_ticks": 128,
              "device": "cpu", "training_run": False, "supplied": "Two stops, connecting roads and one depot; no buses"}
    client, policy = None, None
    started = time.monotonic()
    try:
        initial_expected = json.loads(Path(context["initial"]["path"]).read_text())
        client = game(engine, output / "worker", case["world"], initial_save=Path(context["save"]["path"]), decisions=decisions)
        initial = client.request("OBSERVE")["observation"]
        for name in ("economy", "vehicles", "stations", "depots", "tick"):
            if initial[name] != initial_expected[name]:
                raise ValueError("Paired loaded setup differs: " + name)
        write_json(output / "initial.json", initial)
        if model is not None:
            policy = PolicyClient(policy_path, output / "policy.log", "cpu", case["action_seed"], mode=case["mode"],
                                  weights=Path(model["path"]), financial_features=MODE)
            policy.check_financial_features()
            report["model"] = model
        transitions, operations, interim, interface_limit = [], [], [], []
        with (output / "decisions.jsonl").open("x") as log:
            for index in range(decisions):
                state = client.request("OBSERVE")["observation"]
                if state["terminal"]:
                    break
                if model is not None and capture_interface_limit:
                    interface_limit = unsupported_order_state(state)
                    if interface_limit:
                        break
                if policy is None:
                    candidate = scripted(state)
                    evidence = {"actor": "scripted-one-bus-repay"}
                else:
                    response = client.request("TENSORS")
                    obs, candidates, inventory, mask = checked_tensors(response, state, observation_mode="orders-v1")
                    policy.request("RESET")
                    prediction = policy.request(f"{obs}\t{candidates}")
                    selected = inventory.get(prediction["row"])
                    probabilities = prediction["probabilities"]
                    if (selected is None or not mask[prediction["row"]] or len(probabilities) != len(mask)
                            or any(not math.isfinite(value) or value < 0 or value > 1 for value in probabilities)
                            or abs(sum(probabilities) - 1) > 1e-5
                            or any(value != 0 for value, legal in zip(probabilities, mask) if not legal)):
                        raise ValueError("Policy chose outside the exact native mask")
                    candidate = next(row for row in state["candidates"] if row["key"] == selected["stable_key"])
                    evidence = {"row": prediction["row"], "family": selected["family_index"],
                                "selected_probability": prediction["probabilities"][prediction["row"]],
                                "observation": artifact(obs), "candidates": artifact(candidates),
                                "legal_rows": [row for row, value in enumerate(mask) if value]}
                transition = step(client, state, candidate)
                transitions.append(transition)
                operations.append(operation(candidate))
                log.write(json.dumps({"decision": index + 1, "operation": operations[-1], "candidate": candidate,
                                      "prediction": evidence, "tick": state["tick"]}) + "\n")
                log.flush()
                if (index + 1) % 128 == 0:
                    interim.append(checkpoint(client))
                if transition["terminal"]:
                    break
        final = client.request("OBSERVE")["observation"]
        write_json(output / "final.json", final)
        saved = checkpoint(client)
        client.close()
        client = None
        if policy:
            policy.close()
            policy = None
        archive_tensors(output / "worker", compresslevel=1)
        archive_metadata(output / "worker")
        report.update(status="completed", summary=summarize(transitions, initial, final), final_save=saved,
                      checkpoints=interim, operation_counts=dict(Counter(operations)),
                      valid_running_routes=sum(not bus["stopped"] and len(bus["orders"]) == 2 and
                          len({order["destination"] for order in bus["orders"]}) == 2 and
                          all(order["load_mode"] == 3 for order in bus["orders"]) for bus in final["vehicles"]))
        if interface_limit:
            report.update(status="terminated-interface", interface_limit=interface_limit,
                          termination_reason="Actual orders exceed the frozen orders-v1 representation; no alternative action or input repair applied")
        if verify_save or interface_limit:
            roundtrip(engine, output / "saved-game-roundtrip", case["world"], saved, final)
            report["saved_game_roundtrip"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        if client:
            client.abort()
        if policy:
            policy.abort()
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "run.json", report)
    return report


def plan(engine, output, *, resume=False):
    output.mkdir(parents=True, exist_ok=resume)
    contract = json.loads((ROOT / "config/v2/m15-scalable-contract.json").read_text())
    seeds = contract["seeds"]["sets"]["development"]["seeds"]
    worlds = [{"seed": seed, "width": width, "height": height}
              for width, height in ((64, 64), (128, 128), (64, 128), (128, 64)) for seed in seeds][:25]
    contexts = []
    for index, world in enumerate(worlds):
        directory = output / f"world-{index + 1:02d}"
        if resume and (directory / "report.json").is_file():
            result = json.loads((directory / "report.json").read_text())
            if result["world"] != world:
                raise ValueError("Preserved setup world differs")
            if result["status"] == "completed":
                checked(result["save"])
                checked(result["initial"])
            else:
                retry = 1
                while (output / f"world-{index + 1:02d}-retry-{retry:02d}").exists():
                    retry += 1
                directory = output / f"world-{index + 1:02d}-retry-{retry:02d}"
                result = setup(engine, directory, world)
        else:
            result = setup(engine, directory, world)
        contexts.append({"world_id": index + 1, "world": world, "save": result["save"], "initial": result["initial"]})
        write_json(output / "contexts.json", contexts)
        print(json.dumps({"setup_completed": index + 1, "total": 25, "world": world}), flush=True)
    cases = [{"case_id": index * 2 + offset + 1, "world_id": index + 1, "world": context["world"], "mode": mode,
              "action_seed": 20261005 + index * 2 + offset} for index, context in enumerate(contexts)
             for offset, mode in enumerate(("greedy", "sampled"))]
    protocol = {"schema": "openttd-live-bus-orders-fifty-game-protocol-1", "source": source_identity(),
                "engine": artifact(engine), "episodes_per_actor": 50, "worlds": 25, "contexts": contexts, "cases": cases,
                "decisions": 512, "step_ticks": 128, "modes": ["greedy", "sampled"],
                "claim": "Paired bus-control benchmark on 25 newly generated worlds, two modes each; supplied scripted infrastructure, no construction-learning claim",
                "unique_map_seeds": len({world["seed"] for world in worlds}),
                "baseline": "One bus, independent two-stop Full load any orders; repay 10,000 when cash >=20,000",
                "evaluation_only": True, "training_run": False}
    write_json(output / "protocol.json", protocol)
    return protocol


def campaign(engine, policy_path, model_run, actor, protocol_path, output):
    output.mkdir(parents=True, exist_ok=False)
    protocol_ref = artifact(protocol_path)
    protocol = json.loads(protocol_path.read_text())
    checked(protocol["engine"])
    if artifact(engine) != protocol["engine"]:
        raise ValueError("Campaign engine differs from the frozen setup protocol")
    model = None
    if model_run is not None:
        imitation, _ = checked_imitation_run(model_run, observation_schema=SCHEMA, financial_features=MODE)
        model = checked(imitation["model"])
    report = {"status": "running", "actor": actor, "source": source_identity(), "protocol": protocol_ref,
              "model": model, "training_run": False, "episodes": []}
    try:
        report["source_capture"] = capture_source(output / "source-provenance")
        for case in protocol["cases"]:
            context = protocol["contexts"][case["world_id"] - 1]
            result = episode(engine, policy_path, model, output / f"game-{case['case_id']:02d}", case, context,
                             decisions=protocol["decisions"], verify_save=case["case_id"] in (1, 2))
            report["episodes"].append({"case": case, "report": artifact(output / f"game-{case['case_id']:02d}/run.json"),
                                       "summary": result["summary"], "final_save": result["final_save"],
                                       "valid_running_routes": result["valid_running_routes"]})
            write_json(output / "report.json", report)
            print(json.dumps({"actor": actor, "completed": len(report["episodes"]), "total": 50,
                              "case": case["case_id"], "summary": result["summary"]}), flush=True)
        checked(protocol_ref)
        if model:
            checked(model)
        if len(report["episodes"]) != 50:
            raise ValueError("Campaign did not complete all 50 episodes")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("setup", "campaign"), required=True)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--model-run", type=Path)
    parser.add_argument("--actor", default="scripted-one-bus")
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--resume-setup", action="store_true")
    args = parser.parse_args()
    if args.stage == "setup":
        plan(args.openttd.resolve(), args.output.resolve(), resume=args.resume_setup)
    else:
        if args.protocol is None or (args.model_run is not None and args.policy is None):
            parser.error("Campaign requires a protocol and neural actors require an inference executable")
        campaign(args.openttd.resolve(), args.policy.resolve() if args.policy else None, args.model_run,
                 args.actor, args.protocol.resolve(), args.output.resolve())
