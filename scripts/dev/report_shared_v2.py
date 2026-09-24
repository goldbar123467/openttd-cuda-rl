#!/usr/bin/env python3
"""Summarize simultaneous researcher-only economic snapshots from a shared game."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from local import write_json


def report(worker):
    result_path = worker / "artifacts/live-result.json"
    trace_path = worker / "transitions.jsonl"
    native = json.loads(result_path.read_text())
    rows = [json.loads(line) for line in trace_path.read_text().splitlines()]
    if native["schema_version"] != "openttd-rl-development-v2-shared-1" or native["status"] != "COMPLETE":
        raise ValueError("Shared economics requires a complete native match")
    if len(rows) != native["decisions"] or any(row["decision"] != i + 1 or len(row["research_economies"]) != 2 for i, row in enumerate(rows)):
        raise ValueError("Shared trace is incomplete or lacks simultaneous accounting")
    for i, row in enumerate(rows):
        if row["tick_after"] - row["tick_before"] != 128 or (i and row["tick_before"] != rows[i - 1]["tick_after"]):
            raise ValueError("Shared simulation-time history differs")
        if row["company_id"] != (native["company_id"] + i) % 2:
            raise ValueError("Shared actor order differs")
    attempts = [Counter(), Counter()]
    pending = None
    # Full public observations make these logs exceed a gigabyte per match.
    # Only a single request/response pair is needed for submission accounting.
    requests = worker / "requests.jsonl"
    events_file = requests.open() if requests.exists() else gzip.open(requests.with_suffix(".jsonl.gz"), "rt")
    with events_file as events:
        for line in events:
            event = json.loads(line)
            if event["kind"] == "request":
                pending = event["request"]
            elif event["kind"] == "response" and pending:
                company = pending["company_id"]
                if company not in (0, 1):
                    continue
                response = event["response"]
                if pending["operation"] == "ACT":
                    attempts[company]["action_attempts"] += 1
                    attempts[company]["rejected_submissions"] += response["status"] == "REJECTED"
                attempts[company]["out_of_turn_requests"] += response.get("reason") == "COMPANY_TURN"
                pending = None
    companies = []
    for company in range(2):
        beginning = native["initial_companies"][company]["economy"]
        final = native["companies"][company]["economy"]
        history = [beginning, *[row["research_economies"][company] for row in rows]]
        observed = next(value for value in reversed(history) if "operating_profit" in value)
        end = final if "operating_profit" in final else observed
        actions = [row for row in rows if row["company_id"] == company]
        capital = sum(command["cost"] for row in actions if row["action"]["family"] in
            ("BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS", "SELL_VEHICLE")
            for command in row["action"]["native_commands"] if command["phase"] == "EXECUTE" and command["status"] == "SUCCESS")
        windows = []
        for start in range(0, len(rows), 128):
            finish = min(start + 128, len(rows))
            before, after = history[start], history[finish]
            complete_accounting = all("operating_profit" in value for value in (before, after))
            window_capital = sum(command["cost"] for row in rows[start:finish] if row["company_id"] == company and
                row["action"]["family"] in ("BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS", "SELL_VEHICLE")
                for command in row["action"]["native_commands"] if command["phase"] == "EXECUTE" and command["status"] == "SUCCESS")
            windows.append({"first_global_decision": start + 1, "global_decisions": finish - start,
                "passengers": after["delivered_passengers"] - before["delivered_passengers"] if complete_accounting else None,
                "operating_profit": after["operating_profit"] - before["operating_profit"] if complete_accounting else None,
                "cash_result_before_capital": after["balance"] - before["balance"] -
                    (after["loan"] - before["loan"]) + window_capital if complete_accounting else None})
        profit = end["operating_profit"] - beginning["operating_profit"]
        balance_change = end["balance"] - beginning["balance"]
        loan_change = end["loan"] - beginning["loan"]
        cash_result = balance_change - loan_change
        companies.append({"company_id": company, "actions": len(actions), **dict(attempts[company]),
            "action_counts": dict(Counter(row["action"]["family"] for row in actions)),
            "native_action_failures": sum(row["action"]["status"] not in ("SUCCESS", "NO_OP") for row in actions),
            "bankruptcy": not final["alive"], "accounting_before_liquidation": "operating_profit" not in final,
            "passengers": end["delivered_passengers"] - beginning["delivered_passengers"],
            "income": end["income"] - beginning["income"], "operating_profit": profit,
            "net_capital_spend": capital, "operating_profit_less_capital": profit - capital,
            "balance_change": balance_change, "loan_change": loan_change,
            "cash_result_excluding_financing": cash_result, "other_cash_flow": cash_result - (profit - capital),
            "cash_result_before_capital": cash_result + capital,
            "first_delivery_global_decision": next((row["decision"] for row in rows if row["research_economies"][company].get("delivered_passengers", 0) > beginning["delivered_passengers"]), None),
            "windows": windows,
            "service_in_all_final_three_windows": len(windows) == 4 and all(w["global_decisions"] == 128 and
                (w["passengers"] or 0) > 0 and (w["operating_profit"] or 0) > 0 for w in windows[-3:]),
            "positive_cash_service_in_all_final_three_windows": len(windows) == 4 and all(w["global_decisions"] == 128 and
                (w["passengers"] or 0) > 0 and (w["cash_result_before_capital"] or 0) > 0 for w in windows[-3:])})
    total = sum(company["passengers"] for company in companies)
    for company in companies:
        company["passenger_market_share"] = company["passengers"] / total if total else None
    return {"kind": "shared-native-economic-summary", "accounting_schema": "development-v2-shared-economics-2",
            "global_decisions": len(rows),
            "simulation_ticks": native["tick"] - native["initial_tick"], "companies": companies,
            "inputs": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (result_path, trace_path)},
            "claim": "Native development economics; shaped reward, loan principal and capital are separate"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.worker.resolve())
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "summary.json", result)
    print(json.dumps(result, indent=2))
