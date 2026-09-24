#!/usr/bin/env python3
"""An actual local LLM chooses game tools through the official MCP client."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

from mcp import Client, StdioServerParameters

from local import ROOT, capture_source, write_json
from local_llm import LocalLLM, ollama_schema


PROMPT = """You operate one OpenTTD company against a neural opponent. Your objective is to deliver passengers, maintain positive operating cash flow, and survive. This is a bounded real game, not a conversation to describe hypothetical moves.
Use only the supplied game tools and the current public results. Return one tool call per response, with at most one sentence of accompanying text. Read game_info, then start_match exactly once with include_map=false. Inspect legal actions and public map regions, choose actions, submit them, then call step. A successful submit_action must be followed by step before another action. Copy tokens and candidate keys exactly from current tool results; never invent keys, IDs, money, or success.
Each turn advances 128 simulation ticks for both economies. The opponent then gets an equal action. Tool calls and inference consume wall time, not economic time. Finish the registered action budget or the game's terminal state. If you choose to do nothing, wait_turns consumes 1..8 real own turns. This is a choice available to you, not an instruction to always wait.
Passenger service needs connected roads, two owned bus stops accepting/producing passengers, a connected depot, a purchased bus, an assigned two-stop route, and a started vehicle. Inspect the public map and native candidates; choose spending and loan decisions yourself. Native legality alone does not guarantee useful route connectivity. Building stops/depot is not enough to deliver passengers.
Use observe with include_map=false; inspect smaller map_region rectangles (at most 16x16) for geography. Page legal_actions with limit at most 8 and a family or tile/vehicle filter. You have bounded context: older complete tool cycles may be removed, but current observations and game rules remain available. Re-observe as necessary. A tool error is feedback; correct it rather than claiming it succeeded. Continue calling tools until the match ends. Do not ask the human to choose actions.
For legal_actions, family is an exact action-family name from legal_action_counts, such as BUILD_ROAD_PATH. parameter1 is an integer tile or vehicle ID, not a query string; omit it unless filtering a specific ID. minimum_acceptance and minimum_production are integer thresholds, not text expressions. For example, {"family":"BUILD_BUS_STOP","minimum_acceptance":8,"limit":8} queries stops accepting passengers. Always inspect returned candidates before submitting their keys.
"""


def decode_tool(response):
    if response.structured_content is not None:
        return response.structured_content
    if len(response.content) == 1 and response.content[0].type == "text":
        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return response.content[0].text
    return response.model_dump(mode="json")


def context_messages(cycles):
    """Keep whole assistant/tool cycles; never leave an orphan tool response."""
    kept = []
    size = 0
    for cycle in reversed(cycles):
        length = len(json.dumps(cycle))
        if kept and size + length > 20000:
            break
        kept.append(cycle)
        size += length
    return [message for cycle in reversed(kept) for message in cycle], len(cycles) - len(kept)


async def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    record = {"kind": "local-llm-mcp-development-match", "status": "running", "model_name": args.model,
        "company": args.company, "first_company": args.first_company, "map_seed": args.map_seed,
        "global_decision_budget": args.decisions, "configuration": vars(args) | {"system_prompt": PROMPT},
        "provider_inference_cost_usd": 0, "hardware_energy_cost_usd": None,
        "cost_note": "Inference uses the existing local model; no external paid provider request. Hardware and electricity are not priced.",
        "model_calls": 0, "model_elapsed_ns": 0, "prompt_tokens_processed": 0, "generated_tokens": 0,
        "tool_errors": 0, "global_decisions_completed": 0,
        "claim": "LLM choices through actual MCP; completion and playing strength require the native results"}
    # Convert paths once for JSON provenance, without passing host paths to the model.
    record["configuration"] = {key: str(value) if isinstance(value, Path) else value for key, value in record["configuration"].items()}
    write_json(root / "run.json", record)
    llm = LocalLLM(args.host_python)
    model_log = (root / "model-calls.jsonl").open("x")
    tools_log = (root / "controller-tools.jsonl").open("x")
    try:
        record["identity"] = llm.identity(args.model)
        # Load before starting the native game: loading does not consume its idle deadline.
        warm_request = {"model": args.model, "stream": False, "think": False, "keep_alive": "10m",
            "messages": [{"role": "user", "content": "Reply READY."}],
            "options": {"temperature": 0, "seed": args.seed, "num_ctx": 16384, "num_predict": 8}}
        record["warmup"] = await asyncio.to_thread(llm.request, "/api/chat", warm_request, 120)
        record["runtime_placement"] = llm.request("/api/ps")
        command = [str(ROOT / "scripts/dev/mcp_v2.py"), "--openttd", str(args.openttd.resolve()),
            "--policy", str(args.policy.resolve()), "--training-run", str(args.training_run.resolve()),
            "--device", args.device, "--decisions", str(args.decisions), "--company", str(args.company),
            "--first-company", str(args.first_company), "--split", "development", "--map-seed", str(args.map_seed),
            "--player-label", "local-llm:" + args.model, "--output", str(root / "match")]
        async with Client(StdioServerParameters(command=sys.executable, args=command, cwd=ROOT), read_timeout_seconds=60) as client:
            inventory = await client.list_tools()
            record["mcp_protocol"] = client.protocol_version
            record["server_info"] = client.server_info.model_dump(mode="json")
            record["tools"] = [tool.model_dump(mode="json") for tool in inventory.tools]
            available = {tool.name for tool in inventory.tools}
            ollama_tools = [{"type": "function", "function": {"name": tool.name,
                "description": tool.description, "parameters": ollama_schema(tool.input_schema)}} for tool in inventory.tools]
            for tool in ollama_tools:
                if tool["function"]["name"] == "legal_actions":
                    properties = tool["function"]["parameters"]["properties"]
                    properties["family"]["description"] = "Exact family name from legal_action_counts. Omit to query all families."
                    properties["parameter1"]["description"] = "Integer tile or vehicle ID. Omit for no ID filter. Never pass a string expression."
            cycles = []
            stagnant = 0
            complete = False
            for index in range(args.maximum_model_calls):
                history, dropped = context_messages(cycles)
                messages = [{"role": "system", "content": PROMPT},
                            {"role": "user", "content": "Play the registered match now, making your own decisions through the tools."}, *history]
                request = {"model": args.model, "stream": False, "think": False, "keep_alive": "10m",
                    "messages": messages, "tools": ollama_tools,
                    "options": {"temperature": 0, "seed": args.seed, "num_ctx": 16384, "num_predict": 768}}
                started = time.monotonic_ns()
                try:
                    response = await asyncio.to_thread(llm.request, "/api/chat", request, 45)
                except BaseException as exc:
                    model_log.write(json.dumps({"index": index, "request": request, "error": str(exc),
                        "elapsed_ns": time.monotonic_ns() - started, "dropped_context_cycles": dropped}) + "\n"); model_log.flush()
                    raise
                elapsed = time.monotonic_ns() - started
                record["model_calls"] += 1
                record["model_elapsed_ns"] += elapsed
                record["prompt_tokens_processed"] += response.get("prompt_eval_count", 0)
                record["generated_tokens"] += response.get("eval_count", 0)
                model_log.write(json.dumps({"index": index, "request": request, "response": response,
                    "elapsed_ns": elapsed, "dropped_context_cycles": dropped}, allow_nan=False) + "\n"); model_log.flush()
                message = response["message"]
                cycle = [message]
                calls = message.get("tool_calls", [])
                old_decisions = record["global_decisions_completed"]
                if not calls:
                    cycle.append({"role": "user", "content": "The game has not finished. Call a game tool to inspect, act, step, or explicitly wait; text alone does not play a turn."})
                for selected in calls:
                    function = selected["function"]
                    name, arguments = function["name"], function["arguments"]
                    if name not in available or not isinstance(arguments, dict):
                        result = {"is_error": True, "result": "Choose an available tool and JSON object arguments."}
                    else:
                        tool_response = await client.call_tool(name, arguments)
                        result = {"is_error": tool_response.is_error, "result": decode_tool(tool_response)}
                    record["tool_errors"] += bool(result["is_error"])
                    tools_log.write(json.dumps({"model_call": index, "tool": name, "arguments": arguments, **result}, allow_nan=False) + "\n"); tools_log.flush()
                    data = result["result"]
                    if not result["is_error"] and isinstance(data, dict):
                        observation = data.get("observation", data)
                        record["global_decisions_completed"] = max(record["global_decisions_completed"],
                            observation.get("decisions", data.get("global_decisions_completed", 0)))
                        complete = data.get("match_complete", False)
                    visible = json.dumps(result, separators=(",", ":"))
                    if len(visible) > 12000:
                        visible = json.dumps({"is_error": result["is_error"], "controller_context_limit": True,
                            "message": "The tool executed; its result exceeds the controller context limit. Query compact observations, smaller map regions or smaller candidate pages."})
                    cycle.append({"role": "tool", "tool_name": name, "content": visible})
                    print(json.dumps({"call": index + 1, "tool": name, "error": result["is_error"],
                        "global_decisions": record["global_decisions_completed"], "model_seconds": round(elapsed / 1e9, 3)}), flush=True)
                    if complete:
                        break
                cycles.append(cycle)
                stagnant = stagnant + 1 if record["global_decisions_completed"] == old_decisions else 0
                write_json(root / "run.json", record)
                if complete:
                    break
                if stagnant >= 16:
                    raise RuntimeError("LLM made 16 consecutive calls without advancing a native game turn")
            if not complete:
                raise RuntimeError("LLM exceeded its registered model-call budget before native completion")
        server = json.loads((root / "match/run.json").read_text())
        if server["status"] != "completed":
            raise RuntimeError("MCP server did not record native completion")
        record.update(status="completed", summary=server["summary"], final_runtime_placement=llm.request("/api/ps"))
        write_json(root / "summary.json", record["summary"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "run.json", record)
        model_log.close(); tools_log.close(); llm.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("openttd", "policy", "training-run", "output", "host-python"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--company", type=int, choices=(0, 1), default=0)
    parser.add_argument("--first-company", type=int, choices=(0, 1), default=0)
    parser.add_argument("--decisions", type=int, default=512)
    parser.add_argument("--map-seed", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--maximum-model-calls", type=int, default=1200)
    asyncio.run(run(parser.parse_args()))
