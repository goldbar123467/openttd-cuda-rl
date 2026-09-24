#!/usr/bin/env python3
"""Audit saved model choices against actual MCP calls and native company actions."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from local import write_json
from report_shared_v2 import report as economic_report


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def verify(root):
    run = json.loads((root / "run.json").read_text())
    if run["kind"] != "local-llm-mcp-development-match" or run["status"] != "completed":
        raise ValueError("Audit requires a completed actual LLM/MCP match")
    models = rows(root / "model-calls.jsonl")
    calls = rows(root / "controller-tools.jsonl")
    by_model = defaultdict(list)
    for call in calls:
        by_model[call["model_call"]].append((call["tool"], call["arguments"]))
    for index, model in enumerate(models):
        if model["index"] != index or "response" not in model:
            raise ValueError("Model response history is incomplete")
        selected = [(call["function"]["name"], call["function"]["arguments"])
                    for call in model["response"]["message"].get("tool_calls", [])]
        executed = by_model.pop(index, [])
        # At native completion, the driver may discard later calls in the last
        # model response. Earlier cycles must execute every returned call.
        if (index < len(models) - 1 and selected != executed) or selected[:len(executed)] != executed:
            raise ValueError("Controller tool choices differ from the model response")
    if by_model or run["model_calls"] != len(models):
        raise ValueError("Controller has unaccounted model calls")
    for field, actual in (("model_elapsed_ns", sum(row["elapsed_ns"] for row in models)),
                          ("generated_tokens", sum(row["response"].get("eval_count", 0) for row in models)),
                          ("prompt_tokens_processed", sum(row["response"].get("prompt_eval_count", 0) for row in models)),
                          ("tool_errors", sum(row["is_error"] for row in calls))):
        if run[field] != actual:
            raise ValueError("Recorded inference cost/timing counters disagree with the model/tool history")
    server = rows(root / "match/mcp-tools.jsonl")
    defaults = {tool["name"]: {name: value["default"] for name, value in
        tool["input_schema"]["properties"].items() if "default" in value} for tool in run["tools"]}
    cursor = 0
    for call in calls:
        arguments = defaults.get(call["tool"], {}) | call["arguments"]
        if cursor < len(server) and (call["tool"], arguments) == (server[cursor]["tool"], server[cursor]["arguments"]):
            entry = server[cursor]
            cursor += 1
            if "result" in entry and (call["is_error"] or call["result"] != entry["result"]):
                raise ValueError("Model-visible tool response differs from actual MCP result")
            if "error" in entry and not call["is_error"]:
                raise ValueError("A failed MCP tool was reported as successful")
        elif not call["is_error"]:
            raise ValueError("Successful controller call is absent from MCP server history")
    if cursor != len(server):
        raise ValueError("MCP server received an unaccounted tool call")
    expected_actions = []
    decision = 0
    for call in calls:
        if call["is_error"] or not isinstance(call["result"], dict):
            continue
        data = call["result"]
        if call["tool"] == "submit_action" and data["status"] == "OK":
            expected_actions.append(("key", call["arguments"]["candidate_key"]))
        observation = data.get("observation", data)
        current = observation.get("decisions", data.get("global_decisions_completed", decision))
        if call["tool"] == "wait_turns":
            count = (current - decision + 1) // 2
            if not 1 <= count <= call["arguments"]["count"]:
                raise ValueError("WAIT batch consumed an inconsistent action budget")
            expected_actions.extend(("family", "WAIT") for _ in range(count))
        decision = max(decision, current)
    worker = root / "match/worker"
    native = [row for row in rows(worker / "transitions.jsonl") if row["company_id"] == run["company"]]
    if len(native) != len(expected_actions):
        raise ValueError("Native player actions do not match model-selected submissions/waits")
    for row, (kind, value) in zip(native, expected_actions, strict=True):
        if row["action"]["candidate" if kind == "key" else "family"] != value:
            raise ValueError("Native action differs from the model-selected command")
    summary = economic_report(worker)
    if summary != run["summary"] or decision != summary["global_decisions"]:
        raise ValueError("Saved match economics or decision count differs from native trace")
    names = ["run.json", "model-calls.jsonl", "controller-tools.jsonl", "match/mcp-tools.jsonl", "match/worker/transitions.jsonl"]
    return {"status": "passed", "claim": "Recorded LLM choices agree with MCP calls, responses and native actions; this does not establish strategy competence or deterministic LLM replay",
        "model_digest": run["identity"]["model"]["digest"], "model_calls": len(models), "tool_calls": len(calls),
        "tool_errors": sum(call["is_error"] for call in calls), "player_native_actions": len(native),
        "model_elapsed_ns": run["model_elapsed_ns"], "generated_tokens": run["generated_tokens"],
        "global_decisions": decision, "simulation_ticks": summary["simulation_ticks"],
        "inputs": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "audit.json", result)
    print(json.dumps(result, indent=2))
