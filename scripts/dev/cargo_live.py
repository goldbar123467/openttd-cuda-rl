#!/usr/bin/env python3
"""Natural mail service using public live candidates and ordinary native steps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from live_v2 import LiveV2, canonical, reset_manifest
from local import capture_source, positive, source_identity, write_json
from service_v2 import ServicePolicy

SCHEMA = "openttd-rl-development-v2-cargo-live-1"


class CargoV2(LiveV2):
    """Reuse the existing bounded wire transport with an explicit cargo launch.

    Startup is separate while the bus collector/source is frozen for the
    concurrently running checkpoint experiment. No bus module global is changed.
    """
    def __init__(self, engine, output, *, seed=None, split="training", decisions=512):
        self.engine, self.output = Path(engine).resolve(), Path(output).resolve()
        if type(decisions) is not int or not 1 <= decisions <= 512:
            raise ValueError("Cargo decision budget must be 1..512")
        self.schema = SCHEMA
        manifest = reset_manifest(self.engine, self.engine.parent / "baseset/opengfx-8.0.tar", seed, split)
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / "artifacts").mkdir()
        (self.output / "openttd.cfg").write_text("\n")
        (self.output / "reset.json").write_bytes(canonical(manifest) + b"\n")
        input_child, self.input = os.pipe()
        self.output_fd, output_child = os.pipe()
        config = {"schema_version": self.schema, "company_id": 0, "input_fd": input_child,
                  "output_fd": output_child, "maximum_decisions": decisions, "step_ticks": 128}
        (self.output / "live.json").write_bytes(canonical(config) + b"\n")
        self.request_id = 0
        self.events = (self.output / "requests.jsonl").open("x")
        command = [str(self.engine), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null",
                   "-c", str(self.output / "openttd.cfg"), "-V", str(self.output / "reset.json"),
                   "-U", str(self.output / "reset-projection.json"), "-E", str(self.output / "live.json"),
                   "-F", str(self.output / "transitions.jsonl"), "-H", str(self.output / "artifacts")]
        try:
            with (self.output / "openttd.log").open("x") as log:
                self.process = subprocess.Popen(command, cwd=self.output, pass_fds=(input_child, output_child),
                                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        except BaseException:
            for descriptor in (self.input, self.output_fd):
                os.close(descriptor)
            self.events.close()
            raise
        finally:
            os.close(input_child)
            os.close(output_child)


def mail_planner_view(observation):
    """Reuse the cargo-agnostic road planner, preserving native candidate keys.

    This is a script's local naming adapter, never a neural observation. Actual
    submitted keys, public observations and native traces retain mail identities.
    """
    if observation["schema_version"] != SCHEMA or observation["action_schema_id"] != "v2-development-passenger-mail-action-1":
        raise ValueError("Mail planner requires the explicit cargo public schema")
    candidates = []
    for candidate in observation["candidates"]:
        if candidate["family"] in ("BUILD_BUS_STOP", "BUY_BUS"):
            continue
        projected = dict(candidate)
        if candidate["family"] == "BUILD_TRUCK_STOP":
            projected.update(family="BUILD_BUS_STOP", parameters=[*candidate["parameters"]],
                             passenger_acceptance_eighths=candidate["mail_acceptance_eighths"],
                             passenger_production=candidate["mail_production"])
            projected["parameters"][3] = 0
        elif candidate["family"] == "BUY_MAIL_TRUCK":
            projected["family"] = "BUY_BUS"
        candidates.append(projected)
    return {**observation, "map": {**observation["map"],
            "bus_stop_catchment_radius": observation["map"]["truck_stop_catchment_radius"]},
            "vehicles": [v for v in observation["vehicles"] if v["cargo_label"] == "MAIL"],
            "candidates": candidates}


def summarize_mail(rows, initial, final):
    capital_families = {"BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_TRUCK_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS", "BUY_MAIL_TRUCK", "SELL_VEHICLE"}
    def capital(selected):
        return sum(c["cost"] for row in selected if row["action"]["family"] in capital_families
                   for c in row["action"]["native_commands"] if c["phase"] == "EXECUTE" and c["status"] == "SUCCESS")
    def economics(selected):
        before, after = selected[0]["before"], selected[-1]["after"]
        cash = after["balance"] - before["balance"] - (after["loan"] - before["loan"])
        spend = capital(selected)
        return {"mail": after.get("delivered_mail", before["delivered_mail"]) - before["delivered_mail"],
                "passengers": after.get("delivered_passengers", before["delivered_passengers"]) - before["delivered_passengers"],
                "operating_profit": after.get("operating_profit", before["operating_profit"]) - before["operating_profit"],
                "net_capital_spend": spend, "cash_result_excluding_financing": cash,
                "cash_result_before_capital": cash + spend}
    windows = [{"decisions": len(rows[i:i+128]), **economics(rows[i:i+128])} for i in range(0, len(rows), 128)]
    return {"schema_version": "development-live-mail-economics-1", **economics(rows),
            "decisions": len(rows), "simulation_ticks": final["tick"] - initial["tick"], "windows": windows,
            "invalid_actions": sum(r["action"]["status"] not in ("SUCCESS", "NO_OP") for r in rows),
            "bankruptcy": final["terminal"],
            "sustained_mail_service": len(windows) == 4 and all(w["mail"] > 0 and w["operating_profit"] > 0 for w in windows[-3:])}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-live-mail-development", "status": "running", "source": source_identity(),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "split": args.split, "seed": args.seed, "decisions": args.decisions, "controller": args.controller,
              "hypothesis": "Exposed native truck stops and a mail vehicle can deliver naturally generated mail using the existing public road planner.",
              "claim": "Scripted real sequential mail interaction; no injected cargo or acceptance, neural mail learning, or shared mail game"}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    game = None
    started = time.monotonic()
    try:
        game = CargoV2(args.openttd, root / "worker", seed=args.seed, split=args.split, decisions=args.decisions)
        initial = game.request("OBSERVE")["observation"]
        if initial != game.request("OBSERVE")["observation"]:
            raise RuntimeError("Cargo observation mutated native state")
        if any(c["family_index"] != c["parameters"][0] for c in initial["candidates"]):
            raise RuntimeError("Public cargo family and parameter identity differ")
        if len(initial["candidates"]) > initial["capabilities"]["maximum_candidates"]:
            raise RuntimeError("Cargo candidate budget exceeded")
        checks = [(game.request("OBSERVE", company_id=1), "COMPANY_SCOPE"),
                  (game.request("STEP"), "NO_PENDING_ACTION"),
                  (game.request("ACT", token="stale", candidate=initial["candidates"][0]["key"]), "STALE_TOKEN"),
                  (game.request("ACT", token=initial["token"], candidate="not-exposed"), "ILLEGAL_CANDIDATE")]
        if any(value["status"] != "REJECTED" or value.get("reason") != reason or value["tick"] != initial["tick"]
               for value, reason in checks) or game.request("OBSERVE")["observation"] != initial:
            raise RuntimeError("Cargo protocol rejection changed state or lost its reason")
        record["initial_boundary_checks"] = [reason for _, reason in checks]
        rejection = game.request("TENSORS")
        if rejection.get("reason") != "CARGO_TENSORS_NOT_IMPLEMENTED" or rejection["tick"] != initial["tick"]:
            raise RuntimeError("Cargo mode must reject incompatible bus tensors without advancing time")
        if args.controller == "mail":
            policy = ServicePolicy(mail_planner_view(initial), repay=True, minimum_length=12, planner="graph", site_checks=True)
            write_json(root / "plan.json", {"kind": "mail-public-road-plan", "plan": policy.plan})
        else:
            policy = None
        rows = []
        for i in range(args.decisions):
            observation = initial if i == 0 else game.request("OBSERVE")["observation"]
            candidate = policy.choose(mail_planner_view(observation)) if policy else next(c for c in observation["candidates"] if c["family"] == "WAIT")
            actual = next(c for c in observation["candidates"] if c["key"] == candidate["key"])
            result = game.request("ACT", token=observation["token"], candidate=actual["key"])
            if result["status"] != "OK" or result["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise RuntimeError("Exposed cargo action failed: " + str(result))
            if result["action"]["family"] != actual["family"] or result["action"]["parameters"] != actual["parameters"]:
                raise RuntimeError("Native execution differs from the exposed cargo candidate")
            if i == 0:
                duplicate = game.request("ACT", token=observation["token"], candidate=actual["key"])
                if duplicate.get("reason") != "DECISION_BOUNDARY" or duplicate["tick"] != observation["tick"]:
                    raise RuntimeError("Cargo accepted two actions before a step")
            transition = game.request("STEP")["transition"]
            if transition["tick_after"] - transition["tick_before"] != 128:
                raise RuntimeError("Cargo tick budget differs")
            rows.append(transition)
            if i < 16 or (i + 1) % 128 == 0:
                print(json.dumps({"decision": i + 1, "family": actual["family"], "economy": transition["after"]}), flush=True)
            if transition["terminal"]:
                break
        final = game.request("OBSERVE")["observation"]
        if not (final["terminal"] or final["truncated"]):
            raise RuntimeError("Cargo evaluation did not reach the native episode boundary")
        game.close(); game = None
        record.update(status="completed", summary=summarize_mail(rows, initial, final), final_observation=final)
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
    parser.add_argument("--seed", type=int)
    parser.add_argument("--split", choices=("training", "development"), default="training")
    parser.add_argument("--decisions", type=positive, default=512)
    parser.add_argument("--controller", choices=("wait", "mail"), default="mail")
    run(parser.parse_args())
