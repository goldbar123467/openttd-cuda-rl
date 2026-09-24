"""Native V2 recovery only at a verified episode reset and completed PPO update."""
import hashlib
import json
from pathlib import Path

from infer_v2 import checked_tensors
from guide_v2 import GUIDANCES, PublicPlanGuide
from live_v2 import LiveV2, canonical
from live_v2_artifacts import archive_tensors
from local import ROOT, write_json


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compatibility(record):
    scripts = ["train_v2.py", "checkpoint_v2.py", "infer_v2.py", "live_v2.py", "live_v2_artifacts.py",
               "guide_v2.py", "service_v2.py", "route_v2.py"]
    contracts = ["m15-scalable-contract.json", "m15-native-source.json", "setting-inventory.json"]
    return {"configuration": {key: record[key] for key in (
        "device", "run_seed", "rollout_steps", "environments", "sequence_length", "optimization_epochs",
        "episode_horizon", "training_map_seeds", "reward_schema", "observation_schema_id", "guidance",
        "trainer_sha256", "engine_sha256")} | {"reuse_bootstrap_tensors": record.get("reuse_bootstrap_tensors", False),
            "gamma": record.get("gamma", .99), "gae_lambda": record.get("gae_lambda", .95)},
        "collector_sources": {name: digest(ROOT / "scripts/dev" / name) for name in scripts},
        "contracts": {name: digest(ROOT / "config/v2" / name) for name in contracts}}


def validate_interval(interval, horizon, rollout=32):
    if rollout not in (32, 64, 128):
        raise ValueError("V2 rollout length must be 32, 64 or 128")
    if interval < 0 or (interval and interval * rollout % horizon):
        raise ValueError("V2 checkpoint interval must align with complete native episodes")


def reset_signature(engine, output, configuration, next_episode):
    """A read-only next-game reset probe, never an extra training transition."""
    seeds = configuration["training_map_seeds"]
    game = LiveV2(engine, output, seed=seeds[next_episode % len(seeds)], decisions=configuration["episode_horizon"])
    try:
        observation = game.request("OBSERVE")["observation"]
        tensors = game.request("TENSORS")
        obs, candidate_path, candidates, mask = checked_tensors(tensors, observation)
        signature = {"public_observation_sha256": hashlib.sha256(canonical({k: v for k, v in observation.items() if k != "token"})).hexdigest(),
                     "reset_manifest_sha256": digest(output / "reset.json"),
                     "observation_binary_sha256": digest(obs), "native_candidates_binary_sha256": digest(candidate_path)}
        if configuration["guidance"] in GUIDANCES:
            guide = PublicPlanGuide(observation, output, guidance=configuration["guidance"])
            candidate_path, _, _ = guide.prepare(observation, candidate_path, candidates, mask)
        signature["sampling_candidates_binary_sha256"] = digest(candidate_path)
        game.close(); game = None
        archive_tensors(output)
        return signature
    finally:
        if game is not None:
            game.abort()


def save(trainer, engine, root, expected, update, next_episode):
    target = root / f"update-{update['update']:06d}"
    target.mkdir(parents=True, exist_ok=False)
    native = trainer.request(f"CHECKPOINT\t{target / 'trainer.pt'}")
    if (native["status"] != "SAVED_RESET_CHECKPOINT" or native["updates"] != update["update"] or
            native["transitions"] != update["transitions"]):
        raise ValueError("Native checkpoint counters differ from accepted PPO update")
    signature = reset_signature(engine, target / "next-reset-probe", expected["configuration"], next_episode)
    manifest = {"format": "openttd-rl-development-v2-reset-checkpoint-1", "compatibility": expected,
                "update": native["updates"], "transitions": native["transitions"], "next_episode": next_episode,
                "trainer_sha256": digest(target / "trainer.pt"), "next_reset": signature,
                "claim": "Native optimizer/RNG/recurrent state at an episode reset; no mid-game recovery"}
    write_json(target / "checkpoint.json", manifest)
    return {"status": "saved", "update": native["updates"], "path": str(target),
            "manifest_sha256": digest(target / "checkpoint.json")}


def read(path, expected):
    path = Path(path).resolve()
    manifest = json.loads((path / "checkpoint.json").read_text())
    if manifest.get("format") != "openttd-rl-development-v2-reset-checkpoint-1" or manifest["compatibility"] != expected:
        raise ValueError("V2 checkpoint runtime, source, configuration or contract differs")
    if (type(manifest["update"]) is not int or manifest["update"] <= 0 or
            manifest["transitions"] != manifest["update"] * expected["configuration"]["rollout_steps"] or
            type(manifest["next_episode"]) is not int or manifest["next_episode"] <= 0):
        raise ValueError("V2 checkpoint counters invalid")
    if digest(path / "trainer.pt") != manifest["trainer_sha256"]:
        raise ValueError("V2 checkpoint payload digest mismatch")
    return manifest


def restore(trainer, engine, path, output, expected):
    path = Path(path).resolve()
    manifest = read(path, expected)
    signature = reset_signature(engine, output / "resume-reset-probe", expected["configuration"], manifest["next_episode"])
    if signature != manifest["next_reset"]:
        raise ValueError("Recreated V2 reset observation, candidates or sampling mask differs")
    native = trainer.request(f"RESTORE\t{path / 'trainer.pt'}")
    if native != {"status": "RESTORED_RESET_CHECKPOINT", "updates": manifest["update"], "transitions": manifest["transitions"]}:
        raise ValueError("Restored native counters differ from checkpoint manifest")
    return manifest
