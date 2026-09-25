"""Require registered final models and retain failed/early-stopped training seeds."""
import math
from pathlib import Path

from studies.execution_v2 import checked_artifact, digest
from studies.protocol_v2 import PROTOCOL_SHA256


def early_stop_update(probes, protocol):
    rule = protocol["early_stop"]
    previous, consecutive, first_trigger = None, 0, None
    for probe in probes:
        update = probe["update"]
        if type(update) is not int or update < rule["first_eligible_update"] or update % rule["check_every_updates"]:
            raise ValueError("Training reset probe has an unregistered checkpoint")
        if previous is not None and update != previous + rule["check_every_updates"]:
            raise ValueError("Training reset probe checkpoints are missing or duplicated")
        rows = probe["maps"]
        if len(rows) != len(protocol["training_maps"]) or sorted(r["map_seed"] for r in rows) != sorted(protocol["training_maps"]):
            raise ValueError("Probe must include every training map exactly once")
        values = [r["proposal_probability"] for r in rows]
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise ValueError("Invalid training-reset proposal probability")
        weak = sum(v < rule["proposal_probability_below"] for v in values) >= rule["minimum_maps"]
        consecutive = consecutive + 1 if weak else 0
        if first_trigger is None and consecutive == rule["consecutive_checkpoints"]:
            first_trigger = update
        previous = update
    if probes and probes[0]["update"] != rule["first_eligible_update"]:
        raise ValueError("Training probe series must begin at the first eligible checkpoint")
    return first_trigger


def training_history(reference, registration, protocol, inputs, registration_sha256, seen=None):
    """Rebuild one logical seed from immutable interrupted segments at resets.

    Failed/stopped seeds cannot be replaced. Only work after the last published
    reset checkpoint of an interrupted segment can be replayed; discarded data
    remain in the original segment and are hash identified.
    """
    seen = set() if seen is None else seen
    path = checked_artifact(reference, inputs)
    if str(path) in seen:
        raise ValueError("Training resume ancestry contains a cycle")
    seen.add(str(path))
    if path.name != "run.json":
        raise ValueError("Training result must identify the native run record")
    record = inputs.json(path)
    settings = registration["training"]
    if (record["kind"] != "native-v2-live-recurrent-ppo" or
            record["status"] not in ("completed", "early-stopped", "failed", "running", "interrupted") or
            record["source"] != registration["source"] or
            record.get("study_registration_sha256") != registration_sha256 or
            record["run_seed"] not in protocol["training_seeds"] or type(record["run_seed"]) is not int):
        raise ValueError("Training result is unregistered or from another source/seed")
    pending = bool(record.get("resume_target")) and "restored_update" not in record
    if pending and (record["status"] not in ("running", "interrupted", "failed") or record["updates"]):
        raise ValueError("Unrestored segment cannot contain training experience")
    restored = record.get("restored_update", record.get("resume_target", {}).get("update", 0))
    if type(restored) is not int or not 0 <= restored < settings["decisions"] // settings["rollout_length"]:
        raise ValueError("Invalid registered resume counter")
    expected = {"device": registration["runtime"]["device"], "environments": 1,
                "requested_updates": settings["decisions"] // settings["rollout_length"] - restored,
                "rollout_steps": settings["rollout_length"], "episode_horizon": settings["episode_horizon"],
                "training_map_seeds": protocol["training_maps"], "guidance": settings["guide"],
                "trainer_sha256": registration["binaries"]["trainer"]["sha256"],
                "engine_sha256": registration["binaries"]["engine"]["sha256"],
                **{k: settings[k] for k in ("financial_features", "reuse_bootstrap_tensors", "checkpoint_interval",
                    "gamma", "gae_lambda", "entropy_coefficient", "optimization_epochs", "sequence_length", "choice_weighted", "asset_potential")}}
    if any(type(record.get(k)) is not type(v) or record.get(k) != v for k, v in expected.items()):
        raise ValueError("Training result differs from the exact registered arm")
    updates = record["updates"]
    if len(updates) > record["requested_updates"] or any(u["update"] != restored + i + 1 or
            u["transitions"] != (restored + i + 1) * settings["rollout_length"] for i, u in enumerate(updates)):
        raise ValueError("Training update/experience counters differ")
    if record.get("resume_from"):
        if not restored or record.get("restored_transitions", record.get("resume_target", {}).get("transitions")) != restored * settings["rollout_length"]:
            raise ValueError("Resume has no matching restored counters")
        parent, parent_updates = training_history(record["resume_parent"], registration, protocol, inputs,
                                                   registration_sha256, seen)
        if parent["status"] not in ("running", "interrupted") or parent["run_seed"] != record["run_seed"]:
            raise ValueError("Only an interrupted segment of the same seed may resume")
        checkpoint = Path(record["resume_from"]).resolve()
        parent_root = Path(record["resume_parent"]["path"]).parent
        if checkpoint != parent_root / "checkpoints" / f"update-{restored:06d}":
            raise ValueError("Resume checkpoint is not inside its interrupted segment")
        saved = [c for c in parent["checkpoints"] if c.get("status") == "saved" and c["update"] == restored]
        if len(saved) != 1 or Path(saved[0]["path"]).resolve() != checkpoint:
            raise ValueError("Interrupted segment did not publish this reset checkpoint")
        checked_artifact({"path": str(checkpoint / "checkpoint.json"), "sha256": saved[0]["manifest_sha256"]}, inputs)
        import checkpoint_v2
        manifest = checkpoint_v2.read(checkpoint, checkpoint_v2.compatibility(record))
        if manifest["update"] != restored or len(parent_updates) < restored:
            raise ValueError("Resume checkpoint exceeds its parent experience")
        checked_artifact({"path": str(checkpoint / "trainer.pt"), "sha256": manifest["trainer_sha256"]}, inputs)
        inherited = [p for p in parent["training_reset_probes"] if p["update"] <= restored]
        if (early_stop_update(inherited, protocol) is not None or (not pending and (
                record["training_reset_probes"][:len(inherited)] != inherited or
                record["initial_training_reset_probe"] != parent["initial_training_reset_probe"]))):
            raise ValueError("Resume lost training-probe history or crossed an early stop")
        updates = parent_updates[:restored] + updates
    elif restored or record.get("resume_parent"):
        raise ValueError("Unexplained restored training state")
    if record.get("interrupted_predecessor"):
        parent, _ = training_history(record["interrupted_predecessor"], registration, protocol, inputs,
                                      registration_sha256, seen)
        if (restored or record.get("resume_from") or parent["status"] not in ("running", "interrupted") or
                parent["run_seed"] != record["run_seed"] or parent.get("restored_update", 0) or parent.get("resume_from") or
                any(c.get("status") == "saved" for c in parent["checkpoints"])):
            raise ValueError("Fresh restart would discard a published checkpoint or replace a failed seed")
    return record, updates


def verify_training(reference, registration, protocol, inputs, registration_sha256):
    record, updates = training_history(reference, registration, protocol, inputs, registration_sha256)
    if record["status"] not in ("completed", "early-stopped", "failed"):
        raise ValueError("Training seed has no completed disposition")
    path = Path(reference["path"])
    settings = registration["training"]
    decisions = len(updates) * settings["rollout_length"]
    result = {"training_seed": record["run_seed"], "status": record["status"], "decisions": decisions,
              "run": reference, "record": record, "training_run": str(path.parent)}
    if record["status"] == "failed":
        if not record.get("error"):
            raise ValueError("Failed training must retain its error")
        return result
    runtime_expected = {"rollout_steps": settings["rollout_length"], **{k: settings[k] for k in (
        "gamma", "gae_lambda", "optimization_epochs", "sequence_length", "entropy_coefficient", "choice_weighted",
        "learning_rate", "clip_epsilon", "max_gradient_norm", "value_coefficient")}}
    info = record["native_training_runtime"]
    if any(type(info.get(k)) is not type(v) or info.get(k) != v for k, v in runtime_expected.items()):
        raise ValueError("Native trainer did not verify the registered effective optimizer/loss configuration")
    if record.get("training_probe_protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("Training-reset early stop was not bound before training")
    probes = record["training_reset_probes"]
    expected_updates = list(range(protocol["early_stop"]["first_eligible_update"], len(updates) + 1,
                                  protocol["early_stop"]["check_every_updates"]))
    if [p["update"] for p in probes] != expected_updates:
        raise ValueError("Required training-only checkpoint probes are missing")
    trigger = early_stop_update(probes, protocol)
    if record["status"] == "early-stopped":
        if trigger != len(updates) or trigger is None:
            raise ValueError("Stopped seed does not match the first registered failure trigger")
        result["early_stop_update"] = trigger
        return result
    if decisions != settings["decisions"] or trigger is not None:
        raise ValueError("Final model has the wrong budget or continued past its registered early stop")
    model = record["model"]
    if (Path(model["path"]).resolve() != path.parent / "inference-weights.pt" or
            model["financial_features"] != settings["financial_features"] or
            digest(model["path"]) != model["sha256"] or record["save_validation"] != {
                "status": "SAVED_INFERENCE_WEIGHTS", "updates": len(updates), "reload_output_max_error": 0}):
        raise ValueError("Only the verified final inference model can enter development selection")
    checked_artifact({k: model[k] for k in ("path", "sha256")}, inputs)
    result["model"] = model
    return result
