#!/usr/bin/env python3
"""Rederive live cargo economics from native traces, including failed cases."""
import argparse
import hashlib
import json
from pathlib import Path

from cargo_live import summarize_mail
from local import capture_source, source_identity, write_json


def run(args):
    cases, hashes, engine = [], {}, None
    matrices = {}
    for root in args.runs:
        path = root / "run.json"
        run = json.loads(path.read_text())
        if run["split"] != "development" or run["decisions"] != 512:
            raise ValueError("Cargo comparison requires the full development budget")
        if engine is not None and engine != run["engine_sha256"]:
            raise ValueError("Cargo comparison engines differ")
        engine = run["engine_sha256"]
        controller = "passenger-and-mail" if run["kind"] == "native-live-coordinated-passenger-mail-development" else run["controller"]
        matrices.setdefault(controller, []).append(run["seed"])
        entry = {"controller": controller, "map_seed": run["seed"], "status": run["status"], "path": str(root.resolve())}
        trace = root / "worker/transitions.jsonl"
        hashes[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
        if trace.exists():
            hashes[str(trace.resolve())] = hashlib.sha256(trace.read_bytes()).hexdigest()
        if run["status"] == "completed":
            rows = [json.loads(line) for line in trace.read_text().splitlines()]
            if not rows or any(row["decision"] != i+1 or row["company_id"] != 0 or
                row["tick_after"] - row["tick_before"] != 128 or
                (i and row["tick_before"] != rows[i-1]["tick_after"]) for i, row in enumerate(rows)):
                raise ValueError("Native cargo trace is discontinuous")
            final = run["final_observation"]
            if not (final["terminal"] or final["truncated"]) or (not final["terminal"] and len(rows) != 512):
                raise ValueError("Cargo episode has not reached its native boundary")
            summary = summarize_mail(rows, {"economy": rows[0]["before"], "tick": rows[0]["tick_before"]}, final)
            if any(run["summary"][key] != value for key, value in summary.items()):
                raise ValueError("Native cargo economics differ from the original summary")
            both = len(summary["windows"]) == 4 and all(w["mail"] > 0 and w["passengers"] > 0 and
                w["operating_profit"] > 0 and w["decisions"] == 128 for w in summary["windows"][-3:])
            entry.update(summary=summary, sustained_both_services=both)
        else:
            entry["error"] = run.get("error", "run not completed")
        cases.append(entry)
    values = [sorted(m) for m in matrices.values()]
    if not values or any(len(m) != len(set(m)) or m != values[0] for m in values):
        raise ValueError("Cargo controllers require the same unique map matrix")
    args.output.mkdir(parents=True, exist_ok=False)
    capture_source(args.output / "source")
    report = {"source": source_identity(), "engine_sha256": engine,
              "claim": "Descriptive paired development maps; scripted integration, not learned mail control or broad transport competence",
              "source_sha256": hashes, "cases": cases}
    write_json(args.output / "comparison.json", report)
    lines = ["# Live passenger/mail comparison", "", report["claim"], "",
        "| Controller | Map seed | Passengers | Mail | Operating profit | Net capital | Cash after capital | Sustained mail / both | Invalid / bankrupt |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |"]
    for row in cases:
        if "summary" not in row:
            lines.append(f"| {row['controller']} | {row['map_seed']} | FAILED | — | — | — | — | — | — |")
            continue
        s = row["summary"]
        lines.append(f"| {row['controller']} | {row['map_seed']} | {s['passengers']:,} | {s['mail']:,} | "
            f"{s['operating_profit']:,} | {s['net_capital_spend']:,} | {s['cash_result_excluding_financing']:,} | "
            f"{s['sustained_mail_service']} / {row['sustained_both_services']} | {s['invalid_actions']} / {int(s['bankruptcy'])} |")
    lines += ["", "Every complete run has 512 actions × 128 ticks. The scripts use only public state and exposed legal candidates.",
        "Mail is produced by the native towns: no injected packets, station-acceptance overrides, or fixture SERVICE command.",
        "Cash excludes loan-principal flows and includes construction and other expenses. Positive operating profit does not imply construction has been repaid.",
        "Sustained service requires delivery and positive combined native operating profit in each of the final three 128-action windows.",
        "The cargo schema currently rejects the old bus neural tensor interface. These results demonstrate native scripted transport integration."]
    for row in cases:
        if "error" in row:
            lines += ["", f"Failed {row['controller']} / {row['map_seed']}: {row['error']}"]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
