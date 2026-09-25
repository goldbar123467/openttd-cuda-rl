#!/usr/bin/env python3
"""Build, qualify, register and execute the complete frozen single-GPU study.

Run inside an already provisioned Linux CUDA container. No provider credentials,
instance rental, publication, notification or remote deletion is performed.
"""
import argparse
import fcntl
import json
import re
from pathlib import Path
import shutil
import signal
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local import ROOT, host, source_identity, write_json
from studies.evidence_v2 import Inputs
from studies.execution_v2 import artifact, preflight, register
from studies import heldout_v2, recovery_v2, vast_bootstrap
from studies.protocol_v2 import PROTOCOL_SHA256, load_protocol
from studies.training_result_v2 import training_history, verify_training

MINIMUM_INITIAL_FREE_BYTES = 1_250_000_000_000
RESERVE_BYTES = 20 * 1024**3


class Interrupted(BaseException):
    pass


def interrupt(signum, frame):
    raise Interrupted(f"Supervisor interrupted by signal {signum}; retained work resumes on next launch")


def storage(root, required, *, usage=shutil.disk_usage):
    free = usage(root).free
    if free < required:
        raise RuntimeError(f"Insufficient persistent storage: {free} free bytes, {required} required; retained data are preserved")
    return free


def runtime():
    info = host()
    if info["cuda_available"] is not True or info["torch"] != "2.9.1+cu128" or info["torch_cuda"] != "12.8":
        raise ValueError("This package requires PyTorch 2.9.1+cu128 and a visible CUDA GPU; no fallback")
    import torch
    if torch.cuda.device_count() != 1 or torch.cuda.get_device_properties(0).total_memory < 7.5 * 1024**3:
        raise ValueError("Expose exactly one CUDA GPU with at least 8 GB nominal VRAM")
    return info


def training_command(registration_path, registration, seed, output, *, checkpoint=None, restored_update=0, predecessor=None):
    settings = registration["training"]
    total = settings["decisions"] // settings["rollout_length"]
    if seed not in registration["training_seeds"] or not 0 <= restored_update < total:
        raise ValueError("Unregistered training seed or invalid remaining budget")
    command = [sys.executable, str(ROOT / "scripts/dev/train_v2.py"),
        "--openttd", registration["binaries"]["engine"]["path"], "--trainer", registration["binaries"]["trainer"]["path"],
        "--output", str(output), "--study-registration", str(registration_path), "--training-reset-probes",
        "--device", registration["runtime"]["device"], "--seed", str(seed), "--updates", str(total - restored_update),
        "--rollout-length", str(settings["rollout_length"]), "--episode-horizon", str(settings["episode_horizon"]),
        "--training-map-count", "8", "--financial-features", settings["financial_features"],
        "--entropy-coefficient", str(settings["entropy_coefficient"]), "--gae-lambda", str(settings["gae_lambda"]),
        "--guidance", settings["guide"], "--checkpoint-interval", str(settings["checkpoint_interval"]),
        "--policy-loss", "choice-weighted" if settings["choice_weighted"] else "historical", "--reuse-bootstrap-tensors",
        "--gradient-norm", settings["gradient_norm"]]
    if settings["asset_potential"]:
        command.append("--asset-potential")
    if checkpoint is not None:
        command += ["--resume", str(checkpoint)]
    elif predecessor is not None:
        command += ["--interrupted-predecessor", str(predecessor)]
    return command


def resume_point(record):
    """Keep the most recent durable state, including an inherited checkpoint."""
    checkpoints = [c for c in record["checkpoints"] if c["status"] == "saved"]
    if checkpoints:
        last = max(checkpoints, key=lambda c: c["update"])
        return Path(last["path"]), last["update"]
    if record.get("resume_from"):
        return Path(record["resume_from"]), record.get("restored_update", record.get("resume_target", {}).get("update", 0))
    return None, 0


def train_seed(registration_path, root, seed):
    registration, protocol, inputs = preflight(registration_path)
    root.mkdir(parents=True, exist_ok=True)
    # Receipts/logs share the prefix; never mistake them for run directories.
    segments = sorted(p for p in root.glob("segment-*") if p.is_dir() and re.fullmatch(r"segment-\d{3}", p.name))
    receipts = sorted(p for p in root.glob("segment-*.json") if re.fullmatch(r"segment-\d{3}\.json", p.name))
    attempt = max([int(p.stem.split("-")[1]) for p in receipts] + [int(p.name.split("-")[1]) for p in segments] + [0]) + 1
    latest = next((p for p in reversed(segments) if (p / "run.json").exists()), None)
    if receipts and (latest is None or receipts[-1].stem > latest.name or not (latest / "run.json").exists()):
        last_receipt = json.loads(receipts[-1].read_text())
        if last_receipt["status"] not in ("running", "interrupted"):
            raise RuntimeError("Prior training failed before recording its run; inspect the preserved launch log")
    checkpoint, predecessor, restored = None, None, 0
    if latest is not None and (latest / "run.json").exists():
        previous = json.loads((latest / "run.json").read_text())
        if previous["status"] in ("completed", "early-stopped", "failed"):
            verify_training(artifact(latest / "run.json"), registration, protocol, inputs, artifact(registration_path)["sha256"])
            return latest
        if previous["status"] not in ("running", "interrupted"):
            raise ValueError("Unknown interrupted training disposition")
        training_history(artifact(latest / "run.json"), registration, protocol, inputs, artifact(registration_path)["sha256"])
        checkpoint, restored = resume_point(previous)
        if checkpoint is None:
            predecessor = latest / "run.json"
    if attempt > 16:
        raise RuntimeError("Sixteen interrupted segments retained for this seed; inspect infrastructure before resuming")
    storage(root, RESERVE_BYTES + 32 * 1024**3)
    output = root / f"segment-{attempt:03d}"
    command = training_command(registration_path, registration, seed, output, checkpoint=checkpoint,
                               restored_update=restored, predecessor=predecessor)
    receipt_path = root / (output.name + ".json")
    receipt = {"registration": artifact(registration_path), "seed": seed, "command": command, "status": "running",
               "previous_segments": [artifact(p / "run.json") for p in segments if (p / "run.json").exists()]}
    write_json(receipt_path, receipt)
    try:
        code = recovery_v2.launch(command, root / (output.name + ".log"))
        receipt.update(status="finished", returncode=code)
        if not (output / "run.json").exists():
            raise RuntimeError("Training process ended without a run record; inspect its retained launch log")
        record = json.loads((output / "run.json").read_text())
        if record["status"] in ("interrupted", "running"):
            raise Interrupted("Training was interrupted; resume the same registered seed on next launch")
        if (code == 0) != (record["status"] in ("completed", "early-stopped")):
            raise ValueError("Training exit code conflicts with its native run disposition")
        verify_training(artifact(output / "run.json"), registration, protocol, inputs, artifact(registration_path)["sha256"])
        return output
    except BaseException as exc:
        receipt.update(status="interrupted" if isinstance(exc, Interrupted) else "error", error=str(exc))
        raise
    finally:
        write_json(receipt_path, receipt)


def report(root, state):
    lines = ["# Registered V2 recovery study", "", f"Source: `{state['source']['commit']}`", "",
             f"Execution: **{state['status']}**", "", "| Arm | Eligible on development |", "| --- | --- |"]
    for arm, reference in state.get("results", {}).items():
        result = json.loads(Path(reference["path"]).read_text())
        lines.append(f"| {arm} | {result['decision']['eligible']} |")
    lines += ["", "All failed and early-stopped training seeds remain in the study. Three training seeds are imprecise.",
              "Development selection and held-out confirmation are distinct from an engineering PASS.", ""]
    if state.get("heldout_result"):
        heldout = json.loads(Path(state["heldout_result"]["path"]).read_text())
        lines.append(f"Held-out criteria passed: **{heldout['decision']['eligible']}**. Do not tune from these results.")
    elif state.get("status") == "completed":
        lines.append("No arm qualified; no held-out game was opened.")
    (root / "REPORT.md").write_text("\n".join(lines) + "\n")
    write_json(root / "artifact-index.json", {"source": state["source"], "protocol_sha256": PROTOCOL_SHA256,
        "status": state["status"], "study": str(root / "study.json"), "results": state.get("results", {}),
        "heldout_result": state.get("heldout_result"), "registrations": state.get("registrations", {}),
        "retention": "Copy the entire study directory, including interrupted attempts, native traces and weights; original absolute paths are bound to registrations."})


def run(args):
    root = args.root.resolve()
    if root.is_relative_to(ROOT):
        raise ValueError("Keep persistent study data outside the source checkout")
    identity = source_identity()
    if identity["commit"] != args.revision or identity["status"]:
        raise ValueError("Unattended studies require the exact clean committed revision")
    runtime()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".study.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = root / "study.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["source"] != identity or state["protocol_sha256"] != PROTOCOL_SHA256:
                raise ValueError("Existing study belongs to another frozen source/protocol")
            if state["status"] == "completed":
                for reference in state["results"].values():
                    if artifact(reference["path"]) != reference:
                        raise ValueError("Completed result changed")
                    recovery_v2.verify_results(Path(reference["path"]), Inputs())
                if state.get("heldout_result"):
                    if artifact(state["heldout_result"]["path"]) != state["heldout_result"]:
                        raise ValueError("Completed held-out result changed")
                    heldout_v2.execute(root / "heldout/registration.json")
                else:
                    selected, _ = heldout_v2.selected_evidence(list(state["results"].values()), Inputs())
                    if selected is not None:
                        raise ValueError("Completed study omitted required held-out confirmation")
                return
        else:
            free = storage(root, MINIMUM_INITIAL_FREE_BYTES)
            state = {"status": "starting", "source": identity, "protocol_sha256": PROTOCOL_SHA256,
                     "initial_free_bytes": free, "results": {}, "registrations": {}}
        write_json(state_path, state)
        try:
            binaries = vast_bootstrap.build(root)
            qualification = vast_bootstrap.qualify(root, binaries)
            protocol = load_protocol()
            for arm in protocol["arms"]:
                name = arm["id"]
                registration_path = root / "registrations" / name / "registration.json"
                if not registration_path.exists():
                    register(SimpleNamespace(arm=name, study_id="vast-recovery-" + name.lower(),
                        output=registration_path.parent, **{k: Path(binaries[k]["path"]) for k in ("engine", "trainer", "policy")},
                        qualification=[qualification], cost=ROOT / "config/dev/v2-recovery-cost-estimate-2.json"))
                preflight(registration_path)
                state["registrations"][name] = artifact(registration_path)
                state.update(status="running", current_arm=name, phase="training")
                write_json(state_path, state)
                training = [train_seed(registration_path, root / "training" / name / str(seed), seed) for seed in protocol["training_seeds"]]
                state["phase"] = "development"
                write_json(state_path, state)
                controls = None
                if name in ("A1", "A2") and "A0" in state["results"]:
                    candidate = Path(state["results"]["A0"]["path"])
                    old = json.loads(candidate.read_text())
                    if all(c["execution_status"] == "passed" for c in old["cases"] if c["controller"] != "neural"):
                        controls = candidate
                result = recovery_v2.evaluate(SimpleNamespace(registration=registration_path, output=root / "development" / name,
                    training_runs=training, controls_from=controls), before_case=lambda: storage(root, RESERVE_BYTES + 4 * 1024**3))
                state["results"][name] = artifact(result)
                write_json(state_path, state)
                report(root, state)
            selection = root / "heldout"
            if not selection.exists():
                heldout_v2.freeze([Path(ref["path"]) for ref in state["results"].values()], selection)
            if (selection / "registration.json").exists():
                state["phase"] = "heldout"
                write_json(state_path, state)
                result = heldout_v2.execute(selection / "registration.json", before_case=lambda: storage(root, RESERVE_BYTES + 4 * 1024**3))
                state["heldout_result"] = artifact(result)
            elif not (selection / "selection.json").exists():
                raise ValueError("Interrupted held-out registration must be inspected before any access")
            else:
                selected, _ = heldout_v2.selected_evidence(list(state["results"].values()), Inputs())
                if selected is not None:
                    raise ValueError("Held-out selection record omitted an eligible arm")
            state.update(status="completed", phase="reporting")
        except BaseException as exc:
            state.update(status="interrupted" if isinstance(exc, Interrupted) else "error", error=str(exc))
            raise
        finally:
            write_json(state_path, state)
            report(root, state)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        run(parser.parse_args())
    except Interrupted as error:
        print(str(error), file=sys.stderr, flush=True)
        raise SystemExit(75)
