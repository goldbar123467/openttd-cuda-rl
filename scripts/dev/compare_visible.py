#!/usr/bin/env python3
"""Compare the GUI controller at decision boundaries with the headless policy."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from export_live import compare, require
from local import ROOT, write_json
from play_live import native_screenshot


def run(visible, reference):
    report = json.loads((visible / "inspection.json").read_text())
    require(report["status"] == "COMPLETE", "Visible controller is not complete")
    actual = [json.loads(line) for line in (visible / "actions.jsonl").read_text().splitlines()]
    expected = [json.loads(line) for line in (reference / "actions.jsonl").read_text().splitlines()]
    require(len(actual) == len(expected) == report["action_count"], "Visible/headless decision counts differ")
    tolerance = json.loads((ROOT / "config/v1/m10-model-package-contract.json").read_text())["tolerances"]
    maximum = {key: 0. for key in ("logits", "probabilities", "value")}
    for index, (gui, native) in enumerate(zip(actual, expected, strict=True)):
        require(gui["transition_ordinal"] == index and gui["legal_mask"] == native["legal"], "Visible observation boundary or mask differs")
        prediction = SimpleNamespace(action=gui["current_action"]["index"], value=gui["value"],
                                     logits=gui["policy_logits"], probabilities=gui["masked_probabilities"])
        for key, error in compare(SimpleNamespace(**native["prediction"]), prediction, tolerance).items():
            maximum[key] = max(maximum[key], error)
        require(index == 0 or gui["tick"] - actual[index - 1]["tick"] == 128, "Visible decision tick interval differs")
        # M11 reports just after issuing the command, before its following 128
        # ticks. Passenger and operating counters correspond to M06's pre-state.
        for gui_key, native_key in (("delivered_passengers", "delivered_passengers_total"),
                                    ("income", "operating_income_total"), ("expenses", "operating_expenses_total")):
            require(gui["reward_relevant_state"][gui_key] == native["source"]["pre"][native_key],
                    f"Visible economic counter differs at decision {index}: {gui_key}")
    screenshot = native_screenshot(visible)
    result = {"status": "passed", "visible": str(visible), "reference": str(reference), "decisions": len(actual),
              "exact_actions_masks_delivery_income_expense_counters": True, "maximum_absolute_errors": maximum,
              "screenshot": str(screenshot), "screenshot_dimensions": [1280, 800],
              "boundary": "GUI after-command/pre-advance counters versus headless pre-state; not an extra completed 128-tick interval"}
    write_json(visible / "comparison.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visible", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    run(args.visible.resolve(), args.reference.resolve())
