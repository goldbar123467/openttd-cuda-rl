#!/usr/bin/env python3
"""Compare recorded MCP matches without treating failed runs as missing data."""
import argparse
import hashlib
import json
from pathlib import Path

from local import write_json
from report_shared_v2 import report as economic_report
from verify_mcp_llm import verify as verify_llm


def run(args):
    report = {"claim": "Descriptive development matches; no held-out or population-level strength claim", "matches": [], "inputs": {}}
    common = None
    for root in args.runs:
        root = root.resolve()
        data = json.loads((root / "run.json").read_text())
        if data["kind"] not in ("scripted-public-mcp-development-match", "local-llm-mcp-development-match"):
            raise ValueError("Unsupported controller provenance")
        llm = data["kind"] == "local-llm-mcp-development-match"
        match = json.loads((root / "match/run.json").read_text())
        registered = {key: match[key] for key in ("global_decisions", "ticks_per_global_decision", "first_company",
                                                   "split", "engine_sha256", "policy_binary_sha256", "model", "sampling_seed")}
        registered["neural_guidance"] = match.get("neural_guidance", "none")
        if registered["split"] != "development" or registered["global_decisions"] != 512:
            raise ValueError("Comparison requires registered full 512-step development matches")
        if common is not None and common != registered:
            raise ValueError("Registered game settings or neural opponents differ")
        common = registered
        entry = {"source": str(root), "controller": "LLM" if llm else "scripted:" + data["controller"],
            "map_seed": data["map_seed"], "player_company": data["company"], "status": data["status"],
            "error": data.get("error"), "model_identity": data.get("identity"),
            "model_calls": data.get("model_calls"), "model_seconds": data.get("model_elapsed_ns", 0) / 1e9 if llm else None,
            "generated_tokens": data.get("generated_tokens"), "prompt_tokens_processed": data.get("prompt_tokens_processed"),
            "server_info": data.get("server_info"), "tool_errors": data.get("tool_errors"),
            "provider_cost_usd": data.get("provider_inference_cost_usd"), "hardware_energy_cost_usd": None}
        tool_log = root / "match/mcp-tools.jsonl"
        if tool_log.is_file():
            calls, errors = 0, 0
            with tool_log.open() as events:
                for line in events:
                    calls += 1
                    errors += "error" in json.loads(line)
            entry["server_tool_calls"] = calls
            entry["server_tool_errors"] = errors
            if not llm:
                entry["tool_errors"] = entry["server_tool_errors"]
        if data["status"] == "completed":
            summary = economic_report(root / "match/worker")
            if summary != data["summary"]:
                raise ValueError("Saved economic summary differs from native trace")
            if llm:
                entry["controller_audit"] = verify_llm(root)
            entry["summary"] = summary
            transitions = [json.loads(line) for line in (root / "match/worker/transitions.jsonl").read_text().splitlines()]
            entry["zero_cost_construction_actions"] = [sum(row["company_id"] == company and row["action"]["family"] in
                ("BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT") and
                any(command["phase"] == "EXECUTE" and command["status"] == "SUCCESS" for command in row["action"]["native_commands"]) and
                sum(command["cost"] for command in row["action"]["native_commands"] if command["phase"] == "EXECUTE") == 0
                for row in transitions) for company in range(2)]
            neural = [json.loads(line) for line in (root / "match/neural-actions.jsonl").read_text().splitlines()]
            entry["neural_inference_seconds"] = sum(row["inference_elapsed_ns"] for row in neural) / 1e9
        for name in ("run.json", "match/run.json", "match/mcp-tools.jsonl", "match/worker/transitions.jsonl"):
            path = root / name
            if path.is_file():
                with path.open("rb") as stream:
                    report["inputs"][str(path)] = hashlib.file_digest(stream, "sha256").hexdigest()
        report["matches"].append(entry)
    report["registered_common_settings"] = common
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "comparison.json", report)
    lines = ["# Shared-game MCP development matches", "", report["claim"], "",
        "Each registered match has 512 global decisions, 256 per company, and 65,536 shared simulation ticks unless bankruptcy ends it earlier.", "",
        "| Controller | Map | Company | Status | Passenger deliveries | Native operating profit | Cash after capital | Bankrupt | MCP errors | LLM calls / seconds |",
        "| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: |"]
    for entry in report["matches"]:
        if "summary" not in entry:
            lines.append(f"| {entry['controller']} | {entry['map_seed']} | {entry['player_company']} | {entry['status']} | — | — | — | — | {entry['tool_errors'] if entry['tool_errors'] is not None else '—'} | {entry['model_calls'] or '—'} |")
            continue
        for company in entry["summary"]["companies"]:
            player = company["company_id"] == entry["player_company"]
            label = entry["controller"] if player else "neural opponent"
            inference = f"{entry['model_calls']} / {entry['model_seconds']:.1f}" if player and entry["model_calls"] is not None else "—"
            lines.append(f"| {label} | {entry['map_seed']} | {company['company_id']} | completed | {company['passengers']} | "
                f"{company['operating_profit']} | {company['cash_result_excluding_financing']} | {company['bankruptcy']} | "
                f"{entry['tool_errors'] if player and entry['tool_errors'] is not None else '—'} | {inference} |")
    lines += ["", "Cash excludes loan principal and includes net capital and monthly other expenses. Native operating profit is a narrower subtotal.",
        "Command counts, zero-cost construction, rejected tools, service windows, market share, model identity and input hashes are retained in comparison.json.",
        "LLM wall time excludes model warmup and does not advance the game. Local provider charges are zero where recorded; hardware/electricity remain unpriced.",
        "Role-swapped maps are paired observations, not independent training seeds. Failed runs remain visible; no confidence interval or overall ranking is inferred."]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
