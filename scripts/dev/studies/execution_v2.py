"""Shared preflight and immutable registration for the recovery executors."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET

from local import ROOT, capture_source, host, source_identity
from studies.evidence_v2 import Inputs
from studies.protocol_v2 import PROTOCOL_SHA256, load_protocol, validate_registration

CODE_ROOTS = ("scripts/dev", "scripts/v1", "training/dev", "training/v1", "training/v2", "integration/dev", "config/v2", "config/dev")
CODE_SUFFIXES = {".py", ".cpp", ".cc", ".h", ".hpp", ".inc", ".json", ".cmake", ".patch"}
RUNTIME_FIELDS = ("python", "python_executable", "platform", "torch", "torch_cuda", "cuda_available", "gpu", "compute_capability")
DRIVER = "scripts/dev/studies/recovery_v2.py"
CORRECTNESS_CHECKS = ("python", "portable-fast", "native", "heldout-refusal", "default-equivalence", "recovery", "resume-cpu", "resume-cuda")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": digest(path)}


def code_identity(root=ROOT):
    result = {}
    for folder in CODE_ROOTS:
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and (path.suffix in CODE_SUFFIXES or path.name == "CMakeLists.txt"):
                path.resolve().relative_to(root.resolve())
                result[path.relative_to(root).as_posix()] = digest(path)
    return result


def checked_artifact(reference, inputs):
    path = Path(reference["path"])
    if not path.is_absolute() or digest(path) != reference["sha256"]:
        raise ValueError("Registered artifact path/hash changed: " + str(path))
    inputs.sha256[str(path.resolve())] = reference["sha256"]
    return path


def require_runtime(expected, actual):
    if expected["device"] != "cuda:0" or actual.get("cuda_available") is not True:
        raise ValueError("Registered recovery requires CUDA; no CPU fallback")
    if any(expected.get(k) != actual.get(k) for k in RUNTIME_FIELDS):
        raise ValueError("Registered Python/Torch/CUDA/host runtime changed")


def check_source_archive(registration, inputs):
    root = Path(registration["source_archive"])
    archive = inputs.json(root / "source.json")
    if archive["base_commit"] != registration["source"]["commit"]:
        raise ValueError("Source archive base differs from the registration")
    for name, key in (("working-tree.patch", "patch_sha256"), ("development-files.tar.gz", "archive_sha256")):
        checked_artifact({"path": str(root / name), "sha256": archive[key]}, inputs)
    # Execution registrations are created only from committed clean source.
    if (root / "working-tree.patch").stat().st_size or archive["untracked_files"]:
        raise ValueError("Study source archive must describe committed clean source")
    with tarfile.open(root / "development-files.tar.gz", "r:gz") as tar:
        if tar.getmembers():
            raise ValueError("Unexpected untracked files in a clean study archive")


def check_qualification(reference, registration, inputs):
    report = inputs.json(checked_artifact(reference, inputs))
    if (report.get("format") != "openttd-rl-v2-minimum-correctness-1" or report.get("status") != "passed" or
            report.get("protocol_sha256") != PROTOCOL_SHA256 or
            any(report.get(k) != registration[k] for k in ("source", "code_sha256", "binaries", "runtime")) or
            set(report.get("checks", {})) != set(CORRECTNESS_CHECKS)):
        raise ValueError("Correctness bundle does not cover this exact executable study")
    for item in report["checks"].values():
        check = inputs.json(checked_artifact(item, inputs))
        if check.get("status") != "passed":
            raise ValueError("Required correctness check did not pass")
    tree = ET.fromstring(inputs.read(checked_artifact(report["native_junit"], inputs)))
    cases = list(tree.iter("testcase"))
    names = {case.get("name") for case in cases}
    required = {"rl_choice_weighted_cpu", "rl_choice_weighted_cuda", "rl_dev_v2_policy_cpu", "rl_dev_v2_policy_cuda",
                "rl_checkpoint_roundtrip_cpu", "rl_checkpoint_roundtrip_cuda", "rl_behavior_replay_cpu", "rl_behavior_replay_cuda"}
    if (not required <= names or any(c.get("status") != "run" for c in cases if c.get("name") in required) or
            any(any(x.tag in ("failure", "error", "skipped") for x in c) for c in cases)):
        raise ValueError("Mandatory native CPU/CUDA gates were missing, skipped or failed")


def preflight(path, *, inputs=None, root=ROOT, runtime=None, identity=None):
    """No game or model process is started by preflight; it also checks content."""
    inputs = Inputs() if inputs is None else inputs
    path = Path(path).resolve()
    data = inputs.read(path)
    sha = hashlib.sha256(data).hexdigest()
    if inputs.read(path.with_suffix(".sha256")).decode().strip() != sha:
        raise ValueError("Immutable execution registration digest changed")
    registration = json.loads(data)
    protocol = load_protocol()
    validate_registration(registration, protocol)
    current = source_identity() if identity is None else identity
    if registration["source"]["status"] or current != registration["source"]:
        raise ValueError("Execution requires the registered clean source checkout")
    if registration["driver"] != DRIVER or code_identity(root) != registration["code_sha256"]:
        raise ValueError("Registered driver or complete source closure changed")
    require_runtime(registration["runtime"], host() if runtime is None else runtime)
    check_source_archive(registration, inputs)
    for ref in registration["binaries"].values():
        checked_artifact(ref, inputs)
    content = checked_artifact(registration["content"], inputs)
    if content.resolve() != (Path(registration["binaries"]["engine"]["path"]).parent / "baseset/opengfx-8.0.tar").resolve():
        raise ValueError("Registered content is not the content used by the native launcher")
    for ref in registration["qualification_reports"]:
        check_qualification(ref, registration, inputs)
    cost = inputs.json(checked_artifact(registration["cost_estimate"], inputs))
    if cost.get("status") != "passed" or cost.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("Cost estimate does not cover this frozen study protocol")
    inputs.unchanged()
    return registration, protocol, inputs


def register(args):
    """Create a prospective, exclusive registration; never edit an old one."""
    protocol = load_protocol()
    identity = source_identity()
    if identity["status"]:
        raise ValueError("Commit the study driver and source before registration")
    runtime = {**host(), "device": "cuda:0"}
    require_runtime(runtime, runtime)
    arm = next(a for a in protocol["arms"] if a["id"] == args.arm)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    capture_source(output / "source")
    registration = {"format": "openttd-rl-dev-study-registration-1", "study_id": args.study_id,
        "registered_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol_sha256": PROTOCOL_SHA256, "arm": args.arm, "training_seeds": protocol["training_seeds"],
        "training": {**protocol["fixed_training"], **{k: v for k, v in arm.items() if k != "id"}},
        "runtime": runtime, "source": identity, "source_archive": str(output / "source"), "driver": DRIVER,
        "code_sha256": code_identity(), "binaries": {k: artifact(getattr(args, k)) for k in ("engine", "trainer", "policy")},
        "content": artifact(args.engine.resolve().parent / "baseset/opengfx-8.0.tar"),
        "qualification_reports": [artifact(p) for p in args.qualification], "cost_estimate": artifact(args.cost),
        "maximum_native_jobs": 2, "maximum_cuda_training_jobs": 1}
    validate_registration(registration, protocol)
    path = output / "registration.json"
    with path.open("x") as stream:
        stream.write(json.dumps(registration, indent=2, allow_nan=False) + "\n")
    with path.with_suffix(".sha256").open("x") as stream:
        stream.write(digest(path) + "\n")
    preflight(path)
    return path
