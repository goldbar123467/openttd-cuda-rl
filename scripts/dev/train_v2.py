#!/usr/bin/env python3
"""Collect actual V2 actions and send them to native recurrent C++ PPO."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import signal

from infer_v2 import FINANCIAL_FEATURES, PolicyClient, checked_tensors, financial_features_mode
from guide_v2 import GUIDANCES, PublicPlanGuide
from live_v2 import LiveV2
from live_v2_artifacts import archive_tensors
from local import ROOT, capture_source, positive, source_identity, write_json
import checkpoint_v2
from asset_potential_v2 import AssetPotential, LEDGER, SCHEMA as POTENTIAL_SCHEMA


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


def entropy_coefficient_value(value):
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError("entropy-coefficient must be finite and in [0,1]")
    return result


class UniqueEntropyOption(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        if getattr(namespace, "_entropy_coefficient_seen", False):
            parser.error("duplicate --entropy-coefficient")
        namespace._entropy_coefficient_seen = True
        setattr(namespace, self.dest, value)


class TrainingInterrupted(Exception):
    """Infrastructure interruption, distinct from a failed learning seed."""


def interrupt_training(signum, frame):
    raise TrainingInterrupted(f"Training interrupted by signal {signum}")


def run(args, *, trainer_factory=PolicyClient):
    financial_features = financial_features_mode(getattr(args, "financial_features", "raw"))
    if not 1 <= args.episode_horizon <= 512:
        raise ValueError("V2 episode horizon must be 1..512 decisions")
    gae_lambda = getattr(args, "gae_lambda", .95)
    if not math.isfinite(gae_lambda) or not 0 <= gae_lambda <= 1:
        raise ValueError("V2 gae-lambda must be finite and in [0,1]")
    entropy_coefficient = entropy_coefficient_value(getattr(args, "entropy_coefficient", .01))
    checkpoint_interval = getattr(args, "checkpoint_interval", 0)
    resume = getattr(args, "resume", None)
    rollout = getattr(args, "rollout_length", 32)
    reuse_bootstrap_tensors = bool(getattr(args, "reuse_bootstrap_tensors", False))
    choice_weighted = getattr(args, "policy_loss", "historical") == "choice-weighted"
    gradient_norm = getattr(args, "gradient_norm", "historical")
    if gradient_norm not in ("historical", "fp64-v1"):
        raise ValueError("Unsupported gradient norm accumulation")
    asset_potential = bool(getattr(args, "asset_potential", False))
    training_reset_probes = bool(getattr(args, "training_reset_probes", False))
    recovery_diagnostics = bool(getattr(args, "recovery_diagnostics", False)) or choice_weighted or training_reset_probes
    if (asset_potential or training_reset_probes or recovery_diagnostics) and args.guidance not in GUIDANCES:
        raise ValueError("Recovery potential/probes/diagnostics require public one-bus guidance")
    registration_path = getattr(args, "study_registration", None)
    registration_ref = None
    predecessor_path = getattr(args, "interrupted_predecessor", None)
    if predecessor_path and (resume or not registration_path or not training_reset_probes):
        raise ValueError("A fresh interrupted restart requires registered probes and cannot also resume")
    if registration_path:
        from studies.execution_v2 import artifact, preflight
        registration, protocol, _ = preflight(registration_path)
        registration_ref = artifact(registration_path)
        settings = registration["training"]
        actual = {"device": args.device, "trainer": artifact(args.trainer), "engine": artifact(args.openttd),
                  "rollout_length": rollout, "episode_horizon": args.episode_horizon,
                  "entropy_coefficient": entropy_coefficient, "gae_lambda": gae_lambda,
                  "guide": args.guidance, "choice_weighted": choice_weighted, "asset_potential": asset_potential,
                  "financial_features": financial_features, "checkpoint_interval": checkpoint_interval,
                  "reuse_bootstrap_tensors": reuse_bootstrap_tensors, "gradient_norm": gradient_norm}
        registered_settings = {"gradient_norm": "historical", **settings}
        expected_args = {**{k: registered_settings[k] for k in actual if k not in ("device", "trainer", "engine")},
                         "device": registration["runtime"]["device"],
                         "trainer": registration["binaries"]["trainer"], "engine": registration["binaries"]["engine"]}
        if actual != expected_args or args.seed not in protocol["training_seeds"] or not training_reset_probes:
            raise ValueError("Registered training arguments differ before launching native processes")
    checkpoint_v2.validate_interval(checkpoint_interval, args.episode_horizon, rollout)
    training_seeds = json.loads((ROOT / "config/v2/m15-scalable-contract.json").read_text())["seeds"]["sets"]["training"]["seeds"]
    map_count = getattr(args, "training_map_count", 4)
    if type(map_count) is not int or not 1 <= map_count <= len(training_seeds):
        raise ValueError(f"V2 training map count must be 1..{len(training_seeds)}")
    seeds = training_seeds[:map_count]
    if registration_ref and seeds != protocol["training_maps"]:
        raise ValueError("Registered training map set differs")
    previous_record = None
    resume_parent = None
    predecessor_ref = None
    if predecessor_path:
        from studies.evidence_v2 import Inputs
        from studies.training_result_v2 import training_history
        predecessor_ref = artifact(predecessor_path)
        predecessor, _ = training_history(predecessor_ref, registration, protocol, Inputs(), registration_ref["sha256"])
        if (predecessor["status"] not in ("running", "interrupted") or predecessor["run_seed"] != args.seed or
                predecessor.get("restored_update", 0) or predecessor.get("resume_from") or any(c.get("status") == "saved" for c in predecessor["checkpoints"])):
            raise ValueError("Fresh restart requires an interrupted same-seed run before any published checkpoint")
    if training_reset_probes and resume:
        from studies.execution_v2 import artifact
        resume_parent = artifact(resume.resolve().parents[1] / "run.json")
        previous_record = json.loads(Path(resume_parent["path"]).read_text())
        if (previous_record["status"] not in ("running", "interrupted") or
                previous_record.get("study_registration_sha256") != (registration_ref or {}).get("sha256")):
            raise ValueError("Probed recovery requires an interrupted segment of the same registered seed")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-v2-live-recurrent-ppo", "status": "running", "source": source_identity(),
              "device": args.device, "run_seed": args.seed, "requested_updates": args.updates,
              "rollout_steps": rollout, "gamma": .99, "gae_lambda": gae_lambda, "financial_features": financial_features,
              "entropy_coefficient": entropy_coefficient, "environments": 1, "sequence_length": 8, "optimization_epochs": 4,
              "episode_horizon": args.episode_horizon, "training_map_seeds": seeds,
              "reuse_bootstrap_tensors": reuse_bootstrap_tensors,
              "choice_weighted": choice_weighted, "asset_potential": asset_potential,
              "gradient_norm": gradient_norm,
              "recovery_diagnostics": recovery_diagnostics,
              "reward_schema": POTENTIAL_SCHEMA if asset_potential else "development-v2-live-reward-1",
              "potential_ledger": LEDGER if asset_potential else None, "episodes": [], "updates": [],
              "observation_schema_id": "v2-m15-public-development-v2",
              "guidance": args.guidance,
              "claim": "Live native PPO pipeline; finite updates alone do not establish playing competence",
              "trainer_sha256": hashlib.sha256(args.trainer.read_bytes()).hexdigest(),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest(),
              "inference_weights_only": True, "optimizer_resume_supported": bool(checkpoint_interval or resume),
              "checkpoint_interval": checkpoint_interval, "resume_from": str(resume.resolve()) if resume else None,
              "checkpoints": []}
    if registration_ref:
        record["study_registration"] = registration_ref
        record["study_registration_sha256"] = registration_ref["sha256"]
    if resume_parent:
        record["resume_parent"] = resume_parent
    if predecessor_ref:
        record["interrupted_predecessor"] = predecessor_ref
    if resume and registration_ref:
        planned = checkpoint_v2.read(resume, checkpoint_v2.compatibility(record))
        record["resume_target"] = {"update": planned["update"], "transitions": planned["transitions"]}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    trainer, game = None, None
    episode = 0
    restored_transitions = 0
    worker = None
    observation = None
    guide = None
    cached_frame = None
    ledger = None
    probe_entries = None
    early_stopped = False
    started = time.monotonic()
    try:
        trainer = trainer_factory(args.trainer.resolve(), root / "trainer.log", args.device, args.seed,
                               rollout_length=rollout if rollout != 32 else None,
                               gae_lambda=gae_lambda if gae_lambda != .95 else None, financial_features=financial_features,
                               entropy_coefficient=entropy_coefficient, choice_weighted=choice_weighted,
                               recovery_diagnostics=recovery_diagnostics, gradient_norm=gradient_norm)
        trainer.check_financial_features()
        info = trainer.request("TRAINING_INFO")
        expected_info = {"rollout_steps": rollout, "sequence_length": 8, "optimization_epochs": 4,
                         "gamma": .99, "gae_lambda": gae_lambda, "entropy_coefficient": entropy_coefficient}
        extras = {"choice_weighted": choice_weighted, "learning_rate": .0003, "clip_epsilon": .2,
                  "max_gradient_norm": .5, "value_coefficient": .5, "gradient_norm": gradient_norm}
        if (any(info.get(key) != value for key, value in expected_info.items()) or
                any(key in info and info[key] != value for key, value in extras.items()) or
                (choice_weighted and info.get("choice_weighted") is not True) or
                (gradient_norm != "historical" and info.get("gradient_norm") != gradient_norm) or
                set(info) - (set(expected_info) | set(extras))):
            raise ValueError("Native V2 trainer configuration differs from requested PPO settings")
        record["native_training_runtime"] = info
        if checkpoint_interval or resume:
            info = trainer.request("CHECKPOINT_INFO")
            if info != {"format": "openttd-rl-development-v2-reset-checkpoint-1", "reset_only": True, "updates": 0,
                        "deterministic_algorithms": True, "cublas_workspace_config": ":4096:8"}:
                raise ValueError("Native V2 trainer does not support the requested reset checkpoint format")
            record["native_checkpoint_runtime"] = info
        expected = checkpoint_v2.compatibility(record)
        if training_reset_probes:
            import training_probes_v2
            from studies.protocol_v2 import PROTOCOL_SHA256, load_protocol
            probe_protocol = load_protocol()
            probe_entries = training_probes_v2.prepare(args.openttd, root / "training-reset-inputs", seeds,
                                                       args.episode_horizon, args.guidance)
            record["training_probe_protocol_sha256"] = PROTOCOL_SHA256
            record["training_reset_probes"] = []
            record["initial_training_reset_probe"] = (previous_record["initial_training_reset_probe"] if previous_record else
                                                       training_probes_v2.probe(trainer, probe_entries, 0))
        if resume:
            restored = checkpoint_v2.restore(trainer, args.openttd, resume, root, expected)
            episode = restored["next_episode"]
            record["restored_update"] = restored["update"]
            record["restored_transitions"] = restored["transitions"]
            restored_transitions = restored["transitions"]
            if previous_record:
                record["training_reset_probes"] = [p for p in previous_record["training_reset_probes"] if p["update"] <= restored["update"]]
                from studies.training_result_v2 import early_stop_update
                if early_stop_update(record["training_reset_probes"], probe_protocol) is not None:
                    raise ValueError("Cannot resume a seed past the frozen early-stop trigger")
                if not any(c.get("status") == "saved" and c["update"] == restored["update"] and
                           Path(c["path"]).resolve() == resume.resolve() and
                           c["manifest_sha256"] == hashlib.sha256((resume / "checkpoint.json").read_bytes()).hexdigest()
                           for c in previous_record["checkpoints"]):
                    raise ValueError("Resume checkpoint is not registered by the interrupted segment")
            if registration_ref and args.updates * rollout + restored_transitions != settings["decisions"]:
                raise ValueError("Resumed registered training must end at the original budget")
            write_json(root / "run.json", record)
        elif registration_ref and args.updates * rollout != settings["decisions"]:
            raise ValueError("Registered training must request the exact fixed budget")
        with (root / "trajectory.jsonl").open("x") as trajectory, (root / "metrics.jsonl").open("x") as metrics:
            for index in range(args.updates * rollout):
                reset = game is None
                if reset:
                    ledger = AssetPotential(record["native_training_runtime"]["gamma"], args.episode_horizon) if asset_potential else None
                    cached_frame = None
                    worker = root / f"episode-{episode:06d}"
                    game = LiveV2(args.openttd, worker, seed=seeds[episode % len(seeds)], decisions=args.episode_horizon)
                    episode += 1
                    observation = game.request("OBSERVE")["observation"]
                    guide = PublicPlanGuide(observation, worker, guidance=args.guidance) if args.guidance in GUIDANCES else None
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
                diagnostic = ""
                if recovery_diagnostics:
                    row = next(row for row, value in candidates.items() if value["stable_key"] == guidance["proposed_key"])
                    diagnostic = f"\t{row}"
                prediction = trainer.request(f"ACT\t{obs_path}\t{candidate_path}\t{int(reset)}{diagnostic}")
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
                if ledger:
                    shaped = ledger.apply(shaped, transition)
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
                    if probe_entries and update["update"] >= probe_protocol["early_stop"]["first_eligible_update"] and update["update"] % probe_protocol["early_stop"]["check_every_updates"] == 0:
                        from studies.training_result_v2 import early_stop_update
                        record["training_reset_probes"].append(training_probes_v2.probe(trainer, probe_entries, update["update"]))
                        early_stopped = early_stop_update(record["training_reset_probes"], probe_protocol) is not None
                    if checkpoint_interval and update["update"] % checkpoint_interval == 0:
                        if game is None:
                            saved = checkpoint_v2.save(trainer, args.openttd, root / "checkpoints", expected, update, episode)
                        else:
                            saved = {"status": "skipped", "update": update["update"], "reason": "not at a native episode reset"}
                        record["checkpoints"].append(saved)
                    write_json(root / "run.json", record)
                    print(json.dumps(update), flush=True)
                    if early_stopped:
                        break
        model = root / "inference-weights.pt"
        record["save_validation"] = trainer.request(f"SAVE\t{model}")
        record["model"] = {"path": str(model), "sha256": hashlib.sha256(model.read_bytes()).hexdigest(), "financial_features": financial_features,
                           "training_gradient_norm": gradient_norm,
                           "purpose": "Inference weights only; optimizer/RNG recovery uses separate reset checkpoints"}
        if game:
            game.close(); game = None
            record["episodes"].append({"episode": episode - 1, "completed": False,
                                       "decisions": observation["decisions"], "economy": observation["economy"]})
            archive_tensors(worker)
        trainer.close(); trainer = None
        record["status"] = "early-stopped" if early_stopped else "completed"
    except TrainingInterrupted as exc:
        record.update(status="interrupted", error=str(exc))
        raise
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
    parser.add_argument("--financial-features", choices=FINANCIAL_FEATURES, default="raw",
                        help="Optional signed-log currency preprocessing shared by native training and inference")
    parser.add_argument("--seed", type=positive, default=20260923)
    parser.add_argument("--updates", type=positive, default=2)
    parser.add_argument("--rollout-length", type=int, choices=(32, 64, 128), default=32)
    parser.add_argument("--gae-lambda", type=float, default=.95, help="GAE trace weight in [0,1]; default .95")
    parser.add_argument("--entropy-coefficient", type=entropy_coefficient_value, action=UniqueEntropyOption, default=.01,
                        help="Native PPO entropy bonus in [0,1]; default .01, bound to reset checkpoints")
    parser.add_argument("--episode-horizon", type=positive, default=128)
    parser.add_argument("--training-map-count", type=positive, default=4,
                        help="Use the first N training-ledger seeds in fixed order; default 4, recorded in checkpoint compatibility")
    parser.add_argument("--reuse-bootstrap-tensors", action="store_true",
                        help="Reuse a validated bootstrap frame for the next actor at the same native state; experimental")
    parser.add_argument("--policy-loss", choices=("historical", "choice-weighted"), default="historical")
    parser.add_argument("--gradient-norm", choices=("historical", "fp64-v1"), default="historical",
                        help="Versioned L2 clipping accumulation; parameters and gradients remain float32")
    parser.add_argument("--asset-potential", action="store_true", help="Versioned finite-episode clipped-capital ledger shaping")
    parser.add_argument("--recovery-diagnostics", action="store_true", help="Read-only proposal probabilities on collected actions")
    parser.add_argument("--training-reset-probes", action="store_true", help="Eight training resets and frozen recovery early-stop rule")
    parser.add_argument("--study-registration", type=Path, help="Require a frozen execution registration before training")
    parser.add_argument("--guidance", choices=("none", *GUIDANCES), default="none")
    parser.add_argument("--checkpoint-interval", type=int, default=0,
                        help="Save every N cumulative updates at a verified native reset; 0 disables checkpoints")
    parser.add_argument("--resume", type=Path, help="Restore a V2 reset checkpoint; updates are additional")
    parser.add_argument("--interrupted-predecessor", type=Path, help="Retain a registered interruption before its first reset checkpoint")
    signal.signal(signal.SIGTERM, interrupt_training)
    signal.signal(signal.SIGINT, interrupt_training)
    run(parser.parse_args())
