#!/usr/bin/env python3
"""Operate a passenger bus and mail truck together using public live primitives."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from cargo_live import CargoV2, SCHEMA, mail_planner_view, summarize_mail
from local import capture_source, positive, source_identity, write_json
from service_v2 import ServicePolicy


def protect_existing_infrastructure(observation):
    """A legal road command may clear a stop. Keep existing service sites intact."""
    protected = {site["tile"] for key in ("stations", "depots") for site in observation[key]}
    protected.update(tile for site in observation["stations"] for key in ("bus_stop_tiles", "truck_stop_tiles") for tile in site.get(key, []))
    construction = {"BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_TRUCK_STOP", "BUILD_ROAD_DEPOT"}
    return {**observation, "map": {**observation["map"],
            "roads": [row for row in observation["map"]["roads"] if row[0] not in protected],
            "clear_tiles": [tile for tile in observation["map"]["clear_tiles"] if tile not in protected]},
            "candidates": [c for c in observation["candidates"] if c["family"] not in construction or c["parameters"][1] not in protected]}


def passenger_view(observation):
    if observation["schema_version"] != SCHEMA:
        raise ValueError("Coordinated service requires the live cargo schema")
    observation = protect_existing_infrastructure(observation)
    return {**observation, "stations": facility_stations(observation, "bus_stop_tiles"),
            "vehicles": [v for v in observation["vehicles"] if v["cargo_label"] == "PASS"],
            "candidates": [c for c in observation["candidates"] if c["family"] not in ("BUILD_TRUCK_STOP", "BUY_MAIL_TRUCK")]}


def facility_stations(observation, field):
    if not observation.get("capabilities", {}).get("station_facility_tiles"):
        raise ValueError("Coordinated service needs public station facility tile lists")
    return [{**station, "tile": tile} for station in observation["stations"] for tile in station[field]]


def coordinated_mail_view(observation):
    view = mail_planner_view(protect_existing_infrastructure(observation))
    return {**view, "stations": facility_stations(observation, "truck_stop_tiles")}


class CoordinatedService:
    def __init__(self, observation):
        self.phase = "passengers"
        self.bus = ServicePolicy(passenger_view(observation), repay=False, minimum_length=12, planner="graph", site_checks=True)
        self.mail = None

    @staticmethod
    def running(observation, cargo):
        return any(v["cargo_label"] == cargo and not v["stopped"] and len(v["orders"]) == 2 for v in observation["vehicles"])

    def choose(self, observation):
        if self.phase == "passengers":
            if not self.running(observation, "PASS"):
                return self.bus.choose(passenger_view(observation))
            self.phase = "mail"
            self.mail = ServicePolicy(coordinated_mail_view(observation), repay=False,
                                      minimum_length=12, planner="graph", site_checks=True)
        if self.phase == "mail":
            if not self.running(observation, "MAIL"):
                return self.mail.choose(coordinated_mail_view(observation))
            self.phase = "operate-and-repay"
        payments = [c for c in observation["candidates"] if c["family"] == "MANAGE_LOAN" and c["parameters"][1:3] == [2, 10000]]
        if payments and observation["economy"]["balance"] >= 20000 and observation["economy"]["loan"] >= 10000:
            return payments[0]
        return next(c for c in observation["candidates"] if c["family"] == "WAIT")


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-live-coordinated-passenger-mail-development", "status": "running",
              "source": source_identity(), "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "split": args.split, "seed": args.seed, "decisions": args.decisions,
              "planner_version": "protect-and-locate-station-facilities-v3",
              "hypothesis": "Sequential bus and mail plans can coexist and both deliver cargo through ordinary legal actions.",
              "criterion": "Both cargo types delivered in each final 128-decision window with positive combined operating profit, no invalid action or bankruptcy.",
              "claim": "Public scripted transport integration; no neural mail control, artificial cargo, shared companies, or optimal coordination claim",
              "phase_changes": []}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    game = None
    start = time.monotonic()
    try:
        game = CargoV2(args.openttd, root / "worker", seed=args.seed, split=args.split, decisions=args.decisions)
        initial = game.request("OBSERVE")["observation"]
        policy = CoordinatedService(initial)
        write_json(root / "passenger-plan.json", policy.bus.plan)
        rows = []
        for i in range(args.decisions):
            observation = initial if i == 0 else game.request("OBSERVE")["observation"]
            before_phase = policy.phase
            selected = policy.choose(observation)
            if before_phase != policy.phase:
                record["phase_changes"].append({"decision": i + 1, "phase": policy.phase})
                write_json(root / "run.json", record)
                if policy.mail is not None and not (root / "mail-plan.json").exists():
                    write_json(root / "mail-plan.json", policy.mail.plan)
            actual = next(c for c in observation["candidates"] if c["key"] == selected["key"])
            response = game.request("ACT", token=observation["token"], candidate=actual["key"])
            if response["status"] != "OK" or response["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise RuntimeError("Coordinated native action failed: " + str(response))
            if response["action"]["parameters"] != actual["parameters"] or response["action"]["family"] != actual["family"]:
                raise RuntimeError("Coordinated execution differs from exposed candidate")
            transition = game.request("STEP")["transition"]
            if transition["tick_after"] - transition["tick_before"] != 128:
                raise RuntimeError("Coordinated service changed the tick budget")
            rows.append(transition)
            if i < 20 or (i + 1) % 128 == 0:
                print(json.dumps({"decision": i + 1, "phase": policy.phase, "family": actual["family"], "economy": transition["after"]}), flush=True)
            if transition["terminal"]:
                break
        final = game.request("OBSERVE")["observation"]
        if not (final["terminal"] or final["truncated"]):
            raise RuntimeError("Coordinated service did not reach its native boundary")
        game.close(); game = None
        summary = summarize_mail(rows, initial, final)
        summary["both_services_in_final_three_windows"] = len(summary["windows"]) == 4 and all(
            w["decisions"] == 128 and w["mail"] > 0 and w["passengers"] > 0 and w["operating_profit"] > 0 for w in summary["windows"][-3:])
        summary["acceptance_passed"] = summary["both_services_in_final_three_windows"] and not summary["bankruptcy"] and not summary["invalid_actions"]
        record.update(status="completed", summary=summary, final_observation=final)
        write_json(root / "summary.json", summary)
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if game is not None:
            game.abort()
        record["wall_seconds"] = time.monotonic() - start
        write_json(root / "run.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--split", choices=("training", "development"), default="training")
    parser.add_argument("--decisions", type=positive, default=512)
    run(parser.parse_args())
