"""Frozen recovery protocol and exact full-development matrix validation."""
import hashlib
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local import ROOT

PROTOCOL_PATH = ROOT / "config/dev/v2-recovery-study-protocol-1.json"
PROTOCOL_SHA256 = "50b27a8d31b54485af847ae2478454a401efe9d0f0f8ab16c8a84398aa26f3d0"
REGISTRATION_SCHEMA = ROOT / "docs/project/schema/dev-study-registration.schema.json"


def load_protocol(path=PROTOCOL_PATH):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("Frozen recovery protocol identity changed; amendments require explicit versioning before tuning")
    protocol = json.loads(data)
    contract_path = ROOT / protocol["contract_path"]
    contract_data = contract_path.read_bytes()
    if hashlib.sha256(contract_data).hexdigest() != protocol["contract_sha256"]:
        raise ValueError("Recovery reset contract changed")
    sets = json.loads(contract_data)["seeds"]["sets"]
    if (protocol["development"]["maps"] != sets["development"]["seeds"] or
            protocol["held_out"]["maps"] != sets["generalization"]["seeds"] or
            protocol["training_maps"] != sets["training"]["seeds"][:8]):
        raise ValueError("Protocol map partitions disagree with the native reset contract")
    return protocol


def development_matrix(protocol):
    settings = protocol["development"]
    return [{"split": "development", "map_seed": m, "mode": mode, "sampling_seed": seed}
            for m in settings["maps"]
            for mode, seeds in (("greedy", [settings["greedy_action_seed"]]), ("sampled", settings["sampled_action_seeds"]))
            for seed in seeds]


def validate_registration(registration, protocol):
    import jsonschema
    schema = json.loads(REGISTRATION_SCHEMA.read_text())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(registration)
    # jsonschema's date-time checker is optional in some local environments.
    datetime.strptime(registration["registered_utc"], "%Y-%m-%dT%H:%M:%SZ")
    if registration["protocol_sha256"] != PROTOCOL_SHA256:
        raise ValueError("Execution registration refers to another recovery protocol")
    arm = next(arm for arm in protocol["arms"] if arm["id"] == registration["arm"])
    expected = {**protocol["fixed_training"], **{k: v for k, v in arm.items() if k != "id"}}
    if json.dumps(registration["training"], sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True):
        raise ValueError("Execution training settings differ from the registered arm")
    if registration["driver"] not in registration["code_sha256"]:
        raise ValueError("Execution registration must bind its actual driver source")
    for name in registration["code_sha256"]:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not name.startswith(("scripts/", "training/", "integration/", "config/")):
            raise ValueError("Registered code identity must be a repository source path")
    if not Path(registration["source_archive"]).is_absolute():
        raise ValueError("Source archive must use an absolute path")
    for artifact in [*registration["binaries"].values(), *registration["qualification_reports"], registration["cost_estimate"]]:
        if not Path(artifact["path"]).is_absolute():
            raise ValueError("Registered artifacts must use absolute paths")


def case_key(row):
    if type(row["map_seed"]) is not int or type(row["sampling_seed"]) is not int:
        raise ValueError("Evaluation map/action seeds must be explicit integers")
    return row["split"], row["map_seed"], row["mode"], row["sampling_seed"]


def require_development_matrix(rows, protocol):
    expected = {case_key(r) for r in development_matrix(protocol)}
    actual = [case_key(row) for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Development comparison requires all eight maps, one greedy and three sampled seeds, without duplicates")


def require_episode_identity(record, reset, case, *, engine_sha256, guidance, decisions=512):
    if (record["status"] not in ("passed", "completed") or record["split"] != "development" or
            reset["split"] != "development" or reset["map_seed"] != case["map_seed"] or
            record["map_seed"] != case["map_seed"] or record["mode"] != case["mode"] or
            record.get("run_seed", record.get("sampling_seed")) != case["sampling_seed"] or
            record["engine_sha256"] != engine_sha256 or record["guidance"] != guidance or
            record["decisions"] != decisions or record.get("final_evaluation_accessed") is not False):
        raise ValueError("Completed episode differs from its registered development split/map/guide/mode/seed/budget/engine")
    # Completion includes early true terminals; never call a short nonterminal
    # smoke a full-horizon evaluation. Failed outcomes remain in the study report.
    final = record["final_observation"]
    if not (final["terminal"] or final["truncated"]):
        raise ValueError("Development episode has not reached a native boundary")
