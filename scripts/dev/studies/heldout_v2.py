"""Single registered generalization confirmation, after all mandatory arms.

Ordinary launchers cannot enter this path. Frozen eligibility is rederived from
native development evidence before issuing any in-memory game permits. Each
held-out case is reserved on disk before access and is never replayed after an
interruption. The separate final split is never used.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluate_guide_v2
import infer_v2
from live_v2 import LiveV2, _reset_manifest_payload
from local import write_json
from studies.evidence_v2 import Inputs, load_episode, public_case, verify_registered_episode
from studies.execution_v2 import artifact, checked_artifact, digest, preflight
from studies.protocol_v2 import PROTOCOL_SHA256, development_matrix
from studies.recovery_decision import decide_arm, select_arm
from studies.recovery_v2 import case_name, verify_results


def selected_evidence(results, inputs):
    verified = [verify_results(checked_artifact(ref, inputs), inputs) for ref in results]
    protocol = preflight(checked_artifact(inputs.json(results[0]["path"])["registration"], inputs), inputs=inputs)[1]
    chosen = select_arm([item[3] for item in verified], protocol)
    first = verified[0][0]
    for registration, _, _, _ in verified:
        if any(registration[k] != first[k] for k in ("source", "code_sha256", "binaries", "content", "runtime")):
            raise ValueError("Mandatory arms did not use the same frozen executable source and runtime")
    if chosen is None:
        return None, protocol
    return next(item for item in verified if item[0]["arm"] == chosen), protocol


def freeze(results, output):
    inputs = Inputs()
    references = [artifact(path) for path in results]
    selected, protocol = selected_evidence(references, inputs)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if selected is None:
        write_json(output / "selection.json", {"status": "no-eligible-arm", "held_out_accessed": False,
                                              "protocol_sha256": PROTOCOL_SHA256, "development_results": references})
        return None
    registration, training, _, decision = selected
    selected_result = next(inputs.json(ref["path"]) for ref in references if inputs.json(ref["path"])["decision"]["arm"] == registration["arm"])
    frozen = {"format": "openttd-rl-v2-heldout-registration-1", "protocol_sha256": PROTOCOL_SHA256,
              "selected_arm": registration["arm"], "development_results": references,
              "execution_registration": selected_result["registration"], "source": registration["source"],
              "models": [{"training_seed": t["training_seed"], "run": t["run"],
                          "weights": {k: t["model"][k] for k in ("path", "sha256")}} for t in training],
              "split": "generalization", "maps": protocol["held_out"]["maps"],
              "access_directory": str(output / "access"), "selection": decision,
              "accesses_per_case": 1, "tuning_from_results": False, "final_split_access": False}
    inputs.unchanged()
    path = output / "registration.json"
    with path.open("x") as stream:
        stream.write(json.dumps(frozen, indent=2, allow_nan=False) + "\n")
    with path.with_suffix(".sha256").open("x") as stream:
        stream.write(digest(path) + "\n")
    return path


def open_registration(path):
    inputs = Inputs()
    path = Path(path).resolve()
    data = inputs.read(path)
    if hashlib.sha256(data).hexdigest() != inputs.read(path.with_suffix(".sha256")).decode().strip():
        raise ValueError("Held-out registration changed")
    frozen = json.loads(data)
    if (frozen.get("format") != "openttd-rl-v2-heldout-registration-1" or frozen["protocol_sha256"] != PROTOCOL_SHA256 or
            frozen["split"] != "generalization" or frozen["accesses_per_case"] != 1 or
            frozen["tuning_from_results"] is not False or frozen["final_split_access"] is not False or
            Path(frozen["access_directory"]) != path.parent / "access"):
        raise ValueError("Held-out registration does not implement the frozen one-access protocol")
    selected, protocol = selected_evidence(frozen["development_results"], inputs)
    if selected is None:
        raise ValueError("No eligible development arm; held-out access forbidden")
    registration, training, _, decision = selected
    expected_models = [{"training_seed": t["training_seed"], "run": t["run"],
                        "weights": {k: t["model"][k] for k in ("path", "sha256")}} for t in training]
    registered, _, _ = preflight(checked_artifact(frozen["execution_registration"], inputs), inputs=inputs)
    if (frozen["selected_arm"] != decision["arm"] or json.loads(json.dumps(decision)) != frozen["selection"] or
            frozen["models"] != expected_models or registered != registration or frozen["source"] != registration["source"] or
            frozen["maps"] != protocol["held_out"]["maps"]):
        raise ValueError("Frozen selection/models/source differ from verified development eligibility")
    inputs.unchanged()
    return frozen, registration, protocol, training, inputs


def jobs(training, protocol):
    result = []
    for model in training:
        result.extend({**case, "controller": "neural", "training_seed": model["training_seed"],
                       "training_run": model["training_run"]} for case in development_matrix(protocol, split="generalization"))
    for control in protocol["controls"]["controllers"]:
        result.extend({**case, "controller": control} for case in development_matrix(protocol, split="generalization"))
    return result


class _Permit:
    def __init__(self, reference, frozen, registration, case, output):
        self.reference, self.frozen, self.registration = reference, frozen, registration
        self.case, self.output = case, output
        self.validated = False
        self.used = False

    def validate(self, args, controller):
        case, registration = self.case, self.registration
        if (self.used or controller != case["controller"] or args.split != "generalization" or
                args.map_seed != case["map_seed"] or args.mode != case["mode"] or args.seed != case["sampling_seed"] or
                args.decisions != 512 or args.output.resolve() != self.output or
                artifact(args.openttd) != registration["binaries"]["engine"] or
                getattr(args, "visible", False) or getattr(args, "compare_cpu", False) or
                getattr(args, "onnx_package", None) is not None or getattr(args, "guidance_override", None) is not None):
            raise ValueError("Held-out invocation differs from its reserved case")
        if controller == "neural":
            if (str(args.training_run.resolve()) != case["training_run"] or
                    artifact(args.policy) != registration["binaries"]["policy"] or args.device != registration["runtime"]["device"]):
                raise ValueError("Held-out model/backend differs")
        elif args.guidance != registration["training"]["guide"]:
            raise ValueError("Held-out control guide differs")
        preflight(Path(self.frozen["execution_registration"]["path"]))
        if artifact(self.reference["path"]) != self.reference:
            raise ValueError("Held-out registration changed before game access")
        for model in self.frozen["models"]:
            if artifact(model["run"]["path"]) != model["run"] or artifact(model["weights"]["path"]) != model["weights"]:
                raise ValueError("Held-out model changed before game access")
        self.validated = True

    def live(self, engine, output, **kwargs):
        if (not self.validated or self.used or kwargs.get("split") != "generalization" or
                kwargs.get("seed") != self.case["map_seed"] or kwargs.get("decisions") != 512 or
                Path(output) != self.output / "worker"):
            raise ValueError("Held-out game has no unused validated permit")
        self.used = True
        def manifest(executable, baseset, seed, split):
            if split != "generalization" or seed != self.case["map_seed"]:
                raise ValueError("Held-out reset differs from the reserved case")
            return _reset_manifest_payload(executable, baseset, seed, split)
        return LiveV2(engine, output, _reset_factory=manifest, **kwargs)


def execute(path, *, before_case=lambda: None):
    verified = open_registration(path)
    root = Path(verified[0]["access_directory"])
    root.mkdir(exist_ok=True)
    with (root / ".access.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _execute(path, before_case, verified)


def _execute(path, before_case, verified):
    frozen, registration, protocol, training, inputs = verified
    reference = artifact(path)
    root = Path(frozen["access_directory"])
    root.mkdir(exist_ok=True)
    (root / "receipts").mkdir(exist_ok=True)
    cases = []
    for case in jobs(training, protocol):
        before_case()
        name = case_name(case)
        output = root / name
        receipt_path = root / "receipts" / (name + ".json")
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt["case"] != case or receipt["registration"] != reference:
                raise ValueError("Held-out access receipt changed")
            if receipt["status"] == "reserved":
                receipt.update(status="failed", error="Interrupted after reservation; held-out case is never repeated")
                write_json(receipt_path, receipt)
        else:
            permit = _Permit(reference, frozen, registration, case, output)
            args = SimpleNamespace(output=output, openttd=Path(registration["binaries"]["engine"]["path"]),
                map_seed=case["map_seed"], split="generalization", mode=case["mode"], seed=case["sampling_seed"], decisions=512,
                policy=Path(registration["binaries"]["policy"]["path"]), device=registration["runtime"]["device"],
                training_run=Path(case["training_run"]) if case["controller"] == "neural" else None,
                guidance=registration["training"]["guide"], compare_cpu=False, controller=case["controller"])
            permit.validate(args, case["controller"])
            receipt = {"case": case, "registration": reference, "status": "reserved"}
            # This durable claim consumes the sole permitted attempt.
            write_json(receipt_path, receipt)
            try:
                with (root / (name + ".log")).open("x") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                    function = infer_v2.run if case["controller"] == "neural" else evaluate_guide_v2.run
                    function(args, heldout_permit=permit)
                receipt.update(status="passed", run=artifact(output / "run.json"))
            except Exception as exc:
                receipt.update(status="failed", error=str(exc))
            finally:
                write_json(receipt_path, receipt)
        if receipt["status"] == "passed":
            checked_artifact(receipt["run"], inputs)
            entry = load_episode(output, inputs, heldout_registration=reference)
            verify_registered_episode(entry, case, registration, training_run=case.get("training_run"), split="generalization")
            row = {**case, **public_case(entry), "run": receipt["run"]}
        elif receipt["status"] == "failed":
            row = {**case, "guidance": registration["training"]["guide"], "execution_status": "failed", "summary": None,
                   "receipt": artifact(receipt_path)}
        else:
            raise ValueError("Unknown held-out access disposition")
        cases.append(row)
        write_json(root / "cases.json", cases)
    decision = decide_arm(registration["arm"], training, [c for c in cases if c["controller"] == "neural"],
                          [c for c in cases if c["controller"] != "neural"], protocol, split="generalization")
    inputs.unchanged()
    write_json(root / "result.json", {"status": "completed", "registration": reference, "cases": cases, "decision": decision,
        "inputs_sha256": inputs.sha256, "final_split_accessed": False, "allow_tuning_from_results": False,
        "claim": protocol["held_out"]["claim_limit"]})
    return root / "result.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path, required=True)
    execute(parser.parse_args().registration)
