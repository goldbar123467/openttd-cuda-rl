#!/usr/bin/env python3
"""Measure uniform and fixed-order scripts under the identical public planner mask."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

from guide_v2 import GUIDANCE, GUIDANCES, PublicPlanGuide
from infer_v2 import checked_tensors
from live_v2 import LiveV2
from live_v2_artifacts import archive_tensors
from local import capture_source, positive, source_identity, write_json
from service_v2 import summarize


def run(args):
    guidance_name = getattr(args, "guidance", GUIDANCE)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-v2-guided-baseline", "status": "running",
              "source": source_identity(), "guidance": guidance_name, "controller": args.controller,
              "sampling_seed": args.seed, "map_seed": args.map_seed, "split": args.split,
              "decisions": args.decisions, "final_evaluation_accessed": False,
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "claim": "Planner-assisted baseline; no learned route construction or policy optimization"}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    game = None
    started = time.monotonic()
    rng = random.Random(args.seed)
    try:
        game = LiveV2(args.openttd, root / "worker", seed=args.map_seed,
                      split=args.split, decisions=args.decisions)
        initial = game.request("OBSERVE")["observation"]
        guide = PublicPlanGuide(initial, root / "worker", guidance=guidance_name)
        transitions = []
        with (root / "choices.jsonl").open("x") as choices:
            for decision in range(args.decisions):
                observation = game.request("OBSERVE")["observation"]
                tensors = game.request("TENSORS")
                _, candidate_path, candidates, mask = checked_tensors(tensors, observation)
                _, mask, guidance = guide.prepare(observation, candidate_path, candidates, mask)
                rows = [row for row, allowed in enumerate(mask) if allowed]
                if args.controller == "uniform":
                    row = rng.choice(rows)
                    probability = 1 / len(rows)
                else:
                    row = next(row for row in rows if candidates[row]["stable_key"] == guide.proposal)
                    # The original script builds first. The repay-first control
                    # prioritizes repayment whenever the identical public mask
                    # offers it, then resumes construction without extra WAITs.
                    if args.controller == "repay-first" or guide.families[candidates[row]["family_index"]] == "WAIT":
                        row = next((i for i in rows if guide.families[candidates[i]["family_index"]] == "MANAGE_LOAN"), row)
                    probability = 1.0
                selected = candidates[row]
                action = game.request("ACT", token=observation["token"], candidate=selected["stable_key"])
                if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                    raise RuntimeError("Guided baseline action failed at native boundary")
                guide.commit(selected["stable_key"])
                transition = game.request("STEP")["transition"]
                if transition["tick_after"] - transition["tick_before"] != 128:
                    raise RuntimeError("Guided baseline changed simulation-time budget")
                transitions.append(transition)
                choices.write(json.dumps({"decision": decision + 1, "candidate": selected,
                    "probability": probability, "guidance": guidance, "transition": transition}) + "\n")
                choices.flush()
                if decision < 8 or (decision + 1) % 128 == 0:
                    print(json.dumps({"decision": decision + 1, "family": action["action"]["family"],
                                      "economy": transition["after"]}), flush=True)
                if transition["terminal"]:
                    break
        final = game.request("OBSERVE")["observation"]
        if not (final["terminal"] or final["truncated"]):
            raise RuntimeError("Baseline did not reach its native episode boundary")
        game.close(); game = None
        archive_tensors(root / "worker")
        record.update(status="completed", summary=summarize(transitions, initial, final), final_observation=final)
        write_json(root / "summary.json", record["summary"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if game is not None:
            game.abort()
        record["wall_seconds"] = time.monotonic() - started
        write_json(root / "run.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controller", choices=("uniform", "scripted", "repay-first"), required=True)
    parser.add_argument("--seed", type=positive, default=20260923)
    parser.add_argument("--map-seed", type=int)
    parser.add_argument("--split", choices=("training", "development"), default="development")
    parser.add_argument("--decisions", type=positive, default=512)
    parser.add_argument("--guidance", choices=GUIDANCES, default=GUIDANCE)
    run(parser.parse_args())
