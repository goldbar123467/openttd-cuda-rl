#!/usr/bin/env python3
"""Rederive V2 development economics from native traces without altering old reports."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from local import write_json
from service_v2 import summarize


def run(args):
    episodes = []
    groups = {}
    identities = {}
    engine = None
    for root in args.runs:
        run_path = root / "run.json"
        run = json.loads(run_path.read_text())
        reset = json.loads((root / "worker/reset.json").read_text())
        if run["status"] not in ("passed", "completed") or reset["split"] != "development":
            raise ValueError("Comparison requires completed development episodes")
        if run.get("decisions", run.get("maximum_decisions")) != 512:
            raise ValueError("Comparison requires a registered 512-action episode budget")
        if engine is not None and run["engine_sha256"] != engine:
            raise ValueError("Native engines differ")
        engine = run["engine_sha256"]
        trace_path = root / "worker/transitions.jsonl"
        rows = [json.loads(line) for line in trace_path.read_text().splitlines()]
        final = run["final_observation"]
        if not rows or not (final["terminal"] or final["truncated"]) or any(
            row["decision"] != i + 1 or row["tick_after"] - row["tick_before"] != 128 or
            (i and row["tick_before"] != rows[i-1]["tick_after"]) for i, row in enumerate(rows)):
            raise ValueError("Native episode trace is incomplete or discontinuous")
        initial = {"economy": rows[0]["before"], "tick": rows[0]["tick_before"]}
        summary = summarize(rows, initial, final)
        if "training_run" in run:
            label = f"neural/{run.get('guidance', 'none')}/{run['mode']}"
            controller = {"training_run": run["training_run"], "model": run["model"], "sampling_seed": run["run_seed"]}
        else:
            label = f"{run['controller']}/{run['guidance']}"
            controller = {"sampling_seed": run["sampling_seed"]}
        entry = {"group": label, "map_seed": reset["map_seed"], "source": str(root.resolve()),
                 "controller": controller, "summary": summary}
        episodes.append(entry)
        groups.setdefault(label, []).append(entry)
        for path in (run_path, trace_path):
            identities[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
    matrices = [sorted((entry["map_seed"] for entry in rows)) for rows in groups.values()]
    if any(matrix != matrices[0] for matrix in matrices):
        raise ValueError("Controller map/repetition matrices differ; incomplete comparisons are not averaged")
    report = {"claim": "Descriptive development comparison; one training seed and one sampling seed do not establish learning/generalization uncertainty",
              "engine_sha256": engine, "source_sha256": identities, "episodes": episodes, "summaries": {}}
    for name, rows in groups.items():
        values = [entry["summary"] for entry in rows]
        report["summaries"][name] = {"episodes": len(values),
            **{f"mean_{key}": statistics.mean(row[key] for row in values) for key in
               ("passengers", "operating_profit", "net_capital_spend", "cash_result_excluding_financing", "cash_result_before_capital")},
            "sustained_native_operating_service": sum(row["service_in_all_final_three_windows"] for row in values),
            "sustained_positive_cash_service": sum(row["positive_cash_service_in_all_final_three_windows"] for row in values),
            "bankruptcies": sum(row["bankruptcy"] for row in values), "invalid_actions": sum(row["invalid_actions"] for row in values)}
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "comparison.json", report)
    lines = ["# Live V2 development comparison", "", report["claim"], "",
             "| Controller | Episodes | Passengers | Native operating profit | Cash result before capital | Cash after capital | Sustained cash service |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, row in report["summaries"].items():
        lines.append(f"| {name} | {row['episodes']} | {row['mean_passengers']:.1f} | {row['mean_operating_profit']:.1f} | "
                     f"{row['mean_cash_result_before_capital']:.1f} | {row['mean_cash_result_excluding_financing']:.1f} | "
                     f"{row['sustained_positive_cash_service']}/{row['episodes']} |")
    lines += ["", "Cash results exclude loan principal. Cash before capital adds back net construction/vehicle cost, including sale proceeds.",
              "Native operating profit omits EXPENSES_OTHER; cash measures retain those charges.",
              "The planner supplies route geometry in assisted configurations. Uniform and scripted controls use the same guide.",
              "Prior summaries are preserved; this report rederives economics from their original native traces."]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
