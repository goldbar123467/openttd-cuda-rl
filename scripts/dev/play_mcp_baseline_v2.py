#!/usr/bin/env python3
"""Run an explicitly scripted public-state MCP opponent, never an LLM substitute."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client, StdioServerParameters

from local import ROOT, capture_source, write_json
from service_v2 import ServicePolicy
from repair_v2 import connection


async def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    command = [str(ROOT / "scripts/dev/mcp_v2.py"), "--openttd", str(args.openttd.resolve()),
               "--policy", str(args.policy.resolve()), "--training-run", str(args.training_run.resolve()),
               "--device", args.device, "--decisions", str(args.decisions), "--company", str(args.company),
               "--first-company", str(args.first_company), "--split", "development",
               "--player-label", "scripted-public-mcp-" + args.controller, "--output", str(root / "match")]
    if args.map_seed is not None:
        command += ["--map-seed", str(args.map_seed)]
    record = {"kind": "scripted-public-mcp-development-match", "status": "running", "controller": args.controller,
              "company": args.company, "first_company": args.first_company, "map_seed": args.map_seed,
              "global_decisions": args.decisions, "claim": "Actual MCP/scripted versus neural match; no LLM participated",
              "decisions": [], "blocked_construction_turns": 0, "repair_checks": []}
    write_json(root / "run.json", record)
    try:
        async with Client(StdioServerParameters(command=sys.executable, args=command, cwd=ROOT), read_timeout_seconds=60) as client:
            record["negotiated_protocol"] = client.protocol_version
            record["server_info"] = client.server_info.model_dump(mode="json")

            async def call(name, arguments=None):
                response = await client.call_tool(name, arguments or {})
                if response.is_error:
                    raise RuntimeError(f"MCP {name} failed: {response.content}")
                if response.structured_content is not None:
                    return response.structured_content
                if len(response.content) != 1 or response.content[0].type != "text":
                    raise ValueError("Unexpected MCP JSON response shape")
                return json.loads(response.content[0].text)

            async def legal(family=None, parameter1=None):
                result = []
                offset = 0
                while True:
                    page = await call("legal_actions", {"family": family, "parameter1": parameter1,
                                                       "offset": offset, "limit": 64})
                    result.extend(page["candidates"])
                    offset += len(page["candidates"])
                    if offset >= page["total"]:
                        return result
                    if not page["candidates"]:
                        raise ValueError("MCP candidate pagination made no progress")

            observation = await call("start_match", {"include_map": args.controller != "wait"})
            planner = None
            repair_actions = []
            next_repair_check = 0
            if args.controller != "wait":
                observation["candidates"] = await legal()
                planner = ServicePolicy(observation, repay=True, planner="graph", minimum_length=12, site_checks=True)
                write_json(root / "public-plan.json", planner.plan)
            while not (observation["terminal"] or observation["truncated"]):
                if planner is None:
                    remaining = (args.decisions - observation["decisions"] + 1) // 2
                    stepped = await call("wait_turns", {"count": min(8, remaining)})
                else:
                    if (args.controller == "one-bus-repair" and planner.stage == len(planner.plan["actions"]) and
                            observation["vehicles"] and not observation["vehicles"][0]["stopped"] and
                            not repair_actions and observation["decisions"] >= next_repair_check):
                        observation = await call("observe", {"include_map": True})
                        endpoints = (planner.plan["line"][0], planner.plan["line"][-1])
                        current = connection(observation, *endpoints)
                        event = {"global_decision": observation["decisions"], "connected": current is not None}
                        if current is None:
                            observation["candidates"] = await legal("BUILD_ROAD_PATH")
                            detour = connection(observation, *endpoints, allow_construction=True)
                            event["detour"] = detour
                            if detour is not None:
                                repair_actions = list(detour["actions"])
                        record["repair_checks"].append(event)
                        next_repair_check = observation["decisions"] + 32
                    candidates = await legal("WAIT")
                    if repair_actions:
                        family, parameters = repair_actions[0]
                        candidates += await legal(family, parameters[0])
                    elif planner.stage < len(planner.plan["actions"]):
                        family, parameters = planner.plan["actions"][planner.stage]
                        candidates += await legal(family, parameters[0])
                    elif not observation["vehicles"]:
                        candidates += await legal("BUY_BUS", planner.plan["depot"])
                    else:
                        bus = observation["vehicles"][0]
                        candidates += await legal("SET_ROUTE", bus["id"])
                        candidates += await legal("START_VEHICLE", bus["id"])
                        candidates += await legal("MANAGE_LOAN")
                    observation["candidates"] = candidates
                    try:
                        if repair_actions:
                            family, parameters = repair_actions[0]
                            candidate = next((c for c in candidates if c["family"] == family and c["parameters"][1:4] == parameters), None)
                            if candidate is None:
                                record["repair_checks"].append({"global_decision": observation["decisions"],
                                    "planned_primitive_no_longer_exposed": repair_actions[0]})
                                repair_actions = []
                                next_repair_check = observation["decisions"]
                                candidate = next(c for c in candidates if c["family"] == "WAIT")
                        else:
                            candidate = planner.choose(observation)
                    except RuntimeError as exc:
                        if not str(exc).startswith("Planned primitive is no longer exposed/legal at stage "):
                            raise
                        # An opponent or changed native candidate set can block
                        # this fixed script. Record waiting, without bypassing
                        # exposed legality or inventing a replacement command.
                        candidate = next(c for c in candidates if c["family"] == "WAIT")
                        record["blocked_construction_turns"] += 1
                    accepted = await call("submit_action", {"token": observation["token"], "candidate_key": candidate["key"]})
                    if accepted["status"] != "OK" or accepted["action"]["status"] not in ("SUCCESS", "NO_OP"):
                        raise RuntimeError("Scripted MCP action failed at native boundary")
                    if repair_actions:
                        repair_actions.pop(0)
                        if not repair_actions:
                            next_repair_check = observation["decisions"] + 2
                    record["decisions"].append({"global_decision": observation["decisions"] + 1,
                                                "candidate": candidate, "public_plan_stage": planner.stage})
                    stepped = await call("step")
                observation = stepped["observation"]
                if observation["decisions"] <= 16 or observation["decisions"] % 128 == 0:
                    print(json.dumps({"global_decisions": observation["decisions"], "company": args.company,
                                      "economy": observation["economy"]}), flush=True)
                write_json(root / "run.json", record)
                if stepped["match_complete"]:
                    break
        server_result = json.loads((root / "match/run.json").read_text())
        if server_result["status"] != "completed":
            raise RuntimeError("Scripted MCP match did not complete natively")
        record.update(status="completed", summary=server_result["summary"])
        write_json(root / "summary.json", record["summary"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "run.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("openttd", "policy", "training-run", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--controller", choices=("wait", "one-bus-repay", "one-bus-repair"), required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--company", type=int, choices=(0, 1), default=0)
    parser.add_argument("--first-company", type=int, choices=(0, 1), default=0)
    parser.add_argument("--decisions", type=int, default=512)
    parser.add_argument("--map-seed", type=int)
    asyncio.run(run(parser.parse_args()))
