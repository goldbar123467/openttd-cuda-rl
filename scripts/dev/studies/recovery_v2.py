"""Register and evaluate frozen recovery arms on the complete development matrix.

Training results must already satisfy the registered native/probe contract. This
entry point never silently substitutes a legacy run, an intermediate model, or a
short screening game. Training execution is integrated after recovery mechanisms
and their read-only probes are qualified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local import ROOT, capture_source, source_identity, write_json
from studies.evidence_v2 import Inputs, load_episode, public_case, verify_registered_episode
from studies.execution_v2 import artifact, checked_artifact, digest, preflight, register
from studies.protocol_v2 import development_matrix, require_development_matrix
from studies.recovery_decision import decide_arm
from studies.training_result_v2 import verify_training


def schedule(training, protocol):
    jobs = []
    for result in training:
        if result["status"] == "completed":
            jobs.extend({**case, "controller": "neural", "training_seed": result["training_seed"],
                         "training_run": result["training_run"]} for case in development_matrix(protocol))
    for controller in protocol["controls"]["controllers"]:
        jobs.extend({**case, "controller": controller} for case in development_matrix(protocol))
    return jobs


def case_name(case):
    actor = "model-" + str(case["training_seed"]) if case["controller"] == "neural" else case["controller"]
    return f"{actor}-{case['mode']}-m{case['map_seed']}-s{case['sampling_seed']}"


def case_command(case, registration, output):
    common = ["--openttd", registration["binaries"]["engine"]["path"], "--output", str(output),
              "--split", "development", "--map-seed", str(case["map_seed"]),
              "--seed", str(case["sampling_seed"]), "--mode", case["mode"], "--decisions", "512"]
    if case["controller"] == "neural":
        return [sys.executable, str(ROOT / "scripts/dev/infer_v2.py"), *common,
                "--policy", registration["binaries"]["policy"]["path"], "--device", registration["runtime"]["device"],
                "--training-run", case["training_run"]]
    return [sys.executable, str(ROOT / "scripts/dev/evaluate_guide_v2.py"), *common,
            "--controller", case["controller"], "--guidance", registration["training"]["guide"]]


def launch(command, log):
    with log.open("x") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait()
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=15)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            raise


def validate_training_set(training, protocol):
    if len(training) != len(protocol["training_seeds"]) or sorted(t["training_seed"] for t in training) != sorted(protocol["training_seeds"]):
        raise ValueError("All three training seeds, including failed/stopped ones, must be retained exactly once")


def load_case(reference, case, registration, inputs):
    path = checked_artifact(reference, inputs)
    if path.name != "run.json":
        raise ValueError("Case reference must identify its run record")
    entry = load_episode(path.parent, inputs)
    verify_registered_episode(entry, case, registration, training_run=case.get("training_run"))
    if entry["controller"] != case["controller"] or entry.get("training_seed") != case.get("training_seed"):
        raise ValueError("Registered controller/model seed differs")
    reset = entry["reset"]
    if reset["content_manifest_sha256"] != registration["content"]["sha256"]:
        raise ValueError("Game content differs from the registered control/model environment")
    for field, file in (("contract_sha256", "config/v2/m15-scalable-contract.json"),
                        ("settings_manifest_sha256", "config/v2/setting-inventory.json")):
        if reset[field] != registration["code_sha256"][file]:
            raise ValueError("Native reset contract/settings differ")
    if reset["map_width"] != 64 or reset["map_height"] != 64:
        raise ValueError("Native map dimensions differ from the registered matrix")
    return {**case, **public_case(entry), "run": reference}


def evaluate_jobs(registration, protocol, training, root, inputs, *, launcher=launch, reader=load_case, reused_controls=(), before_case=lambda: None):
    """Run every scheduled case; injected callables are for executor tests only."""
    cases = list(reused_controls)
    if cases:
        for controller in protocol["controls"]["controllers"]:
            require_development_matrix([c for c in cases if c["controller"] == controller], protocol)
        if any(c["execution_status"] != "passed" or c["controller"] not in protocol["controls"]["controllers"] for c in cases):
            raise ValueError("Only a complete verified same-guide control matrix can be reused")
    (root / "cases").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    for job in schedule(training, protocol):
        if reused_controls and job["controller"] != "neural":
            continue
        before_case()
        name = case_name(job)
        existing = sorted((root / "logs").glob(name + "-attempt-*.json"))
        receipt, receipt_path = None, None
        if existing:
            receipt_path = existing[-1]
            receipt = json.loads(receipt_path.read_text())
            if receipt["case"] != job or receipt["source"] != registration["source"]:
                raise ValueError("Existing evaluation receipt differs from the registered job")
            output = Path(receipt["output"])
            if receipt["command"] != case_command(job, registration, output):
                raise ValueError("Existing evaluation command changed")
            if receipt["status"] in ("running", "interrupted"):
                child = json.loads((output / "run.json").read_text()) if (output / "run.json").exists() else None
                if child and child["status"] in ("passed", "completed"):
                    # A completed native boundary can survive a supervisor crash.
                    reader(artifact(output / "run.json"), job, registration, inputs)
                    receipt.update(status="passed", returncode=0, recovered_completed_child=True)
                    write_json(receipt_path, receipt)
                elif child and child["status"] == "failed":
                    receipt.update(status="failed", returncode=1, recovered_failed_child=True)
                    write_json(receipt_path, receipt)
                else:
                    receipt = None  # Retain this attempt; replay only incomplete infrastructure work.
        if receipt is None:
            if len(existing) >= 3:
                raise RuntimeError("Three interrupted evaluation attempts retained; operator attention required")
            attempt = f"{name}-attempt-{len(existing) + 1:03d}"
            output = root / "cases" / attempt
            command = case_command(job, registration, output)
            receipt = {"case": job, "command": command, "status": "running", "output": str(output),
                       "source": registration["source"], "registration_source_sha256": registration["source"]["working_files_sha256"]}
            receipt_path = root / "logs" / (attempt + ".json")
            write_json(receipt_path, receipt)
            try:
                code = launcher(command, root / "logs" / (attempt + ".log"))
                receipt.update(status="passed" if code == 0 else "failed", returncode=code)
            except BaseException as exc:
                receipt.update(status="interrupted", error=str(exc))
                raise
            finally:
                write_json(receipt_path, receipt)
        if receipt["status"] not in ("passed", "failed"):
            raise ValueError("Unknown evaluation execution disposition")
        code = receipt["returncode"]
        if type(code) is not int or (receipt["status"] == "passed") != (code == 0):
            raise ValueError("Evaluation receipt status and exit code disagree")
        inputs.read(receipt_path)
        if code == 0:
            row = reader(artifact(output / "run.json"), job, registration, inputs)
        else:
            row = {**job, "guidance": registration["training"]["guide"], "execution_status": "failed",
                   "launch": artifact(receipt_path), "summary": None, "run": None}
            if (output / "run.json").exists():
                row["run"] = artifact(output / "run.json")
                failed = inputs.json(output / "run.json")
                if failed.get("status") != "failed":
                    raise ValueError("Failed child exit conflicts with a nonfailed native run record")
        cases.append(row)
        write_json(root / "cases.json", cases)
        print(json.dumps({"case": name, "execution_status": row["execution_status"], "cases_finished": len(cases)}), flush=True)
    return cases


def verify_results(path, inputs):
    """Recompute development eligibility from immutable inputs, never a bool."""
    result = inputs.json(path)
    if result.get("format") != "openttd-rl-v2-development-study-result-1" or result.get("status") != "completed":
        raise ValueError("All scheduled study work must have a completed disposition")
    registration_path = checked_artifact(result["registration"], inputs)
    # The same frozen source/runtime is used across the mandatory arms.
    registration, protocol, _ = preflight(registration_path, inputs=inputs)
    sha = result["registration"]["sha256"]
    training = [verify_training(t["run"], registration, protocol, inputs, sha) for t in result["training"]]
    validate_training_set(training, protocol)
    expected = {case_name(c): c for c in schedule(training, protocol)}
    actual = [case_name(c) for c in result["cases"]]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ValueError("Completed result has a missing, duplicate or extra scheduled case")
    for name, expected_sha in result["inputs_sha256"].items():
        checked_artifact({"path": name, "sha256": expected_sha}, inputs)
    cases = []
    for stored in result["cases"]:
        case = expected[case_name(stored)]
        if stored["execution_status"] == "passed":
            verified = load_case(stored["run"], case, registration, inputs)
            if verified["summary"] != stored["summary"]:
                raise ValueError("Study summary changed from native economics")
            cases.append(verified)
        elif stored["execution_status"] == "failed":
            receipt = inputs.json(checked_artifact(stored["launch"], inputs))
            if (receipt["case"] != case or receipt["status"] != "failed" or receipt["returncode"] == 0 or
                    receipt["source"] != registration["source"] or
                    receipt["command"] != case_command(case, registration, Path(receipt["output"]))):
                raise ValueError("Failed case has no matching failed execution receipt")
            if stored["run"] is not None:
                run = inputs.json(checked_artifact(stored["run"], inputs))
                if run["status"] != "failed":
                    raise ValueError("Failed run status changed")
            cases.append({**case, "guidance": registration["training"]["guide"], "execution_status": "failed", "summary": None})
        else:
            raise ValueError("Undisposed study case")
    decision = decide_arm(registration["arm"], training, [c for c in cases if c["controller"] == "neural"],
                          [c for c in cases if c["controller"] != "neural"], protocol)
    if json.loads(json.dumps(decision)) != result["decision"]:
        raise ValueError("Stored eligibility differs from the frozen decision recomputed from native inputs")
    inputs.unchanged()
    return registration, training, cases, decision


def evaluate(args, *, before_case=lambda: None):
    inputs = Inputs()
    registration, protocol, _ = preflight(args.registration, inputs=inputs)
    registration_ref = artifact(args.registration)
    training = [verify_training(artifact(p / "run.json"), registration, protocol, inputs, registration_ref["sha256"])
                for p in args.training_runs]
    validate_training_set(training, protocol)
    reused = []
    if args.controls_from:
        old, _, cases, _ = verify_results(args.controls_from, inputs)
        if any(old[k] != registration[k] for k in ("source", "code_sha256", "binaries", "content", "runtime")) or old["training"]["guide"] != registration["training"]["guide"]:
            raise ValueError("Control source/binary/content/runtime/guide identities differ")
        reused = [c for c in cases if c["controller"] != "neural"]
    root = args.output.resolve()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
        capture_source(root / "source")
    else:
        prior = json.loads((root / "result.json").read_text())
        if prior["registration"] != registration_ref or prior["source"] != registration["source"]:
            raise ValueError("Cannot resume another registered evaluation")
        if prior["status"] == "completed":
            verify_results(root / "result.json", inputs)
            return root / "result.json"
    result = {"format": "openttd-rl-v2-development-study-result-1", "status": "running",
              "source": source_identity(), "registration": registration_ref,
              "training": [{k: v for k, v in t.items() if k != "record"} for t in training],
              "cases": [], "decision": None, "controls_from": artifact(args.controls_from) if args.controls_from else None}
    write_json(root / "result.json", result)
    try:
        cases = evaluate_jobs(registration, protocol, training, root, inputs, reused_controls=reused, before_case=before_case)
        result["cases"] = cases
        result["decision"] = decide_arm(registration["arm"], training, [c for c in cases if c["controller"] == "neural"],
                                         [c for c in cases if c["controller"] != "neural"], protocol)
        preflight(args.registration, inputs=inputs)
        inputs.unchanged()
        result["status"] = "completed"
    except BaseException as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        result["inputs_sha256"] = inputs.sha256
        write_json(root / "result.json", result)
    print(json.dumps({"status": result["status"], "arm": registration["arm"], "eligible": result["decision"]["eligible"]}))
    return root / "result.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("register")
    create.add_argument("--arm", choices=("A0", "A1", "A2", "A3"), required=True)
    create.add_argument("--study-id", required=True)
    for name in ("output", "engine", "trainer", "policy", "cost"):
        create.add_argument("--" + name, type=Path, required=True)
    create.add_argument("--qualification", type=Path, nargs="+", required=True)
    execute = commands.add_parser("evaluate")
    for name in ("registration", "output"):
        execute.add_argument("--" + name, type=Path, required=True)
    execute.add_argument("--training-runs", type=Path, nargs=3, required=True)
    execute.add_argument("--controls-from", type=Path)
    args = parser.parse_args()
    print(register(args)) if args.command == "register" else evaluate(args)
