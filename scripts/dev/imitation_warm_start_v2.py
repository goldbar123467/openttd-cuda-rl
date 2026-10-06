"""Validate supervised-policy ancestry before fresh live PPO or evaluation."""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_imitation_run(directory, *, observation_schema=None, financial_features=None):
    root = Path(directory).resolve()
    manifest = root / "run.json"
    record = json.loads(manifest.read_text())
    if record.get("kind") != "native-v2-human-imitation" or record.get("status") != "completed":
        raise ValueError("Warm start requires a completed native human-imitation run")
    if observation_schema is not None and record.get("observation_schema_id") != observation_schema:
        raise ValueError("Imitation/PPO observation schema differs")
    if financial_features is not None and record.get("financial_features") != financial_features:
        raise ValueError("Imitation/PPO financial preprocessing differs")
    model = record["model"]
    weights = Path(model["path"]).resolve()
    if weights != root / "inference-weights.pt" or digest(weights) != model["sha256"]:
        raise ValueError("Imitation weights path/hash differs")
    if model.get("financial_features") != record.get("financial_features"):
        raise ValueError("Imitation model preprocessing metadata differs")
    if record.get("financial_features") in ("signed-log-orders-v1", "signed-log-orders-v2", "signed-log-orders-v3"):
        if (record.get("observation_schema_id") != "v2-m15-public-development-orders-v1" or
                record.get("action_semantics") != "orders-v1" or model.get("action_semantics") != "orders-v1" or
                model.get("observation_schema_id") != record["observation_schema_id"]):
            raise ValueError("Imitation order observation/action metadata differs")
    ancestry = {"kind": record["kind"], "run": str(manifest), "run_sha256": digest(manifest),
                "weights": str(weights), "weights_sha256": model["sha256"],
                "observation_schema_id": record["observation_schema_id"],
                "financial_features": record["financial_features"],
                "guidance": record.get("guidance", "none"),
                "optimizer": "fresh-PPO-Adam", "recurrent_state": "reset",
                "claim": "Policy initialization only; human examples never enter the on-policy PPO rollout"}
    return record, ancestry


def import_imitation(trainer, ancestry):
    # Recheck immediately before loading, after process startup/configuration.
    if digest(ancestry["weights"]) != ancestry["weights_sha256"]:
        raise ValueError("Imitation weights changed before native import")
    result = trainer.request(f"IMPORT_WEIGHTS\t{ancestry['weights']}")
    expected = {"status": "IMPORTED_WEIGHTS", "updates": 0,
                "optimizer_reset": True, "recurrent_reset": True}
    if result != expected:
        raise ValueError("Native PPO did not confirm a fresh imitation-policy import")
    return result
