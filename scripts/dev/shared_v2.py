#!/usr/bin/env python3
"""Bounded two-company identity, ownership and timing check on one native map."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from infer_v2 import checked_tensors
from live_v2 import LiveV2
from local import capture_source, source_identity, write_json


def check_private_company_fields(response, observation):
    metadata = json.loads(Path(response["tensors"]["observation"]).read_text())
    data = (Path(response["tensors"]["observation"]).parent / metadata["binary"]["file"]).read_bytes()
    sections = {section["name"]: section for section in metadata["sections"]}
    start = sections["entities.companies.values"]["offset"]
    mask = sections["entities.companies.mask"]["offset"]
    own = 0
    for index in range(15):
        if not data[mask + index]:
            continue
        row = struct.unpack_from("<32f", data, start + index * 128)
        if row[1] == 1:
            own += 1
            if abs(row[0] - observation["company_id"] / 14) > 1e-7:
                raise ValueError("Tensor ownership marker refers to another company")
            if abs(row[2] - observation["economy"]["balance"] / 1e9) > 1e-7:
                raise ValueError("Tensor company finances differ from scoped observation")
        elif any(row[2:]):
            raise ValueError("Opponent private finances leaked into public tensors")
    if own != 1:
        raise ValueError("Tensor view must identify exactly one own company")


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-v2-shared-company-smoke", "status": "running", "source": source_identity(),
              "first_company": args.first_company, "global_decisions": 8, "decisions_per_company": 4,
              "ticks_per_global_decision": 128, "transitions": [],
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "claim": "Two scoped controllers in one simulation; identity/timing test, not a competitive learning result"}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    game = None
    start_keys = {}
    cross_company_checks = 0
    try:
        game = LiveV2(args.openttd, root / "worker", companies=2, first_company=args.first_company, decisions=8)
        for step in range(8):
            company = (args.first_company + step) % 2
            obs = game.request("OBSERVE", company_id=company)["observation"]
            if obs["company_id"] != company or obs["decisions"] != step:
                raise ValueError("Native actor identity/decision differs")
            reject = game.request("OBSERVE", company_id=1 - company)
            if reject.get("reason") != "COMPANY_TURN" or reject["tick"] != obs["tick"]:
                raise ValueError("Out-of-turn observation advanced time or escaped company scope")
            tensors = game.request("TENSORS", company_id=company)
            checked_tensors(tensors, obs)
            check_private_company_fields(tensors, obs)
            own_vehicles = {vehicle["id"] for vehicle in obs["vehicles"]}
            own_depots = {depot["tile"] for depot in obs["depots"]}
            for candidate in obs["candidates"]:
                family, params = candidate["family"], candidate["parameters"]
                if family in ("SET_ROUTE", "START_VEHICLE", "STOP_VEHICLE", "SEND_TO_DEPOT", "SELL_VEHICLE") and params[1] not in own_vehicles:
                    raise ValueError("Candidate refers to an opponent vehicle")
                if family == "BUY_BUS" and params[1] not in own_depots:
                    raise ValueError("Candidate refers to an opponent depot")
                if family == "START_VEHICLE":
                    start_keys[company] = candidate["key"]
            if 1 - company in start_keys:
                reject = game.request("ACT", company_id=company, token=obs["token"], candidate=start_keys[1 - company])
                if reject.get("reason") != "ILLEGAL_CANDIDATE" or reject["tick"] != obs["tick"]:
                    raise ValueError("Opponent vehicle command escaped the legal-action boundary")
                cross_company_checks += 1
            if game.request("OBSERVE", company_id=company)["observation"] != obs:
                raise ValueError("Read/rejected command changed native state")
            family = "BUILD_ROAD_DEPOT" if not obs["depots"] else "BUY_BUS" if not obs["vehicles"] else "WAIT"
            candidates = [candidate for candidate in obs["candidates"] if candidate["family"] == family]
            if not candidates:
                raise ValueError(f"No legal scoped {family}")
            action = game.request("ACT", company_id=company, token=obs["token"], candidate=candidates[0]["key"])
            if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise ValueError("Scoped construction failed")
            response = game.request("STEP", company_id=company)
            transition = response["transition"]
            if transition["company_id"] != company or transition["tick_after"] - transition["tick_before"] != 128 or response["next_company"] != 1 - company:
                raise ValueError("Shared scheduler violated company/tick budget")
            record["transitions"].append(transition)
        final = [game.request("OBSERVE", company_id=i)["observation"] for i in range(2)]
        if not cross_company_checks or any(len(obs["depots"]) != 1 or len(obs["vehicles"]) != 1 for obs in final):
            raise ValueError("Two-company construction/isolation check incomplete")
        if set(v["id"] for v in final[0]["vehicles"]) & set(v["id"] for v in final[1]["vehicles"]):
            raise ValueError("Company observations share own vehicle identity")
        game.close(); game = None
        record.update(status="passed", cross_company_rejections=cross_company_checks, final_observations=final,
                      native_result=json.loads((root / "worker/artifacts/live-result.json").read_text()))
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if game is not None:
            game.abort()
        write_json(root / "run.json", record)
    print(f"Two-company native check: {root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-company", type=int, choices=(0, 1), default=0)
    run(parser.parse_args())
