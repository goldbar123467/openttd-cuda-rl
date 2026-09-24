#!/usr/bin/env python3
"""Official-SDK MCP adapter for a scoped player versus a saved live V2 policy."""
import argparse
from collections import Counter
from contextlib import asynccontextmanager
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import threading
import time

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from infer_v2 import PolicyClient, checked_tensors, financial_features_mode
from guide_v2 import GUIDANCE, PublicPlanGuide
from live_v2 import LiveV2, SHARED_SCHEMA
from local import capture_source, source_identity, write_json
from live_v2_artifacts import archive_tensors
from report_shared_v2 import report as economic_report


class Match:
    def __init__(self, args):
        if args.decisions % 2 or not 2 <= args.decisions <= 512:
            raise ValueError("Match needs an even global action budget in 2..512")
        training = json.loads((args.training_run / "run.json").read_text())
        if training["kind"] != "native-v2-live-recurrent-ppo" or training["status"] != "completed" or training.get("observation_schema_id") != "v2-m15-public-development-v2":
            raise ValueError("Opponent requires completed compatible live PPO weights")
        self.guidance_name = training.get("guidance", "none")
        if self.guidance_name not in ("none", GUIDANCE):
            raise ValueError("MCP opponent weights use an unsupported planner curriculum")
        self.financial_features = financial_features_mode(training.get("financial_features", "raw"))
        if training["model"].get("financial_features", "raw") != self.financial_features:
            raise ValueError("MCP model and training financial preprocessing differ")
        self.guide = None
        self.weights = args.training_run.resolve() / "inference-weights.pt"
        if str(self.weights) != training["model"]["path"] or hashlib.sha256(self.weights.read_bytes()).hexdigest() != training["model"]["sha256"]:
            raise ValueError("Opponent model path/hash differs")
        self.args, self.root = args, args.output.resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        capture_source(self.root / "source")
        self.record = {"kind": "native-v2-mcp-shared-match", "status": "ready", "source": source_identity(),
            "mcp_sdk": importlib.metadata.version("mcp"), "interface": SHARED_SCHEMA,
            "controllers": {str(args.company): args.player_label, str(1 - args.company):
                "native-recurrent-neural" + ("+public-planner" if self.guidance_name != "none" else "")},
            "neural_guidance": self.guidance_name,
            "neural_financial_features": self.financial_features,
            "global_decisions": args.decisions, "per_company_action_budget": args.decisions // 2,
            "ticks_per_global_decision": 128, "first_company": args.first_company,
            "split": args.split, "map_seed": args.map_seed, "sampling_seed": args.sampling_seed,
            "model": training["model"], "training_run": str(args.training_run.resolve()),
            "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
            "policy_binary_sha256": hashlib.sha256(args.policy.read_bytes()).hexdigest(),
            "financial_inference_cost_usd": None, "cost_note": "No provider billing telemetry supplied; unknown is not zero",
            "archived_neural_observations": 0,
            "claim": "MCP transport and shared gameplay; an LLM claim additionally needs actual controller provenance"}
        self.game = self.policy = None
        self.current = args.first_company
        self.decisions = 0
        self.pending = False
        self.started = self.finished = False
        self.final = None
        self.turn_started_ns = None
        self.lock = threading.RLock()
        self.log = (self.root / "mcp-tools.jsonl").open("x")
        self.neural_log = (self.root / "neural-actions.jsonl").open("x")
        self.persist()

    def persist(self):
        write_json(self.root / "run.json", self.record)

    def invoke(self, name, arguments, function):
        with self.lock:
            started = time.monotonic_ns()
            entry = {"tool": name, "arguments": arguments, "started_monotonic_ns": started}
            try:
                result = function()
                entry["result"] = result
                return result
            except BaseException as exc:
                entry["error"] = str(exc)
                if isinstance(exc, ValueError):
                    raise ToolError(str(exc)) from exc
                self.record.update(status="failed", error=str(exc)); self.persist()
                raise
            finally:
                entry["elapsed_ns"] = time.monotonic_ns() - started
                self.log.write(json.dumps(entry, allow_nan=False) + "\n")
                self.log.flush()

    def info(self):
        return {"schema_version": "openttd-rl-development-mcp-1", "company_id": self.args.company,
            "status": self.record["status"], "global_decisions_completed": self.decisions,
            "pending_action_requires_step": self.pending,
            "action_budget_per_company": self.args.decisions // 2, "ticks_per_global_decision": 128,
            "schedule": "Alternating companies; one native action and 128 ticks per turn. Both economies advance together.",
            "information": "Current public map and own company; no reset seeds, RNG, future breakdown timers or opponent private finances.",
            "timeout": "Native 60-second idle timeout aborts without advancing simulation; no automatic victory claim.",
            "workflow": "start_match, observe/map_region, legal_actions, submit_action, step; step also runs the opponent turn. WAIT batches are limited to eight own turns per call.",
            "road_geometry": {"tile": "x + map_width * y", "road_bits": {"x_axis": 10, "y_axis": 5},
                "entrance_directions": {"0": "negative x", "1": "positive y", "2": "positive x", "3": "negative y"}},
            "parameters": {"BUILD_ROAD_PATH": "[family, tile, road_bits, 1]", "BUILD_BUS_STOP": "[family, tile, entrance_direction]",
                "BUILD_ROAD_DEPOT": "[family, tile, entrance_direction]", "BUY_BUS": "[family, depot_tile, engine_id]",
                "SET_ROUTE": "[family, owned_vehicle_id, owned_origin_station_id, owned_destination_station_id]",
                "START_VEHICLE": "[family, owned_vehicle_id]", "MANAGE_LOAN": "[family, 1=borrow or 2=repay, 10000]"},
            "model_sha256": self.record["model"]["sha256"]}

    def start(self, include_map=True):
        if self.started:
            raise ValueError("A server permits exactly one match; resets would change the registered scenario")
        self.started = True
        try:
            self.policy = PolicyClient(self.args.policy.resolve(), self.root / "neural.log", self.args.device,
                self.args.sampling_seed, "sampled", self.weights, financial_features=self.financial_features)
            self.policy.check_financial_features()
            self.game = LiveV2(self.args.openttd, self.root / "worker", seed=self.args.map_seed,
                split=self.args.split, companies=2, first_company=self.current, decisions=self.args.decisions)
            self.record["status"] = "running"
            self.neural_turn()
            self.turn_started_ns = time.monotonic_ns()
            self.persist()
            return self.observe(include_map)
        except BaseException as exc:
            self.record.update(status="failed", error=str(exc)); self.persist()
            raise

    def observation(self):
        if not self.started:
            raise ValueError("Start the registered match first")
        if self.finished:
            return self.final
        response = self.game.request("OBSERVE", company_id=self.args.company)
        if response["status"] != "OK":
            raise RuntimeError("MCP player is outside its scheduled company turn")
        return response["observation"]

    def observe(self, include_map=True):
        observation = self.observation()
        return {**{key: value for key, value in observation.items()
                   if key != "candidates" and (include_map or key != "map")},
                "map_dimensions": {key: observation["map"][key] for key in ("width", "height")},
                "legal_action_counts": dict(Counter(c["family"] for c in observation["candidates"]))}

    def region(self, x, y, width, height):
        observation = self.observation()
        grid = observation["map"]
        if not (0 <= x < grid["width"] and 0 <= y < grid["height"] and
                1 <= width <= 32 and 1 <= height <= 32 and
                x + width <= grid["width"] and y + height <= grid["height"]):
            raise ValueError("Public map region must fit the map and have dimensions 1..32")
        def inside(tile):
            return x <= tile % grid["width"] < x + width and y <= tile // grid["width"] < y + height
        return {"company_id": self.args.company, "token": observation["token"],
                "map_width": grid["width"], "map_height": grid["height"],
                "bounds": {"x": x, "y": y, "width": width, "height": height},
                "bus_stop_catchment_radius": grid["bus_stop_catchment_radius"],
                **{key: [tile for tile in grid[key] if inside(tile)] for key in ("clear_tiles", "flat_tiles", "houses")},
                "roads": [road for road in grid["roads"] if inside(road[0])]}

    def legal(self, family, offset, limit, parameter1=None, minimum_acceptance=0, minimum_production=0, include_features=False):
        if not 0 <= offset <= 4096 or not 1 <= limit <= 64:
            raise ValueError("Candidate page must have offset 0..4096 and limit 1..64")
        observation = self.observation()
        candidates = [c for c in observation["candidates"] if family is None or c["family"] == family]
        candidates = [c for c in candidates if (parameter1 is None or c["parameters"][1] == parameter1)
            and c.get("passenger_acceptance_eighths", 0) >= minimum_acceptance
            and c.get("passenger_production", 0) >= minimum_production]
        page = candidates[offset:offset + limit]
        if not include_features:
            page = [{key: value for key, value in candidate.items() if key != "features"} for candidate in page]
        return {"company_id": self.args.company, "token": observation["token"], "total": len(candidates),
                "offset": offset, "candidates": page}

    def act(self, token, candidate_key):
        if self.pending:
            raise ValueError("An accepted action is pending; call step before submitting another action")
        if not self.started or self.finished:
            raise ValueError("Action requires a live decision boundary")
        response = self.game.request("ACT", company_id=self.args.company, token=token, candidate=candidate_key)
        if response["status"] == "OK":
            self.pending = True
            response["controller_wall_decision_ns"] = time.monotonic_ns() - self.turn_started_ns
            response["next_required_tool"] = "step"
        return response

    def native_step(self, company):
        response = self.game.request("STEP", company_id=company)
        if response["status"] != "OK":
            raise RuntimeError("Native shared step failed")
        transition = response["transition"]
        if transition["tick_after"] - transition["tick_before"] != 128 or transition["company_id"] != company:
            raise RuntimeError("Native shared time/identity boundary differs")
        self.decisions = transition["decision"]
        self.current = response["next_company"]
        if transition["terminal"] or transition["truncated"]:
            self.finish()
        return transition

    def neural_turn(self):
        if self.finished or self.current == self.args.company:
            return
        company = 1 - self.args.company
        observation = self.game.request("OBSERVE", company_id=company)["observation"]
        if self.guidance_name == GUIDANCE and self.guide is None:
            self.guide = PublicPlanGuide(observation, self.root / "worker")
        tensors = self.game.request("TENSORS", company_id=company)
        obs_path, candidate_path, candidates, mask = checked_tensors(tensors, observation)
        guidance = None
        if self.guide:
            candidate_path, mask, guidance = self.guide.prepare(observation, candidate_path, candidates, mask)
        started = time.monotonic_ns()
        prediction = self.policy.request(f"{obs_path}\t{candidate_path}")
        elapsed = time.monotonic_ns() - started
        if prediction["row"] not in candidates or not mask[prediction["row"]]:
            raise RuntimeError("Opponent selected an illegal native row")
        probabilities = prediction["probabilities"]
        if (len(probabilities) != 4096 or not all(math.isfinite(value) and value >= 0 for value in probabilities) or
            abs(sum(probabilities) - 1) > 1e-5 or any(probabilities[i] != 0 for i in range(4096) if not mask[i])):
            raise RuntimeError("Opponent probabilities do not respect the actual sampling mask")
        candidate = candidates[prediction["row"]]
        response = self.game.request("ACT", company_id=company, token=observation["token"], candidate=candidate["stable_key"])
        if response["status"] != "OK" or response["action"]["status"] not in ("SUCCESS", "NO_OP"):
            raise RuntimeError("Opponent native command failed")
        if self.guide:
            self.guide.commit(candidate["stable_key"])
        transition = self.native_step(company)
        self.neural_log.write(json.dumps({"decision": transition["decision"], "company_id": company,
            "candidate": candidate, "prediction": prediction, "guidance": guidance, "inference_elapsed_ns": elapsed}) + "\n")
        self.neural_log.flush()
        # These immutable snapshots have been consumed and the native world
        # advanced. Archive each here: the MCP SDK allows only a short shutdown
        # grace period, insufficient to compress an entire match on close.
        archive_tensors(self.root / "worker")
        self.record["archived_neural_observations"] += 1
        if self.finished:
            self.persist()

    def step(self):
        if not self.pending or self.finished:
            raise ValueError("Step requires an accepted player action")
        transition = self.native_step(self.args.company)
        self.pending = False
        self.neural_turn()
        self.turn_started_ns = time.monotonic_ns()
        return {"player_transition": transition, "match_complete": self.finished,
                "global_decisions_completed": self.decisions, "observation": self.observe(include_map=False)}

    def wait_turns(self, count):
        if self.pending:
            raise ValueError("An accepted action is pending; call step before waiting")
        if not 1 <= count <= min(8, self.args.decisions // 2):
            raise ValueError("Wait batches require 1..8 own turns within the registered budget at a decision boundary")
        result = None
        for _ in range(count):
            if self.finished:
                break
            observation = self.observation()
            candidate = next(c for c in observation["candidates"] if c["family"] == "WAIT")
            self.act(observation["token"], candidate["key"])
            result = self.step()
        return result

    def finish(self):
        self.final = self.game.request("OBSERVE", company_id=self.args.company)["observation"]
        self.game.close(); self.game = None
        result = json.loads((self.root / "worker/artifacts/live-result.json").read_text())
        self.record.update(status="completed", native_result=result, global_decisions_completed=self.decisions)
        self.record["summary"] = economic_report(self.root / "worker")
        write_json(self.root / "summary.json", self.record["summary"])
        self.finished = True
        self.persist()

    def close(self):
        if self.game:
            self.game.abort(); self.game = None
        if self.policy:
            self.policy.abort(); self.policy = None
        if self.started and not self.finished and self.record["status"] != "failed":
            self.record["status"] = "aborted-before-native-boundary"
        if (self.root / "worker").exists():
            archive_tensors(self.root / "worker")
        self.persist()
        self.log.close(); self.neural_log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("openttd", "policy", "training-run", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--company", type=int, choices=(0, 1), default=0)
    parser.add_argument("--first-company", type=int, choices=(0, 1), default=0)
    parser.add_argument("--decisions", type=int, default=512)
    parser.add_argument("--map-seed", type=int)
    parser.add_argument("--split", choices=("training", "development"), default="development")
    parser.add_argument("--sampling-seed", type=int, default=20260923)
    parser.add_argument("--player-label", default="interactive-mcp-controller-unverified")
    args = parser.parse_args()
    match = Match(args)

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {}
        finally:
            match.close()

    server = MCPServer("OpenTTD development match", version="0.2.2", lifespan=lifespan,
        instructions="Operate only your assigned company through current native candidates. No tools change the map seed or reveal opponent private state.")

    @server.tool()
    def game_info() -> dict:
        """Read interface, assigned company, action/tick budgets and timeout policy."""
        return match.invoke("game_info", {}, match.info)

    @server.tool()
    def start_match(include_map: bool = True) -> dict:
        """Start the one registered scenario. Set include_map=false for compact state, then inspect public map regions."""
        return match.invoke("start_match", {"include_map": include_map}, lambda: match.start(include_map))

    @server.tool()
    def observe(include_map: bool = True) -> dict:
        """Read own company, token and counts without advancing time; optionally include the full current public map."""
        return match.invoke("observe", {"include_map": include_map}, lambda: match.observe(include_map))

    @server.tool()
    def map_region(x: int, y: int, width: int, height: int) -> dict:
        """Read a current public map rectangle up to 32 by 32 tiles, without advancing time or exposing new information."""
        arguments = {"x": x, "y": y, "width": width, "height": height}
        return match.invoke("map_region", arguments, lambda: match.region(**arguments))

    @server.tool()
    def legal_actions(family: str | None = None, offset: int = 0, limit: int = 32,
                      parameter1: int | None = None, minimum_acceptance: int = 0,
                      minimum_production: int = 0, include_features: bool = False) -> dict:
        """Page native candidates, optionally filtering tile/vehicle ID or present stop acceptance/production. All filters use current public fields."""
        arguments = {"family": family, "offset": offset, "limit": limit, "parameter1": parameter1,
                     "minimum_acceptance": minimum_acceptance, "minimum_production": minimum_production, "include_features": include_features}
        return match.invoke("legal_actions", arguments, lambda: match.legal(**arguments))

    @server.tool()
    def submit_action(token: str, candidate_key: str) -> dict:
        """Execute one exposed native command for your fixed company; requires step afterward."""
        return match.invoke("submit_action", {"token": token, "candidate_key": candidate_key}, lambda: match.act(token, candidate_key))

    @server.tool()
    def step() -> dict:
        """Advance your accepted action by 128 ticks, then run the opponent's equal turn. Returns compact own state; observe includes the current public map."""
        return match.invoke("step", {}, match.step)

    @server.tool()
    def wait_turns(count: int) -> dict:
        """Repeat 1..8 explicit WAIT actions, each charged one turn with its ordinary opponent response."""
        return match.invoke("wait_turns", {"count": count}, lambda: match.wait_turns(count))

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
