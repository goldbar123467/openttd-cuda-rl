#!/usr/bin/env python3
"""Collect actual V2 actions and send them to native recurrent C++ PPO."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from infer_v2 import PolicyClient, checked_tensors
from guide_v2 import GUIDANCE, PublicPlanGuide
from live_v2 import LiveV2
from live_v2_artifacts import archive_tensors
from local import ROOT, capture_source, positive, source_identity, write_json
import checkpoint_v2


def reward_components(transition):
    before, after, action = transition["before"], transition["after"], transition["action"]
    delivery = after.get("delivered_passengers", before["delivered_passengers"]) - before["delivered_passengers"]
    profit = after.get("operating_profit", before["operating_profit"]) - before["operating_profit"]
    capital = 0
    if action["family"] in ("BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS"):
        capital = sum(max(0, command["cost"]) for command in action["native_commands"]
                      if command["phase"] == "EXECUTE" and command["status"] == "SUCCESS")
    components = {"delivery": min(max(delivery, 0), 64) / 64,
                  "operating_profit": min(max(profit, -256), 256) / 256,
                  "capital": -min(capital, 4096) / 4096,
                  "decision": -1 / 64, "bankruptcy": -5.0 if transition["terminal"] else 0.0}
    return {"schema_version": "development-v2-live-reward-1", "components": components,
            "reward": sum(components.values()), "raw_passengers": delivery, "raw_operating_profit": profit,
            "raw_capital": capital}


def run(args):
    if not 1 <= args.episode_horizon <= 512:
        raise ValueError("V2 episode horizon must be 1..512 decisions")
    gae_lambda = getattr(args, "gae_lambda", .95)
    if not math.isfinite(gae_lambda) or not 0 <= gae_lambda <= 1:
        raise ValueError("V2 gae-lambda must be finite and in [0,1]")
    checkpoint_interval = getattr(args, "checkpoint_interval", 0)
    resume = getattr(args, "resume", None)
    rollout = getattr(args, "rollout_length", 32)
    reuse_bootstrap_tensors = bool(getattr(args, "reuse_bootstrap_tensors", False))
    checkpoint_v2.validate_interval(checkpoint_interval, args.episode_horizon, rollout)
    training_seeds = json.loads((ROOT / "config/v2/m15-scalable-contract.json").read_text())["seeds"]["sets"]["training"]["seeds"]
    map_count = getattr(args, "training_map_count", 4)
    if type(map_count) is not int or not 1 <= map_count <= len(training_seeds):
        raise ValueError(f"V2 training map count must be 1..{len(training_seeds)}")
    seeds = training_seeds[:map_count]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-v2-live-recurrent-ppo", "status": "running", "source": source_identity(),
              "device": args.device, "run_seed": args.seed, "requested_updates": args.updates,
              "rollout_steps": rollout, "gamma": .99, "gae_lambda": gae_lambda, "environments": 1, "sequence_length": 8, "optimization_epochs": 4,
              "episode_horizon": args.episode_horizon, "training_map_seeds": seeds,
              "reuse_bootstrap_tensors": reuse_bootstrap_tensors,
              "reward_schema": "development-v2-live-reward-1", "episodes": [], "updates": [],
              "observation_schema_id": "v2-m15-public-development-v2",
              "guidance": args.guidance,
              "claim": "Live native PPO pipeline; finite updates alone do not establish playing competence",
              "trainer_sha256": hashlib.sha256(args.trainer.read_bytes()).hexdigest(),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "inference_weights_only": True, "optimizer_resume_supported": bool(checkpoint_interval or resume),
              "checkpoint_interval": checkpoint_interval, "resume_from": str(resume.resolve()) if resume else None,
              "checkpoints": []}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    trainer, game = None, None
    episode = 0
    restored_transitions = 0
    worker = None
    observation = None
    guide = None
    cached_frame = None
    started = time.monotonic()
    try:
        trainer = PolicyClient(args.trainer.resolve(), root / "trainer.log", args.device, args.seed,
                               rollout_length=rollout if rollout != 32 else None,
                               gae_lambda=gae_lambda if gae_lambda != .95 else None)
        if rollout != 32 or gae_lambda != .95:
            info = trainer.request("TRAINING_INFO")
            expected_info = {"rollout_steps": rollout, "sequence_length": 8, "optimization_epochs": 4}
            if "gamma" in info or "gae_lambda" in info:
                expected_info.update(gamma=.99, gae_lambda=gae_lambda)
            elif gae_lambda != .95:
                raise ValueError("Native V2 trainer does not report the requested GAE configuration")
            if info != expected_info:
                raise ValueError("Native V2 trainer configuration differs from the requested rollout or GAE")
            record["native_training_runtime"] = info
        if checkpoint_interval or resume:
            info = trainer.request("CHECKPOINT_INFO")
            if info != {"format": "openttd-rl-development-v2-reset-checkpoint-1", "reset_only": True, "updates": 0,
                        "deterministic_algorithms": True, "cublas_workspace_config": ":4096:8"}:
                raise ValueError("Native V2 trainer does not support the requested reset checkpoint format")
            record["native_checkpoint_runtime"] = info
        expected = checkpoint_v2.compatibility(record)
        if resume:
            restored = checkpoint_v2.restore(trainer, args.openttd, resume, root, expected)
            episode = restored["next_episode"]
            record["restored_update"] = restored["update"]
            record["restored_transitions"] = restored["transitions"]
            restored_transitions = restored["transitions"]
            write_json(root / "run.json", record)
        with (root / "trajectory.jsonl").open("x") as trajectory, (root / "metrics.jsonl").open("x") as metrics:
            for index in range(args.updates * rollout):
                reset = game is None
                if reset:
                    cached_frame = None
                    worker = root / f"episode-{episode:06d}"
                    game = LiveV2(args.openttd, worker, seed=seeds[episode % len(seeds)], decisions=args.episode_horizon)
                    episode += 1
                    observation = game.request("OBSERVE")["observation"]
                    guide = PublicPlanGuide(observation, worker) if args.guidance == GUIDANCE else None
                if cached_frame is None:
                    tensors = game.request("TENSORS")
                    obs_path, candidate_path, candidates, mask = checked_tensors(tensors, observation)
                    guidance = None
                    if guide:
                        candidate_path, mask, guidance = guide.prepare(observation, candidate_path, candidates, mask)
                else:
                    if (cached_frame["token"] != observation["token"] or
                            cached_frame["company_id"] != observation["company_id"]):
                        raise ValueError("Cached bootstrap tensors belong to another native state or company")
                    tensors = cached_frame["response"]
                    obs_path, candidate_path = cached_frame["observation_path"], cached_frame["candidate_path"]
                    candidates, mask, guidance = cached_frame["candidates"], cached_frame["mask"], cached_frame["guidance"]
                inference_start = time.monotonic_ns()
                prediction = trainer.request(f"ACT\t{obs_path}\t{candidate_path}\t{int(reset)}")
                inference_ns = time.monotonic_ns() - inference_start
                if prediction["row"] not in candidates or not mask[prediction["row"]]:
                    raise ValueError("Native PPO selected an illegal candidate row")
                selected = candidates[prediction["row"]]
                action = game.request("ACT", token=observation["token"], candidate=selected["stable_key"])
                if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                    raise RuntimeError("Native PPO action failed at the shared boundary")
                if guide:
                    guide.commit(selected["stable_key"])
                transition = game.request("STEP")["transition"]
                if transition["tick_after"] - transition["tick_before"] != 128:
                    raise RuntimeError("Live PPO changed the simulation-time budget")
                shaped = reward_components(transition)
                next_observation = game.request("OBSERVE")["observation"]
                bootstrap = not transition["terminal"]
                continuation = not (transition["terminal"] or transition["truncated"])
                next_obs_path, next_candidate_path = "-", "-"
                cached_frame = None
                if bootstrap:
                    next_tensors = game.request("TENSORS")
                    next_obs_path, next_candidate_path, next_candidates, next_mask = checked_tensors(next_tensors, next_observation, bootstrap_only=True)
                    next_guidance = None
                    if guide:
                        next_candidate_path, next_mask, next_guidance = guide.prepare(next_observation, next_candidate_path, next_candidates, next_mask)
                    if reuse_bootstrap_tensors and continuation:
                        # Native STEP produced this immutable, validated frame.
                        # REWARD reads it without advancing the game or guide.
                        # A real reset always discards the previous episode's frame.
                        cached_frame = {"token": next_observation["token"], "company_id": next_observation["company_id"],
                            "response": next_tensors, "observation_path": next_obs_path, "candidate_path": next_candidate_path,
                            "candidates": next_candidates, "mask": next_mask, "guidance": next_guidance}
                feedback = trainer.request(f"REWARD\t{shaped['reward']:.17g}\t{int(bootstrap)}\t{int(continuation)}\t{next_obs_path}\t{next_candidate_path}")
                if feedback["accepted"] != index % rollout + 1:
                    raise ValueError("Native V2 trainer accepted another rollout position")
                trajectory.write(json.dumps({"step": restored_transitions + index + 1, "episode": episode - 1, "reset": reset,
                    "prediction": prediction, "candidate": selected, "observation_metadata": tensors["tensors"]["observation"],
                    "candidates_metadata": tensors["tensors"]["candidates"], "transition": transition, "training_reward": shaped,
                    "guidance": guidance,
                    "bootstrap": bootstrap, "continuation": continuation, "feedback": feedback,
                    "inference_elapsed_ns": inference_ns}) + "\n")
                trajectory.flush()
                observation = next_observation
                if not continuation:
                    game.close(); game = None
                    record["episodes"].append({"episode": episode - 1, "completed": True,
                                               "decisions": observation["decisions"], "economy": observation["economy"]})
                    archive_tensors(worker)
                if (index + 1) % rollout == 0:
                    update_start = time.monotonic_ns()
                    update = trainer.request("UPDATE")
                    if update["transitions"] != restored_transitions + index + 1:
                        raise ValueError("Native V2 update transition count differs from collection")
                    update["elapsed_ns"] = time.monotonic_ns() - update_start
                    metrics.write(json.dumps(update) + "\n"); metrics.flush()
                    record["updates"].append(update)
                    if checkpoint_interval and update["update"] % checkpoint_interval == 0:
                        if game is None:
                            saved = checkpoint_v2.save(trainer, args.openttd, root / "checkpoints", expected, update, episode)
                        else:
                            saved = {"status": "skipped", "update": update["update"], "reason": "not at a native episode reset"}
                        record["checkpoints"].append(saved)
                    write_json(root / "run.json", record)
                    print(json.dumps(update), flush=True)
        model = root / "inference-weights.pt"
        record["save_validation"] = trainer.request(f"SAVE\t{model}")
        record["model"] = {"path": str(model), "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                           "purpose": "Inference weights only; optimizer/RNG recovery uses separate reset checkpoints"}
        if game:
            game.close(); game = None
            record["episodes"].append({"episode": episode - 1, "completed": False,
                                       "decisions": observation["decisions"], "economy": observation["economy"]})
            archive_tensors(worker)
        trainer.close(); trainer = None
        record["status"] = "completed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        for client in (game, trainer):
            if client is not None:
                client.abort()
        record["wall_seconds"] = time.monotonic() - started
        write_json(root / "run.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--seed", type=positive, default=20260923)
    parser.add_argument("--updates", type=positive, default=2)
    parser.add_argument("--rollout-length", type=int, choices=(32, 64, 128), default=32)
    parser.add_argument("--gae-lambda", type=float, default=.95, help="GAE trace weight in [0,1]; default .95")
    parser.add_argument("--episode-horizon", type=positive, default=128)
    parser.add_argument("--training-map-count", type=positive, default=4,
                        help="Use the first N training-ledger seeds in fixed order; default 4, recorded in checkpoint compatibility")
    parser.add_argument("--reuse-bootstrap-tensors", action="store_true",
                        help="Reuse a validated bootstrap frame for the next actor at the same native state; experimental")
    parser.add_argument("--guidance", choices=("none", GUIDANCE), default="none")
    parser.add_argument("--checkpoint-interval", type=int, default=0,
                        help="Save every N cumulative updates at a verified native reset; 0 disables checkpoints")
    parser.add_argument("--resume", type=Path, help="Restore a V2 reset checkpoint; updates are additional")
    run(parser.parse_args())
