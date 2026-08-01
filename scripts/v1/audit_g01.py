#!/usr/bin/env python3
"""Audit all immutable evidence required to close the V1 G01 gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import stat
import subprocess
import sys
from typing import Any

import jsonschema

import generate_dependency_provenance
import measure_runtime_resources
import validate_build_profiles


class G01AuditError(ValueError):
    """A G01 declaration or retained evidence artifact failed validation."""


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise G01AuditError(f"cannot load {path}: {exc}") from exc


def run(command: list[str], label: str, cwd: pathlib.Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-20:])
        raise G01AuditError(f"{label} failed with exit code {result.returncode}: {detail}")
    return result.stdout


def validate_install(root: pathlib.Path, manifest: dict[str, Any]) -> None:
    prefix = root / "stage" / f"opt/openttd-rl-v1-{manifest['variant']}"
    for item in manifest["install_artifacts"]:
        path = prefix / item["path"]
        if item["type"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != item["target"]:
                raise G01AuditError(f"installed symlink drift: {path}")
        elif item["type"] == "file":
            if path.is_symlink() or not path.is_file():
                raise G01AuditError(f"installed file is missing: {path}")
            if path.stat().st_size != item["size_bytes"] or sha256_file(path) != item["sha256"]:
                raise G01AuditError(f"installed file content drift: {path}")
            if stat.S_IMODE(path.stat().st_mode) != item["mode"]:
                raise G01AuditError(f"installed file mode drift: {path}")
        else:
            raise G01AuditError(f"unknown installed artifact type: {item['type']}")
    if (root / "build").exists():
        raise G01AuditError(f"accepted build directory was not cleaned: {root / 'build'}")


def audit_baseline(store: pathlib.Path, baseline: dict[str, Any]) -> dict[str, Any]:
    roots = [store / run_id for run_id in baseline["accepted_runs"]]
    filename = "build-manifest.json" if baseline["kind"] == "openttd-build" else "toolchain-probe.json"
    paths = [root / filename for root in roots]
    if any(not path.is_file() for path in paths):
        raise G01AuditError(f"accepted baseline manifest is missing: {baseline['id']}")
    if paths[0].read_bytes() != paths[1].read_bytes():
        raise G01AuditError(f"accepted paired manifests differ: {baseline['id']}")
    manifest_sha256 = sha256_file(paths[0])
    if manifest_sha256 != baseline["manifest_sha256"]:
        raise G01AuditError(
            f"accepted manifest SHA-256 drift for {baseline['id']}: "
            f"expected={baseline['manifest_sha256']} actual={manifest_sha256}"
        )
    manifests = [load_json(path) for path in paths]
    identity_key = "build_identity_sha256" if baseline["kind"] == "openttd-build" else "probe_identity_sha256"
    if any(
        manifest.get("result") != "PASS"
        or manifest.get(identity_key) != baseline["identity_sha256"]
        for manifest in manifests
    ):
        raise G01AuditError(f"accepted result/identity drift: {baseline['id']}")
    if baseline["kind"] == "openttd-build":
        for root, manifest in zip(roots, manifests, strict=True):
            validate_install(root, manifest)
    else:
        for product in manifests[0]["products"]["native_binaries"]:
            relative = pathlib.Path("native-build") / product["name"]
            first = roots[0] / relative
            second = roots[1] / relative
            if sha256_file(first) != product["sha256"] or first.read_bytes() != second.read_bytes():
                raise G01AuditError(f"toolchain native product drift: {product['name']}")
        model_paths = [root / "probe-model.onnx" for root in roots]
        expected_model = manifests[0]["products"]["onnx_model"]["sha256"]
        if sha256_file(model_paths[0]) != expected_model or model_paths[0].read_bytes() != model_paths[1].read_bytes():
            raise G01AuditError("toolchain ONNX model drift")
    return {
        "id": baseline["id"],
        "identity_sha256": baseline["identity_sha256"],
        "manifest_sha256": manifest_sha256,
        "paired_runs": 2,
        "result": "PASS",
    }


def resource_protocol(report: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(report))
    value.pop("report_identity_sha256")
    for workload in value["workloads"]:
        workload.pop("warmups")
        workload.pop("samples")
        workload.pop("aggregate")
    return value


def audit_resources(
    store: pathlib.Path,
    index: dict[str, Any],
    report_schema: pathlib.Path,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for run in index["resource_runs"]:
        path = store / run["id"] / "resource-report.json"
        if sha256_file(path) != run["report_sha256"]:
            raise G01AuditError(f"resource report SHA-256 drift: {run['id']}")
        report = load_json(path)
        measure_runtime_resources.validate_json(report, report_schema, "resource report")
        if report["report_identity_sha256"] != run["identity_sha256"]:
            raise G01AuditError(f"resource report identity drift: {run['id']}")
        if report["plan"]["sha256"] != index["resource_plan_sha256"]:
            raise G01AuditError(f"resource plan drift: {run['id']}")
        if any(len(workload["warmups"]) != 1 or len(workload["samples"]) != 5 for workload in report["workloads"]):
            raise G01AuditError(f"resource sample inventory drift: {run['id']}")
        reports.append(report)
    if resource_protocol(reports[0]) != resource_protocol(reports[1]):
        raise G01AuditError("resource runs used different protocols or binary identities")
    return {
        "runs": 2,
        "workloads": 4,
        "samples_per_workload": 5,
        "protocol_equal": True,
        "result": "PASS",
    }


def audit_provenance(
    store: pathlib.Path,
    index: dict[str, Any],
    schema: pathlib.Path,
) -> dict[str, Any]:
    paths: list[pathlib.Path] = []
    manifests: list[dict[str, Any]] = []
    for run in index["provenance_runs"]:
        path = store / run["id"] / "dependency-provenance.json"
        if sha256_file(path) != run["manifest_sha256"]:
            raise G01AuditError(f"provenance manifest SHA-256 drift: {run['id']}")
        manifest = load_json(path)
        generate_dependency_provenance.validate_manifest(manifest, schema)
        if manifest["provenance_identity_sha256"] != run["identity_sha256"]:
            raise G01AuditError(f"provenance identity drift: {run['id']}")
        paths.append(path)
        manifests.append(manifest)
    if paths[0].read_bytes() != paths[1].read_bytes():
        raise G01AuditError("repeated provenance manifests are not byte-identical")
    manifest = manifests[0]
    return {
        "runs": 2,
        "byte_identical": True,
        "toolchain": len(manifest["toolchain_artifacts"]),
        "build_overlay": len(manifest["build_overlay_packages"]),
        "runtime": len(manifest["runtime_dependencies"]),
        "result": "PASS",
    }


def audit_source(root: pathlib.Path, store: pathlib.Path, index: dict[str, Any]) -> dict[str, Any]:
    outer_commit = run(["git", "rev-parse", "HEAD"], "outer commit", root).strip()
    if outer_commit != index["outer_repository"]["baseline_commit"]:
        raise G01AuditError(f"outer baseline commit drift: {outer_commit}")
    submodule = root / "openttd-upstream"
    submodule_commit = run(["git", "rev-parse", "HEAD"], "submodule commit", submodule).strip()
    submodule_status = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], "submodule status", submodule)
    if submodule_commit != index["submodule"]["commit"] or submodule_status:
        raise G01AuditError("OpenTTD submodule is not clean at its preserved gitlink")
    snapshot = store / index["outer_repository"]["snapshot_id"]
    for filename, digest in index["outer_repository"]["snapshot_sha256"].items():
        if sha256_file(snapshot / filename) != digest:
            raise G01AuditError(f"worktree preservation snapshot drift: {filename}")
    run(["git", "diff", "--check"], "outer diff check", root)
    return {
        "outer_commit": outer_commit,
        "outer_worktree": "PRESERVED_DIRTY",
        "snapshot_verified": True,
        "submodule_commit": submodule_commit,
        "submodule_clean": True,
    }


def validate_report(report: dict[str, Any], schema_path: pathlib.Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise G01AuditError(f"G01 report schema failed at {location}: {exc.message}") from exc


def write_json(path: pathlib.Path, value: Any) -> None:
    if path.exists():
        raise G01AuditError(f"refusing to overwrite output: {path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_human(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "OpenTTD RL V1 G01 audit",
            f"result: {report['result']}",
            f"profiles: {report['profile_matrix']['profiles']}",
            f"accepted paired baselines: {len(report['accepted_baselines'])}",
            f"resource workloads: {report['resource_evidence']['workloads']}",
            f"provenance runtime dependencies: {report['provenance_evidence']['runtime']}",
            f"checks: {len(report['checks'])}",
            f"identity: {report['audit_identity_sha256']}",
            "",
        ]
    )


def audit(options: argparse.Namespace) -> dict[str, Any]:
    artifact_root = options.artifact_root.resolve()
    if not artifact_root.is_dir() or any(artifact_root.iterdir()):
        raise G01AuditError("artifact root must be an existing empty directory")
    root = options.root.resolve()
    store = options.artifact_store.resolve()
    index = load_json(options.evidence_index)
    profile_summary = validate_build_profiles.validate(options.profile_matrix, options.profile_schema)
    matrix = validate_build_profiles.load_json(options.profile_matrix)
    baselines = [audit_baseline(store, baseline) for baseline in matrix["accepted_baselines"]]
    resources = audit_resources(store, index, options.resource_schema)
    provenance = audit_provenance(store, index, options.provenance_schema)
    source = audit_source(root, store, index)
    checks = [
        {"id": "profile-matrix-schema-and-semantics", "result": "PASS"},
        {"id": "dedicated-headless-pair-byte-reproducibility", "result": "PASS"},
        {"id": "playable-pair-byte-reproducibility", "result": "PASS"},
        {"id": "cuda-libtorch-onnx-probe-pair-reproducibility", "result": "PASS"},
        {"id": "accepted-install-tree-content-validation", "result": "PASS"},
        {"id": "accepted-build-directory-cleanup", "result": "PASS"},
        {"id": "resource-plan-and-raw-sample-validation", "result": "PASS"},
        {"id": "resource-protocol-repeatability", "result": "PASS"},
        {"id": "license-provenance-completeness", "result": "PASS"},
        {"id": "provenance-byte-reproducibility", "result": "PASS"},
        {"id": "submodule-cleanliness-and-source-identity", "result": "PASS"},
        {"id": "preserved-dirty-worktree-recoverability", "result": "PASS"},
        {"id": "whitespace-validation", "result": "PASS"},
        {"id": "future-profile-resolution-tasks", "result": "PASS"},
        {"id": "dedicated-binary-worker-prohibition", "result": "PASS"},
    ]
    report_base = {
        "schema_version": "openttd-rl-v1-g01-audit-report-1",
        "gate": "G01",
        "profile_matrix": {
            "identity_sha256": profile_summary["matrix_identity_sha256"],
            "sha256": profile_summary["matrix_sha256"],
            "profiles": profile_summary["profiles"],
            "pending_profiles": profile_summary["pending_profiles"],
        },
        "accepted_baselines": baselines,
        "resource_evidence": resources,
        "provenance_evidence": provenance,
        "source_state": source,
        "checks": checks,
        "result": "PASS",
    }
    report = dict(report_base)
    report["audit_identity_sha256"] = hashlib.sha256(canonical_bytes(report_base)).hexdigest()
    validate_report(report, options.report_schema)
    write_json(artifact_root / "g01-audit.json", report)
    (artifact_root / "g01-audit.txt").write_text(render_human(report), encoding="utf-8")
    return report


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-store", required=True, type=pathlib.Path)
    parser.add_argument("--evidence-index", required=True, type=pathlib.Path)
    parser.add_argument("--profile-matrix", required=True, type=pathlib.Path)
    parser.add_argument("--profile-schema", required=True, type=pathlib.Path)
    parser.add_argument("--resource-schema", required=True, type=pathlib.Path)
    parser.add_argument("--provenance-schema", required=True, type=pathlib.Path)
    parser.add_argument("--report-schema", required=True, type=pathlib.Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        report = audit(options)
    except (
        G01AuditError,
        generate_dependency_provenance.ProvenanceError,
        measure_runtime_resources.ResourceMeasurementError,
        validate_build_profiles.BuildProfileError,
        OSError,
        UnicodeError,
    ) as exc:
        print(f"V1_G01_AUDIT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_G01_AUDIT=PASS "
        f"checks={len(report['checks'])} identity={report['audit_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
