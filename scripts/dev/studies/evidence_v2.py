"""Read-only native episode evidence for reports and registered study decisions."""
import gzip
import hashlib
import json
import math
from pathlib import Path

from service_v2 import summarize
from studies.protocol_v2 import require_episode_identity


class Inputs:
    """Hash stored bytes, including compressed traces; refuse changes mid-read."""
    def __init__(self):
        self.sha256 = {}

    def read(self, path):
        path = Path(path).resolve()
        if path.suffix == ".jsonl":
            compressed = Path(str(path) + ".gz")
            if path.exists() and compressed.exists():
                raise ValueError("Ambiguous raw and compressed trace: " + str(path))
            if not path.exists():
                path = compressed
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if str(path) in self.sha256 and self.sha256[str(path)] != sha:
            raise ValueError("Study input changed: " + str(path))
        self.sha256[str(path)] = sha
        return gzip.decompress(data) if path.suffix == ".gz" else data

    def json(self, path):
        return json.loads(self.read(path))

    def unchanged(self):
        for path, sha in self.sha256.items():
            with Path(path).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                    raise ValueError("Study inputs changed during reporting")


def verify_trace(rows, final, reset, projection, live, *, decisions=512):
    """Check the native reset, action clock, state/economics chain and boundary."""
    request, state = projection["request"], projection["state"]
    aliases = {"map_width": "width", "map_height": "height"}
    for field in ("split", "map_seed", "map_width", "map_height", "simulation_seed", "candidate_tiebreak_seed",
                  "executable_sha256", "town_target", "industry_target", "resource_tier"):
        if reset[field] != request[aliases.get(field, field)]:
            raise ValueError("Native reset projection differs: " + field)
    if (projection["contract_sha256"] != reset["contract_sha256"] or
            reset["company_count"] != 1 or live["company_id"] != 0 or
            live["schema_version"] != "openttd-rl-development-v2-live-1" or
            live["maximum_decisions"] != decisions or live["step_ticks"] != 128):
        raise ValueError("Native contract/company/action budget differs")
    if not rows or len(rows) > decisions:
        raise ValueError("Native trace is empty or exceeds the budget")
    if (rows[0]["tick_before"] != state["date"]["tick"] or
            rows[0]["before"]["balance"] != state["company"]["money"] or
            rows[0]["before"]["loan"] != state["company"]["loan"]):
        raise ValueError("First native transition differs from reset")
    for i, row in enumerate(rows):
        if (type(row["decision"]) is not int or row["decision"] != i + 1 or row["company_id"] != 0 or
                row["tick_after"] - row["tick_before"] != 128 or
                any(type(row[k]) is not bool for k in ("terminal", "truncated")) or
                (i < len(rows) - 1 and (row["terminal"] or row["truncated"]))):
            raise ValueError("Native trace has an invalid clock, company or early boundary")
        for economy in (row["before"], row["after"]):
            if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in economy.values()):
                raise ValueError("Nonfinite native economy")
        if i and (row["tick_before"] != rows[i - 1]["tick_after"] or
                  row["state_before"] != rows[i - 1]["state_after"] or row["before"] != rows[i - 1]["after"]):
            raise ValueError("Native trace clock/state/economics chain is discontinuous")
    last = rows[-1]
    if (final["company_id"] != 0 or final["pending_step"] or final["decisions"] != len(rows) or
            final["maximum_decisions"] != decisions or final["step_ticks"] != 128 or
            final["tick"] != last["tick_after"] or final["token"] != last["state_after"] or
            final["economy"] != last["after"] or final["terminal"] != last["terminal"] or
            final["truncated"] != last["truncated"] or not (last["terminal"] or last["truncated"]) or
            (not last["terminal"] and len(rows) != decisions)):
        raise ValueError("Final observation does not certify the complete native episode boundary")
    result = summarize(rows, {"economy": rows[0]["before"], "tick": rows[0]["tick_before"]}, final)
    if any(isinstance(value, (float, int)) and not math.isfinite(value) for value in result.values()):
        raise ValueError("Nonfinite native summary")
    return result


def load_episode(root, inputs, *, legacy_sampled_control=False):
    """Load a full development episode; this function never launches a game."""
    root = Path(root).resolve()
    run = inputs.json(root / "run.json")
    reset = inputs.json(root / "worker/reset.json")
    if (run["status"] not in ("passed", "completed") or run["split"] != "development" or
            reset["split"] != "development" or run.get("final_evaluation_accessed") is not False or
            run["decisions"] != 512 or run["engine_sha256"] != reset["executable_sha256"] or
            run["map_seed"] != reset["map_seed"] or type(run["map_seed"]) is not int):
        raise ValueError("Full development run identity differs from the native reset")
    rows = [json.loads(line) for line in inputs.read(root / "worker/transitions.jsonl").splitlines()]
    summary = verify_trace(rows, run["final_observation"], reset,
                           inputs.json(root / "worker/reset-projection.json"), inputs.json(root / "worker/live.json"))
    if "summary" in run and run["summary"] != summary:
        raise ValueError("Stored summary differs from independently rederived native economics")
    neural = bool(run.get("training_run"))
    mode = run.get("mode")
    if mode is None and legacy_sampled_control and not neural:
        mode = "sampled"
    if mode not in ("greedy", "sampled"):
        raise ValueError("Action mode must be explicit; historical sampled controls require an explicit legacy option")
    seed = run["run_seed"] if neural else run["sampling_seed"]
    if type(seed) is not int:
        raise ValueError("Action seed must be an explicit integer")
    entry = {"source": str(root), "split": "development", "map_seed": run["map_seed"], "mode": mode,
             "sampling_seed": seed, "guidance": run["guidance"], "execution_status": "passed", "summary": summary,
             "controller": "neural" if neural else run["controller"], "record": run, "reset": reset,
             "legacy_assumed_sampled_mode": "mode" not in run}
    if neural:
        training_root = Path(run["training_run"]).resolve()
        training = inputs.json(training_root / "run.json")
        model = Path(training["model"]["path"]).resolve()
        if (training["status"] != "completed" or training["kind"] != "native-v2-live-recurrent-ppo" or
                training["model"] != run["model"] or model != training_root / "inference-weights.pt" or
                hashlib.sha256(inputs.read(model)).hexdigest() != training["model"]["sha256"] or
                type(training["run_seed"]) is not int or training["engine_sha256"] != run["engine_sha256"] or
                training.get("financial_features", "raw") != run.get("financial_features", "raw") or
                training["guidance"] != run["trained_guidance"]):
            raise ValueError("Evaluation does not identify the completed training run and its final model")
        entry.update(training_seed=training["run_seed"], training=training,
                     model_sha256=training["model"]["sha256"], training_run=str(training_root))
    return entry


def verify_registered_episode(entry, case, registration, *, training_run=None):
    """Additional prospective checks; legacy mode assumptions are never accepted."""
    run, reset = entry["record"], entry["reset"]
    require_episode_identity(run, reset, case, engine_sha256=registration["binaries"]["engine"]["sha256"],
                             guidance=registration["training"]["guide"])
    if entry["legacy_assumed_sampled_mode"] or run["source"] != registration["source"]:
        raise ValueError("Registered evaluation source or explicit mode differs")
    if training_run is None:
        if entry["controller"] not in ("uniform", "scripted"):
            raise ValueError("Unregistered public control")
    elif (entry["controller"] != "neural" or Path(run["training_run"]).resolve() != Path(training_run).resolve() or
          run["policy_sha256"] != registration["binaries"]["policy"]["sha256"] or
          run.get("guidance_override") is not None or run["device"] != registration["runtime"]["device"] or
          run.get("onnx_package") is not None):
        raise ValueError("Registered model/policy/backend differs or uses a guide override")


def public_case(entry):
    return {k: v for k, v in entry.items() if k not in ("record", "reset", "training")}
