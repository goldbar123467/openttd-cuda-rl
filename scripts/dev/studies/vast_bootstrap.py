"""Portable native build and mandatory correctness bundle for one visible GPU."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from local import ROOT, host, source_identity, write_json
from studies.execution_v2 import artifact, code_identity, CORRECTNESS_CHECKS
from studies.protocol_v2 import PROTOCOL_SHA256
from studies.recovery_v2 import launch

REFERENCE_COMMIT = "e5f69435ab53fa85dbfb2a50f03f57bec2f7a405"
OPEN_GFX_SHA256 = "9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c"


def next_attempt(root, name):
    folder = root / name
    folder.mkdir(exist_ok=True, parents=True)
    attempts = sorted(folder.glob("attempt-*"))
    if len(attempts) >= 3:
        raise RuntimeError(f"Three {name} attempts retained; inspect their logs before continuing")
    output = folder / f"attempt-{len(attempts) + 1:03d}"
    output.mkdir(exist_ok=False)
    return output


def command(root, name, argv):
    receipt = {"command": [str(v) for v in argv], "status": "running", "source": source_identity()}
    write_json(root / (name + ".json"), receipt)
    try:
        code = launch(receipt["command"], root / (name + ".log"))
        receipt.update(status="passed" if code == 0 else "failed", returncode=code)
        if code:
            raise RuntimeError(f"{name} failed; inspect {root / (name + '.log')}")
    except BaseException as exc:
        if receipt["status"] == "running":
            receipt.update(status="interrupted", error=str(exc))
        raise
    finally:
        write_json(root / (name + ".json"), receipt)
    return artifact(root / (name + ".json"))


def assets(root):
    target = root / "opengfx-8.0.tar"
    if not target.exists():
        download = root / "opengfx-8.0-all.zip"
        with urllib.request.urlopen("https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip", timeout=120) as response, download.open("xb") as output:
            shutil.copyfileobj(response, output)
        with zipfile.ZipFile(download) as archive:
            members = [n for n in archive.namelist() if Path(n).name == "opengfx-8.0.tar"]
            if len(members) != 1:
                raise ValueError("OpenGFX download has an unexpected layout")
            data = archive.read(members[0])
            if hashlib.sha256(data).hexdigest() != OPEN_GFX_SHA256:
                raise ValueError("OpenGFX 8.0 digest differs")
            target.write_bytes(data)
    if artifact(target)["sha256"] != OPEN_GFX_SHA256:
        raise ValueError("Cached OpenGFX asset changed")
    return target


def build(root, jobs=2):
    stamp = root / "build.json"
    if stamp.exists():
        record = json.loads(stamp.read_text())
        if record["source"] != source_identity() or any(artifact(v["path"]) != v for v in record["binaries"].values()):
            raise ValueError("Persistent study build/source changed")
        return record["binaries"]
    out = next_attempt(root, "builds")
    base = out / "v1-engine"
    engine = out / "v2-engine"
    trainer = out / "training"
    gfx = assets(out)
    python = sys.executable
    command(out, "v1-source", [python, ROOT / "scripts/dev/prepare_engine.py", "--output", base])
    command(out, "v2-source", [python, ROOT / "scripts/dev/prepare_v2.py", "--base-source", base / "source",
        "--output", engine, "--through", "m15-competence", "--build", "--baseset", gfx, "--jobs", jobs])
    command(out, "v2-live", [python, ROOT / "scripts/dev/enable_v2_live.py", "--engine-root", engine, "--jobs", jobs])
    command(out, "training", [python, ROOT / "scripts/dev/local.py", "build", "--v2-policy", "--cuda-root", "/usr/local/cuda",
                              "--build-dir", trainer, "--jobs", jobs])
    reference = out / "reference-source"
    command(out, "reference-checkout", ["git", "worktree", "add", "--detach", reference, REFERENCE_COMMIT])
    command(out, "reference-training", [python, reference / "scripts/dev/local.py", "build", "--v2-policy", "--cuda-root", "/usr/local/cuda",
                                        "--build-dir", out / "reference-training", "--jobs", jobs])
    binaries = {"engine": artifact(engine / "build/openttd"), "trainer": artifact(trainer / "rl_dev_v2_train"),
                "policy": artifact(trainer / "rl_dev_v2_infer"), "reference_trainer": artifact(out / "reference-training/rl_dev_v2_train")}
    write_json(stamp, {"status": "passed", "source": source_identity(), "runtime": host(), "binaries": binaries})
    return binaries


def qualify(root, binaries):
    stamp = root / "qualification.json"
    if stamp.exists():
        return stamp  # execution_v2.preflight rechecks every bound identity.
    out = next_attempt(root, "qualifications")
    checks = {}
    checks["python"] = command(out, "python", [sys.executable, "-m", "unittest", "discover", "-s", "tests/dev"])
    checks["portable-fast"] = command(out, "portable-fast", ["bash", ROOT / "scripts/v2/verify.sh", "--tier", "fast", "--tools-python", "/usr/bin/python3"])
    checks["native"] = command(out, "native", ["ctest", "--test-dir", Path(binaries["trainer"]["path"]).parent,
                                              "--output-on-failure", "--output-junit", out / "native-tests.xml"])
    checks["heldout-refusal"] = command(out, "heldout-refusal", [sys.executable, "-m", "unittest", "discover", "-s", "tests/dev", "-p", "test_heldout_v2.py", "-v"])
    common = ["--trainer", binaries["trainer"]["path"], "--openttd", binaries["engine"]["path"]]
    command(out, "default-equivalence", [sys.executable, ROOT / "scripts/dev/verify_v2_default.py", *common,
        "--reference-trainer", binaries["reference_trainer"]["path"], "--output", out / "default-equivalence"])
    checks["default-equivalence"] = artifact(out / "default-equivalence/verification.json")
    command(out, "recovery", [sys.executable, ROOT / "scripts/dev/verify_v2_recovery.py", *common, "--output", out / "recovery"])
    checks["recovery"] = artifact(out / "recovery/verification.json")
    for label, device in (("cpu", "cpu"), ("cuda", "cuda:0")):
        name = "resume-" + label
        command(out, name, [sys.executable, ROOT / "scripts/dev/verify_v2_resume.py", *common, "--device", device,
            "--guidance", "one-bus-public-plan-v4", "--rollout-length", "64", "--training-map-count", "8",
            "--financial-features", "signed-log-v1", "--entropy-coefficient", ".003", "--policy-loss", "choice-weighted",
            "--asset-potential", "--reuse-bootstrap-tensors", "--output", out / name])
        checks[name] = artifact(out / name / "verification.json")
    if set(checks) != set(CORRECTNESS_CHECKS):
        raise ValueError("Correctness bundle is incomplete")
    write_json(stamp, {"format": "openttd-rl-v2-minimum-correctness-1", "status": "passed", "source": source_identity(),
        "protocol_sha256": PROTOCOL_SHA256, "code_sha256": code_identity(), "runtime": {**host(), "device": "cuda:0"},
        "binaries": {k: v for k, v in binaries.items() if k != "reference_trainer"}, "checks": checks,
        "native_junit": artifact(out / "native-tests.xml"), "limits": "Bounded engineering qualifications; no learning claim"})
    return stamp
