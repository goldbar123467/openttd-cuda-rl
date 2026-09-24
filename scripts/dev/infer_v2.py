#!/usr/bin/env python3
"""Connect the scalable C++ policy or saved live-PPO weights to real V2 states."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import select
import struct
import subprocess
import time

from live_v2 import LiveV2
from live_v2_artifacts import archive_tensors
from local import capture_source, positive, source_identity, write_json
from service_v2 import summarize
from guide_v2 import GUIDANCE, PublicPlanGuide
from play_live import native_screenshot

TENSOR_SCHEMA = "openttd-rl-development-v2-public-tensors-1"


def checked_tensors(response, observation, *, bootstrap_only=False):
    if response["status"] != "OK" or response["tensors"]["schema_version"] != TENSOR_SCHEMA:
        raise ValueError("Native public tensor response differs")
    tensors = response["tensors"]
    if tensors["token"] != observation["token"]:
        raise ValueError("Public tensor snapshot and observation tokens differ")
    if tensors.get("company_id") != observation["company_id"]:
        raise ValueError("Public tensor snapshot company differs")
    result = {}
    for name, expected_size in (("observation", 2182927), ("candidates", 790528)):
        path = Path(tensors[name])
        metadata = json.loads(path.read_text())
        filename = metadata["binary"]["file"]
        if Path(filename).name != filename:
            raise ValueError("Tensor binary reference is not a basename")
        binary = path.parent / filename
        data = binary.read_bytes()
        if len(data) != expected_size or metadata["binary"]["bytes"] != expected_size or hashlib.sha256(data).hexdigest() != metadata["binary"]["sha256"]:
            raise ValueError("Native tensor binary size/hash differs")
        if any(metadata["snapshot"][key] != 0 for key in ("map_seed", "simulation_seed")):
            raise ValueError("Native tensor metadata exposes reset seeds")
        result[name] = (binary, metadata, data)
    _, obs_meta, obs_bytes = result["observation"]
    if obs_meta["schema_version"] != "openttd-rl-development-v2-observation-metadata-1" or obs_meta["snapshot"]["candidate_tiebreak_seed"] != 0:
        raise ValueError("Unredacted observation metadata is forbidden")
    if obs_meta["observation_schema_id"] != "v2-m15-public-development-v2" or obs_meta.get("vehicle_order") != "own-company-first-then-public-vehicle-id":
        raise ValueError("Live tensors must order vehicles by public identity before selection")
    if obs_meta.get("observing_company") != observation["company_id"]:
        raise ValueError("Native tensor metadata has a different observing company")
    if struct.unpack_from("<3f", obs_bytes, 13 * 4) != (0.0, 0.0, 0.0):
        raise ValueError("Native tensor observation exposes seed features")
    if any(struct.unpack_from("<2f", obs_bytes, 1286927 + (row * 40 + 7) * 4) != (0.0, 0.0) for row in range(1024)):
        raise ValueError("Native tensor observation exposes breakdown countdowns")
    _, candidate_meta, candidate_bytes = result["candidates"]
    if candidate_meta["observation_sha256"] != obs_meta["binary"]["sha256"]:
        raise ValueError("Candidate tensor bound to another observation")
    records = {record["row"]: record for record in candidate_meta["records"]}
    if len(records) != len(candidate_meta["records"]):
        raise ValueError("Candidate row identities repeat")
    mask = candidate_bytes[-4096:]
    if any(value not in (0, 1) for value in mask) or {i for i, value in enumerate(mask) if value} != records.keys():
        raise ValueError("Candidate record and mask rows differ")
    exposed = {candidate["key"]: candidate for candidate in observation["candidates"]}
    if bootstrap_only and observation["truncated"] and not tensors["can_act"] and not exposed:
        return result["observation"][0], result["candidates"][0], records, mask
    if {record["stable_key"] for record in records.values()} != exposed.keys():
        raise ValueError("Neural tensors and public action candidates differ")
    for row, record in records.items():
        candidate = exposed[record["stable_key"]]
        if record["parameters"] != candidate["parameters"]:
            raise ValueError("Neural and public action parameters differ")
        if candidate_bytes[row * 128:(row + 1) * 128] != struct.pack("<32f", *candidate["features"]):
            raise ValueError("Neural and public candidate features differ")
    return result["observation"][0], result["candidates"][0], records, mask


class PolicyClient:
    def __init__(self, executable, output, device, seed, mode=None, weights=None, rollout_length=None, gae_lambda=None):
        self.log = Path(output).open("x")
        command = [str(executable), "--device", device, "--seed", str(seed)]
        if mode is not None:
            command += ["--mode", mode]
        if weights is not None:
            command += ["--weights", str(weights)]
        if rollout_length is not None:
            command += ["--rollout-length", str(rollout_length)]
        if gae_lambda is not None:
            command += ["--gae-lambda", str(gae_lambda)]
        self.process = subprocess.Popen(command,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                        text=True, bufsize=1)

    def request(self, line):
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 60)[0]:
            raise TimeoutError("Native V2 policy response timed out")
        response = self.process.stdout.readline(256 * 1024)
        if not response.endswith("\n"):
            raise RuntimeError("Native V2 inference failed or exceeded its response bound; inspect policy log")
        return json.loads(response)

    def close(self):
        self.request("CLOSE")
        if self.process.wait(timeout=10) != 0:
            raise RuntimeError("Native policy exited unsuccessfully")
        self.abort()

    def abort(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()


def run(args):
    visible = bool(getattr(args, "visible", False))
    weights = None
    training = None
    guidance_name = "none"
    if args.training_run:
        training = json.loads((args.training_run / "run.json").read_text())
        if training["kind"] != "native-v2-live-recurrent-ppo" or training["status"] != "completed":
            raise ValueError("Inference requires a completed live V2 training run")
        if training.get("observation_schema_id") != "v2-m15-public-development-v2":
            raise ValueError("Saved weights use an incompatible public observation version")
        if training.get("financial_features", "raw") != "raw" or training["model"].get("financial_features", "raw") != "raw":
            raise ValueError("This playback prototype supports the existing raw-input weights only")
        guidance_name = training.get("guidance", "none")
        if guidance_name not in ("none", GUIDANCE):
            raise ValueError("Saved weights use an unsupported planner curriculum")
        weights = Path(training["model"]["path"]).resolve()
        if weights != args.training_run.resolve() / "inference-weights.pt" or hashlib.sha256(weights.read_bytes()).hexdigest() != training["model"]["sha256"]:
            raise ValueError("Saved V2 training weights path/hash differs")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-v2-neural-live-inference-smoke", "status": "running", "source": source_identity(),
              "device": args.device, "run_seed": args.seed, "mode": args.mode, "decisions": args.decisions,
              "split": args.split, "map_seed": args.map_seed, "final_evaluation_accessed": False, "visible": visible,
              "claim": "Live recurrent policy inference check; short interaction does not establish learned competence",
              "training_run": str(args.training_run.resolve()) if args.training_run else None,
              "model": training["model"] if training else {"initialization_only": True},
              "guidance": guidance_name,
              "policy_sha256": hashlib.sha256(args.policy.read_bytes()).hexdigest(),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "tolerances": {"probability_atol": 1e-5, "value_atol": 1e-4}}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    game, policy, reference = None, None, None
    errors = {"probability_max_abs": 0.0, "value_max_abs": 0.0}
    try:
        policy = PolicyClient(args.policy.resolve(), root / "policy.log", args.device, args.seed, args.mode, weights)
        if args.compare_cpu:
            reference = PolicyClient(args.policy.resolve(), root / "cpu-reference.log", "cpu", args.seed, args.mode, weights)
        game = LiveV2(args.openttd, root / "worker", decisions=args.decisions, split=args.split, seed=args.map_seed, visible=visible)
        initial = game.request("OBSERVE")["observation"]
        guide = PublicPlanGuide(initial, root / "worker") if guidance_name == GUIDANCE else None
        transitions = []
        with (root / "predictions.jsonl").open("x") as predictions:
            for decision in range(args.decisions):
                observation = game.request("OBSERVE")["observation"]
                response = game.request("TENSORS")
                obs_path, candidate_path, candidates, mask = checked_tensors(response, observation)
                guidance = None
                if guide:
                    candidate_path, mask, guidance = guide.prepare(observation, candidate_path, candidates, mask)
                if game.request("OBSERVE")["observation"] != observation or game.request("TENSORS")["tensors"] != response["tensors"]:
                    raise RuntimeError("Tensor observation changed state or was not cached")
                started = time.monotonic_ns()
                prediction = policy.request(f"{obs_path}\t{candidate_path}")
                elapsed = time.monotonic_ns() - started
                if prediction["schema_version"] != TENSOR_SCHEMA or prediction["row"] not in candidates:
                    raise ValueError("Native policy selected an unexposed row")
                p = prediction["probabilities"]
                if len(p) != 4096 or not all(math.isfinite(value) and value >= 0 for value in p) or abs(sum(p) - 1) > 1e-5 or any(p[i] != 0 for i in range(4096) if not mask[i]):
                    raise ValueError("Native policy returned invalid probabilities/masks")
                if reference:
                    cpu = reference.request(f"{obs_path}\t{candidate_path}")
                    errors["probability_max_abs"] = max(errors["probability_max_abs"], max(abs(a - b) for a, b in zip(p, cpu["probabilities"], strict=True)))
                    errors["value_max_abs"] = max(errors["value_max_abs"], abs(prediction["value"] - cpu["value"]))
                    if errors["probability_max_abs"] > 1e-5 or errors["value_max_abs"] > 1e-4 or prediction["row"] != cpu["row"]:
                        raise RuntimeError("CPU/GPU live policy comparison differs")
                selected = candidates[prediction["row"]]
                predictions.write(json.dumps({"decision": decision + 1, "token": observation["token"], "prediction": prediction,
                                              "candidate": selected, "guidance": guidance, "inference_elapsed_ns": elapsed}) + "\n")
                predictions.flush()
                action = game.request("ACT", token=observation["token"], candidate=selected["stable_key"])
                if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                    raise RuntimeError("Neural candidate execution failed")
                if guide:
                    guide.commit(selected["stable_key"])
                transition = game.request("STEP")["transition"]
                if transition["tick_after"] - transition["tick_before"] != 128:
                    raise RuntimeError("Neural step budget differs")
                transitions.append(transition)
                if decision < 8 or (decision + 1) % 128 == 0:
                    print(json.dumps({"decision": decision + 1, "family": action["action"]["family"], "row": prediction["row"],
                        "economy": transition["after"]}), flush=True)
                if transition["terminal"]:
                    break
        final = game.request("OBSERVE")["observation"]
        game.close(); game = None
        if visible:
            screenshot = native_screenshot(root / "worker", "v2-live-playback")
            record.update(screenshot=str(screenshot), screenshot_sha256=hashlib.sha256(screenshot.read_bytes()).hexdigest(),
                          display=json.loads((root / "worker/display.json").read_text()))
        archive_tensors(root / "worker")
        policy.close(); policy = None
        if reference:
            reference.close(); reference = None
        record.update(status="passed", comparison=errors, final_observation=final, summary=summarize(transitions, initial, final))
        write_json(root / "summary.json", record["summary"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        for client in (game, policy, reference):
            if client is not None:
                client.abort()
        write_json(root / "run.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--seed", type=positive, default=20260923)
    parser.add_argument("--decisions", type=positive, default=8)
    parser.add_argument("--mode", choices=("greedy", "sampled"), default="sampled")
    parser.add_argument("--compare-cpu", action="store_true")
    parser.add_argument("--visible", action="store_true", help="View-only native SDL window; requires the isolated V2 playback engine")
    parser.add_argument("--training-run", type=Path, help="Load hash-verified inference weights from a completed live V2 PPO run")
    parser.add_argument("--split", choices=("training", "development"), default="training")
    parser.add_argument("--map-seed", type=int)
    run(parser.parse_args())
