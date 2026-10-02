#!/usr/bin/env python3
"""Audit service and financing in short development evaluations after imitation/PPO.

This is a read-only report. It never consumes historical held-out games or treats
loan principal as earnings. Financing diagnostics describe behavior, not an
optimal debt policy or an explanation of the neural network's reasoning.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import statistics

from finance_observation_v2 import FIELDS
from local import ROOT, write_json
from studies.evidence_v2 import Inputs, verify_trace


def finance_metrics(rows):
    if not rows:
        raise ValueError("Cannot audit an empty episode")
    first, last = rows[0]["before"], rows[-1]["after"]
    started = None
    events = []
    opposite = 0
    previous_direction = 0
    interest = 0
    counter_resets = 0
    for row in rows:
        before, after = row["before"], row["after"]
        action = row["action"]
        successful = action["status"] in ("SUCCESS", "NO_OP") and not action.get("rolled_back", False)
        if successful and action["family"] == "START_VEHICLE" and started is None:
            started = row["decision"]
        direction = 0
        if successful and action["family"] == "MANAGE_LOAN":
            delta = after["loan"] - before["loan"]
            operation, amount = action["parameters"][1:3]
            if operation not in (1, 2) or amount <= 0 or delta != (amount if operation == 1 else -amount):
                raise ValueError("Successful financing action differs from observed principal movement")
            direction = 1 if delta > 0 else -1
            opposite += int(previous_direction == -direction)
            events.append({"decision": row["decision"], "choice": "borrow" if direction > 0 else "repay",
                           "principal": abs(delta), "cash_before": before["balance"], "cash_after": after["balance"],
                           "debt_before": before["loan"], "debt_after": after["loan"],
                           "service_already_started": started is not None,
                           "operating_profit_before": before["operating_profit"],
                           "cash_after_below_10000": after["balance"] < 10000})
        previous_direction = direction
        old = before.get("finance", {}).get("year_interest_paid")
        new = after.get("finance", {}).get("year_interest_paid")
        if old is not None and new is not None:
            counter_resets += int(new < old)
            interest += new - old if new >= old else new
    return {"initial_cash": first["balance"], "final_cash": last["balance"],
            "minimum_cash_at_decision_boundary": min([first["balance"], *[r["after"]["balance"] for r in rows]]),
            "initial_debt": first["loan"], "final_debt": last["loan"],
            "first_start_service_action": started,
            "borrow_actions": sum(e["choice"] == "borrow" for e in events),
            "repay_actions": sum(e["choice"] == "repay" for e in events),
            "principal_borrowed": sum(e["principal"] for e in events if e["choice"] == "borrow"),
            "principal_repaid": sum(e["principal"] for e in events if e["choice"] == "repay"),
            "immediate_opposite_loan_actions": opposite,
            "repay_before_service_actions": sum(e["choice"] == "repay" and not e["service_already_started"] for e in events),
            "repay_leaving_less_than_10000": sum(e["choice"] == "repay" and e["cash_after_below_10000"] for e in events),
            "observed_interest_lower_bound": interest if "finance" in first else None,
            "interest_counter_resets": counter_resets,
            "loan_decisions": events}


def validate_finance_chain(rows):
    for index, row in enumerate(rows):
        if index and row["before"] != rows[index - 1]["after"]:
            raise ValueError("Native finance state chain is discontinuous")
        for economy in (row["before"], row["after"]):
            finance = economy.get("finance")
            if finance is None:
                raise ValueError("This report requires finance-v1 observations")
            if set(finance) != set(FIELDS) or any(type(finance[k]) is not int for k in FIELDS):
                raise ValueError("Invalid native finance fields")
            if finance["borrowing_headroom"] != max(0, finance["maximum_loan"] - economy["loan"]):
                raise ValueError("Borrowing capacity does not reconcile with debt")
            if finance["quarter_operating_profit"] != finance["quarter_income"] + finance["quarter_expenses"]:
                raise ValueError("Quarter finance does not reconcile")
            if finance["year_interest_paid"] < 0:
                raise ValueError("Native interest counter is negative")


def load_case(label, path, inputs):
    root = Path(path).resolve()
    run = inputs.json(root / "run.json")
    reset = inputs.json(root / "worker/reset.json")
    contract = inputs.json(ROOT / "config/v2/m15-scalable-contract.json")
    if (run["status"] not in ("passed", "completed") or run["split"] != "development" or
            reset["split"] != "development" or run.get("final_evaluation_accessed") is not False or
            run["map_seed"] != reset["map_seed"] or reset["map_seed"] not in contract["seeds"]["sets"]["development"]["seeds"] or
            run["engine_sha256"] != reset["executable_sha256"]):
        raise ValueError("Only completed development episodes with matching native reset identities are accepted")
    if run["observation_schema_id"] != "v2-m15-public-development-finance-v1":
        raise ValueError("Evaluation must use finance-v1 observations")
    rows = [json.loads(line) for line in inputs.read(root / "worker/transitions.jsonl").splitlines()]
    validate_finance_chain(rows)
    # Reuse the established clock, reset, state-hash, boundary and economics
    # verifier without weakening its historical scalar-only economy schema.
    stripped = copy.deepcopy(rows)
    final = copy.deepcopy(run["final_observation"])
    if final["economy"] != rows[-1]["after"]:
        raise ValueError("Final finance observation differs from native trace")
    final["economy"].pop("finance")
    for row in stripped:
        row["before"].pop("finance")
        row["after"].pop("finance")
    summary = verify_trace(stripped, final, reset, inputs.json(root / "worker/reset-projection.json"),
                           inputs.json(root / "worker/live.json"), decisions=run["decisions"])
    if run.get("summary") != summary:
        raise ValueError("Stored summary differs from native economics and command costs")
    model = run.get("model")
    training_path = run.get("training_run") or run.get("imitation_run")
    if training_path:
        training_root = Path(training_path).resolve()
        training = inputs.json(training_root / "run.json")
        weights = Path(training["model"]["path"]).resolve()
        if (training["status"] != "completed" or training["model"] != model or
                weights != training_root / "inference-weights.pt" or
                hashlib.sha256(inputs.read(weights)).hexdigest() != model["sha256"] or
                (run.get("training_run") and training["engine_sha256"] != run["engine_sha256"]) or
                (training.get("guidance", "none") or "none") != run.get("trained_guidance") or
                training["observation_schema_id"] != run["observation_schema_id"] or
                training.get("financial_features", "raw") != run.get("financial_features", "raw")):
            raise ValueError("Evaluation model does not match its completed training run")
        if set(training.get("training_map_seeds", [])) & {run["map_seed"]}:
            raise ValueError("Evaluation map also appears in policy training")
        if run.get("imitation_run"):
            ancestry = run["initial_policy"]
            if (training["kind"] != "native-v2-human-imitation" or
                    ancestry["run_sha256"] != hashlib.sha256(inputs.read(training_root / "run.json")).hexdigest() or
                    ancestry["weights_sha256"] != model["sha256"]):
                raise ValueError("Imitation ancestry identity differs")
    return {"label": label, "path": str(root), "map_seed": run["map_seed"], "mode": run["mode"],
            "requested_decisions": run["decisions"],
            "action_seed": run.get("run_seed", run.get("sampling_seed")), "model": model,
            "guidance": run["guidance"], "guidance_override": run.get("guidance_override"),
            "trained_guidance": run.get("trained_guidance"), "imitation_run": run.get("imitation_run"),
            "engine_sha256": run["engine_sha256"], "source": run["source"], "reset": reset,
            "observation_schema_id": run["observation_schema_id"], "summary": summary,
            "finance": finance_metrics(rows)}


def build_report(cases):
    if not cases:
        raise ValueError("No completed evaluation cases supplied")
    groups = defaultdict(list)
    seen = set()
    for case in cases:
        identity = (case["label"], case["map_seed"], case["mode"], case["action_seed"])
        if identity in seen:
            raise ValueError("Duplicate evaluation case")
        seen.add(identity)
        groups[case["label"]].append(case)
    comparisons = {}
    for label, values in groups.items():
        if len({json.dumps(c["model"], sort_keys=True) for c in values}) != 1:
            raise ValueError("Multiple model identities share one evaluation label")
        if len({(c["guidance"], c["mode"], c["requested_decisions"]) for c in values}) != 1:
            raise ValueError("One evaluation label mixes guides, modes or episode budgets")
        comparisons[label] = {"games": len(values), "maps": sorted({c["map_seed"] for c in values}),
            "service_started_games": sum(c["finance"]["first_start_service_action"] is not None for c in values),
            "passenger_service_games": sum(c["summary"]["passengers"] > 0 for c in values),
            "bankruptcies": sum(c["summary"]["bankruptcy"] for c in values),
            "invalid_actions": sum(c["summary"]["invalid_actions"] for c in values),
            **{"mean_" + key: statistics.mean(c["summary"][key] for c in values)
               for key in ("passengers", "operating_profit", "cash_result_excluding_financing", "capital_spend")},
            **{"mean_" + key: statistics.mean(c["finance"][key] for c in values)
               for key in ("final_cash", "minimum_cash_at_decision_boundary", "final_debt", "borrow_actions", "repay_actions", "immediate_opposite_loan_actions")}}
    signatures = {}
    for label, values in groups.items():
        signatures[label] = sorted(json.dumps({"reset": c["reset"], "mode": c["mode"], "seed": c["action_seed"],
            "guidance": c["guidance"],
            "schema": c["observation_schema_id"], "decisions": c["requested_decisions"]}, sort_keys=True) for c in values)
    return {"kind": "development-v2-imitation-ppo-evaluation-report", "groups": comparisons, "cases": cases,
            "matched_environment_settings": all(v == next(iter(signatures.values())) for v in signatures.values()),
            "source_identity_same": len({json.dumps(c["source"], sort_keys=True) for c in cases}) == 1,
            "claim": "Descriptive development-map evaluation; this small sample does not establish general playing strength or optimal financing.",
            "notes": ["Loan principal is excluded from cash results. Native executed command costs determine capital spending.",
                      "The public planner supplies route geometry. Repayment counts and a cash threshold do not establish sensible financing by themselves.",
                      "Immediate opposite loan actions count adjacent decision pairs; an alternating three-action sequence has two such pairs.",
                      "Interest is a lower bound from observed year-to-date counters. Charges in a step crossing a year boundary can be hidden by the reset.",
                      "Effective environment/guide settings and source identities are checked separately. Imitation-to-guide mask transfer remains explicit per case.",
                      "No held-out episodes are read or used, and no model is selected automatically."]}


def run(args):
    inputs = Inputs()
    cases = []
    for value in args.runs:
        label, separator, path = value.partition("=")
        if not separator or not label or not path:
            raise ValueError("Each run must be LABEL=PATH")
        cases.append(load_case(label, path, inputs))
    report = build_report(cases)
    inputs.unchanged()
    report["input_sha256"] = inputs.sha256
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "report.json", report)
    lines = ["# Imitation/PPO development evaluation", "", report["claim"], "",
             "| Policy | Map | Starts service | Passengers | Operating profit | Cash excluding financing | Final cash | Final debt | Borrow / repay | Immediate reversals |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in cases:
        summary, finance = case["summary"], case["finance"]
        lines.append(f"| {case['label']} | {case['map_seed']} | {finance['first_start_service_action'] or 'no'} | "
                     f"{summary['passengers']} | {summary['operating_profit']} | {summary['cash_result_excluding_financing']} | "
                     f"{finance['final_cash']} | {finance['final_debt']} | {finance['borrow_actions']} / {finance['repay_actions']} | "
                     f"{finance['immediate_opposite_loan_actions']} |")
    lines += ["", f"Matched environment settings across groups: {report['matched_environment_settings']}.",
              f"Identical evaluator source snapshots: {report['source_identity_same']}.", "", *report["notes"]]
    (args.output / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output": str(args.output), "groups": report["groups"],
                      "matched_environment_settings": report["matched_environment_settings"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", required=True, help="Repeated labels pair models across maps: LABEL=PATH")
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
