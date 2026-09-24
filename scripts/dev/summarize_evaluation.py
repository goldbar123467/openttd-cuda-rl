#!/usr/bin/env python3
"""Read completed or running development evaluations without touching the game."""
import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    for path in sorted(args.run.glob("*/episode.json")):
        episode = json.loads(path.read_text())
        if episode["status"] == "completed":
            print(json.dumps({key: episode[key] for key in (
                "policy", "template_id", "sampling_seed", "passengers", "operating_profit",
                "operating_profit_less_capital", "first_delivery_action", "invalid_actions", "bankruptcy",
                "final_buses", "final_routes", "action_counts", "service_in_all_final_three_windows")}))
        else:
            trace = path.parent / "actions.jsonl"
            rows = []
            if trace.exists():
                for line in trace.read_text().splitlines():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        break  # A running writer may have an incomplete final line.
            print(json.dumps({"episode": path.parent.name, "status": episode["status"],
                              "steps": len(rows), "actions": dict(Counter(row["action"] for row in rows)),
                              "error": episode.get("error")}))


if __name__ == "__main__":
    main()
