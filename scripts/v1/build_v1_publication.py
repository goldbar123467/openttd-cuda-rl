#!/usr/bin/env python3
"""Build and verify the deterministic OpenTTD RL V1 public release artifact."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
from typing import Any

import m10_deployment_client
import validate_m13_publication_contract


class PublicationError(RuntimeError):
    """The repository or publication artifact failed closed."""


EXPECTED_SOURCE_FILES = {
    "INSTALL.md",
    "evaluation.json",
    "golden.jsonl",
    "manifest.json",
    "model.onnx",
}
SCREENSHOT_SHA256 = "aab1f33d7be1ef2fe080d177995f1ed82a90a9918879305391b9d729ab7d5fea"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def write_canonical(path: pathlib.Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value) + b"\n")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def absolute_directory(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise argparse.ArgumentTypeError("must be an existing absolute directory")
    return path.resolve()


def absolute_file(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_file():
        raise argparse.ArgumentTypeError("must be an existing absolute file")
    return path.resolve()


def absolute_executable(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_file() or not path.stat().st_mode & 0o111:
        raise argparse.ArgumentTypeError("must be an existing absolute executable")
    return path


def new_absolute_path(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or path.exists():
        raise argparse.ArgumentTypeError("must be a new absolute path")
    return path


def command_output(command: list[str], *, cwd: pathlib.Path) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def validate_repository(root: pathlib.Path, contract: dict[str, Any]) -> str:
    require(command_output(["git", "status", "--porcelain"], cwd=root) == "", "publication requires a clean repository")
    require(command_output(["git", "branch", "--show-current"], cwd=root) == "main", "publication requires branch main")
    subprocess.run(["git", "fetch", "--quiet", "origin", "main"], cwd=root, check=True)
    commit = command_output(["git", "rev-parse", "HEAD"], cwd=root)
    origin = command_output(["git", "rev-parse", "origin/main"], cwd=root)
    require(commit == origin, "publication requires local main equal to origin/main")
    remote = command_output(["git", "remote", "get-url", "origin"], cwd=root)
    expected = contract["release"]["repository"]
    require(remote.removesuffix(".git") == expected, "origin URL differs from the publication contract")
    for relative in contract["repository_surface"]["required_paths"]:
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"repository surface is missing a regular file: {relative}")
    require(sha256_file(root / "LICENSE") == sha256_file(root / "LICENSES/GPL-2.0-only.txt"), "root GPL license text drifted")
    require(sha256_file(root / "docs/assets/openttd-rl-v1-playback.png") == SCREENSHOT_SHA256, "accepted playback screenshot drifted")
    notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for marker in ("OpenTTD", "OpenGFX", "ONNX Runtime", "PyTorch/LibTorch", "NVIDIA CUDA", "not bundled"):
        require(marker in notices, f"third-party notice is missing: {marker}")
    gitleaks = shutil.which("gitleaks")
    require(gitleaks is not None, "publication requires the gitleaks executable")
    subprocess.run(
        [gitleaks, "detect", "--redact", "--no-banner", "--source", str(root)],
        cwd=root,
        check=True,
    )
    return commit


def validate_m12(path: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    accepted = contract["accepted_m12"]
    require(sha256_file(path) == accepted["manifest_file_sha256"], "accepted M12 manifest file identity drifted")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    require(manifest["manifest_sha256"] == accepted["manifest_sha256"], "accepted M12 semantic identity drifted")
    require(manifest["contract_sha256"] == accepted["contract_sha256"], "accepted M12 contract link drifted")
    require(manifest["source"]["commit"] == accepted["source_commit"], "accepted M12 source commit drifted")
    require(manifest["source"]["openttd_upstream_commit"] == accepted["openttd_upstream_commit"], "accepted OpenTTD source drifted")
    require(manifest["traceability"]["requirements_passed"] == accepted["requirements_passed"], "accepted requirement count drifted")
    require(len(manifest["campaigns"]) == accepted["campaigns_passed"] and all(item["status"] == "PASS" for item in manifest["campaigns"]), "accepted campaign closure drifted")
    require(manifest["defects"]["total_nonclosed"] == accepted["nonclosed_defects"], "accepted defect closure drifted")
    return manifest


def validate_source_package(path: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    model = contract["model_package"]
    require(path.name == model["source_package_id"] and not path.is_symlink(), "accepted M10 source package identity drifted")
    entries = list(path.iterdir())
    require(len(entries) == 5 and {item.name for item in entries} == EXPECTED_SOURCE_FILES, "accepted M10 source inventory drifted")
    require(all(item.is_file() and not item.is_symlink() for item in entries), "accepted M10 source contains a symlink or nonfile")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    semantic = copy.deepcopy(manifest)
    observed = semantic.pop("package_id")
    require(observed == path.name == sha256_bytes(canonical_bytes(semantic)), "accepted M10 package content address drifted")
    require(sha256_file(path / "model.onnx") == model["source_model_sha256"], "accepted M10 model identity drifted")
    for name in ("INSTALL.md", "evaluation.json", "golden.jsonl"):
        require(sha256_file(path / name) == model["files"][name], f"accepted M10 payload drifted: {name}")
    return manifest


def sanitize_package(
    *,
    root: pathlib.Path,
    exporter_python: pathlib.Path,
    source: pathlib.Path,
    output: pathlib.Path,
    contract: dict[str, Any],
) -> pathlib.Path:
    subprocess.run(
        [
            str(exporter_python),
            str(root / "scripts/v1/sanitize_m10_package.py"),
            "--source-package",
            str(source),
            "--output-root",
            str(output),
        ],
        cwd=root,
        check=True,
    )
    package = output / contract["model_package"]["package_id"]
    require(package.is_dir() and not package.is_symlink(), "sanitizer returned the wrong package identity")
    entries = list(package.iterdir())
    require(len(entries) == 5 and {item.name for item in entries} == EXPECTED_SOURCE_FILES, "sanitized package inventory drifted")
    require(all(item.is_file() and not item.is_symlink() for item in entries), "sanitized package contains a symlink or nonfile")
    for name, digest in contract["model_package"]["files"].items():
        require(sha256_file(package / name) == digest, f"sanitized package payload drifted: {name}")
    return package


def evaluate_package(
    evaluator: pathlib.Path,
    package: pathlib.Path,
    cases: list[dict[str, Any]],
    mode: str,
) -> list[Any]:
    client = m10_deployment_client.DeploymentClient.start(
        evaluator,
        package=package,
        sampling_seed=2026101011,
        mode=mode,
    )
    try:
        values = client.inspect(
            [item["structured"] for item in cases],
            [item["spatial"] for item in cases],
            [item["legal_mask"] for item in cases],
            deterministic=True,
        )
        package_id, model_sha256 = client.close(30.0)
        require(package_id == package.name and model_sha256 == sha256_file(package / "model.onnx"), f"{mode} evaluator identity drifted")
        return values
    except Exception:
        client.abort()
        raise


def prove_runtime_equivalence(
    evaluator: pathlib.Path,
    source: pathlib.Path,
    sanitized: pathlib.Path,
) -> None:
    cases = [json.loads(line) for line in (source / "golden.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(cases) == 12, "golden publication corpus must contain 12 cases")
    for mode in ("standalone", "ingame"):
        accepted = evaluate_package(evaluator, source, cases, mode)
        published = evaluate_package(evaluator, sanitized, cases, mode)
        require(len(accepted) == len(published) == 12, f"{mode} publication case count drifted")
        for before, after in zip(accepted, published, strict=True):
            require(
                before.action == after.action
                and before.logits == after.logits
                and before.probabilities == after.probabilities
                and before.value == after.value,
                f"{mode} sanitized ONNX output differs from accepted M10",
            )


def payload_manifest(
    *,
    contract: dict[str, Any],
    source_commit: str,
    package: pathlib.Path,
    release_root: pathlib.Path,
) -> dict[str, Any]:
    files = {}
    for relative in contract["archive"]["required_payload_files"]:
        path = release_root / relative
        files[relative] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    model = contract["model_package"]
    manifest = {
        "schema_version": "openttd-rl-v1-publication-manifest-1",
        "release": {
            "tag": contract["release"]["tag"],
            "name": contract["release"]["name"],
            "archive": contract["release"]["artifact_name"],
            "archive_root": contract["release"]["artifact_root"],
        },
        "source": {
            "repository": contract["release"]["repository"],
            "branch": contract["release"]["branch"],
            "commit": source_commit,
            "openttd_upstream_commit": contract["accepted_m12"]["openttd_upstream_commit"],
        },
        "license": {
            "project": contract["release"]["license"],
            "model_package": model["license"],
            "third_party_notices": "THIRD_PARTY_NOTICES.md",
        },
        "accepted_evidence": {
            "m12_contract_sha256": contract["accepted_m12"]["contract_sha256"],
            "m12_manifest_sha256": contract["accepted_m12"]["manifest_sha256"],
            "m12_manifest_file_sha256": contract["accepted_m12"]["manifest_file_sha256"],
            "m12_source_commit": contract["accepted_m12"]["source_commit"],
            "requirements_passed": contract["accepted_m12"]["requirements_passed"],
            "campaigns_passed": contract["accepted_m12"]["campaigns_passed"],
            "nonclosed_defects": contract["accepted_m12"]["nonclosed_defects"],
        },
        "model_package": {
            "package_id": model["package_id"],
            "source_package_id": model["source_package_id"],
            "source_model_sha256": model["source_model_sha256"],
            "architecture": model["architecture"],
            "onnx_opset": 18,
            "onnxruntime_version": "1.28.0",
            "sanitization": model["sanitization"]["kind"],
            "runtime_equivalence": model["runtime_equivalence"],
            "files": {name: sha256_file(package / name) for name in sorted(EXPECTED_SOURCE_FILES)},
        },
        "files": files,
        "exclusions": contract["archive"]["excluded_components"],
        "verification": {
            "byte_identical_rebuilds": contract["publication_review"]["rebuild_count"],
            "safe_archive_paths": "PASS",
            "no_symlinks": "PASS",
            "credential_scan": "PASS",
            "host_path_scan": "PASS",
            "canonical_json": "PASS",
        },
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_bytes(manifest))
    return manifest


def scan_release_tree(root: pathlib.Path, contract: dict[str, Any]) -> None:
    forbidden_text = [value.encode() for value in contract["publication_review"]["forbidden_text"]]
    for path in root.rglob("*"):
        require(not path.is_symlink(), f"release tree contains a symlink: {path.relative_to(root)}")
        if path.is_file():
            value = path.read_bytes()
            require(value, f"release tree contains an empty file: {path.relative_to(root)}")
            require(not any(marker in value for marker in forbidden_text), f"forbidden_text found in release file: {path.relative_to(root)}")


def write_checksum_file(root: pathlib.Path, paths: list[str]) -> None:
    lines = [f"{sha256_file(root / relative)}  {relative}" for relative in sorted(paths)]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_archive(source: pathlib.Path, destination: pathlib.Path) -> None:
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for path in sorted([source, *source.rglob("*")], key=lambda item: item.relative_to(source.parent).as_posix()):
                    relative = path.relative_to(source.parent).as_posix()
                    info = tarfile.TarInfo(relative)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    if path.is_dir():
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o755
                        archive.addfile(info)
                    else:
                        require(path.is_file() and not path.is_symlink(), "canonical tar input contains a symlink or nonfile")
                        info.size = path.stat().st_size
                        info.mode = 0o644
                        with path.open("rb") as stream:
                            archive.addfile(info, stream)


def validate_archive(path: pathlib.Path, contract: dict[str, Any]) -> None:
    prefix = pathlib.PurePosixPath(contract["release"]["artifact_root"])
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [item.name for item in members]
        require(names == sorted(names) and len(names) == len(set(names)), "safe archive member order/inventory drifted")
        for member in members:
            value = pathlib.PurePosixPath(member.name)
            require(not value.is_absolute() and ".." not in value.parts and value.parts[0] == prefix.parts[0], "safe archive path validation failed")
            require(member.isdir() or member.isfile(), "safe archive contains a symlink, hardlink, or special member")
            require(member.uid == member.gid == member.mtime == 0 and member.uname == member.gname == "", "canonical tar metadata drifted")
        sums_member = archive.getmember(f"{prefix}/SHA256SUMS")
        sums = archive.extractfile(sums_member)
        require(sums is not None, "archive checksum file is unreadable")
        for line in sums.read().decode().splitlines():
            digest, relative = line.split("  ", 1)
            member = archive.getmember(f"{prefix}/{relative}")
            stream = archive.extractfile(member)
            require(stream is not None and sha256_bytes(stream.read()) == digest, f"archive checksum mismatch: {relative}")


def build_tree(
    *,
    root: pathlib.Path,
    destination: pathlib.Path,
    package: pathlib.Path,
    contract: dict[str, Any],
    source_commit: str,
) -> tuple[pathlib.Path, pathlib.Path]:
    release_root = destination / contract["release"]["artifact_root"]
    release_root.mkdir(parents=True)
    shutil.copyfile(root / "LICENSE", release_root / "LICENSE")
    shutil.copyfile(root / "docs/project/V1_MODEL_RELEASE_README.md", release_root / "README.md")
    shutil.copyfile(root / "THIRD_PARTY_NOTICES.md", release_root / "THIRD_PARTY_NOTICES.md")
    model_root = release_root / "models" / package.name
    model_root.parent.mkdir()
    shutil.copytree(package, model_root)
    expected_payload = set(contract["archive"]["required_payload_files"])
    observed_payload = {
        item.relative_to(release_root).as_posix()
        for item in release_root.rglob("*")
        if item.is_file()
    }
    require(observed_payload == expected_payload, "publication payload inventory differs from the frozen contract")
    manifest = payload_manifest(
        contract=contract,
        source_commit=source_commit,
        package=model_root,
        release_root=release_root,
    )
    manifest_path = release_root / "publication-manifest.json"
    write_canonical(manifest_path, manifest)
    validate_m13_publication_contract.validate_manifest(
        manifest_path,
        root / contract["identity"]["manifest_schema_path"],
        contract,
    )
    write_checksum_file(release_root, [*sorted(expected_payload), "publication-manifest.json"])
    all_files = {
        item.relative_to(release_root).as_posix()
        for item in release_root.rglob("*")
        if item.is_file()
    }
    require(all_files == expected_payload | {"publication-manifest.json", "SHA256SUMS"}, "final release inventory drifted")
    scan_release_tree(release_root, contract)
    archive_path = destination / contract["release"]["artifact_name"]
    create_archive(release_root, archive_path)
    validate_archive(archive_path, contract)
    return archive_path, manifest_path


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.repo_root
    contract_path = root / "config/v1/m13-publication-contract.json"
    contract = validate_m13_publication_contract.validate(
        contract_path,
        root / "docs/project/schema/v1-m13-publication-contract.schema.json",
    )
    source_commit = validate_repository(root, contract)
    validate_m12(args.m12_manifest, contract)
    validate_source_package(args.source_package, contract)
    args.artifact_root.mkdir(parents=True)
    try:
        package_a = sanitize_package(
            root=root,
            exporter_python=args.exporter_python,
            source=args.source_package,
            output=args.artifact_root / "sanitized-a",
            contract=contract,
        )
        package_b = sanitize_package(
            root=root,
            exporter_python=args.exporter_python,
            source=args.source_package,
            output=args.artifact_root / "sanitized-b",
            contract=contract,
        )
        require(
            all((package_a / name).read_bytes() == (package_b / name).read_bytes() for name in EXPECTED_SOURCE_FILES),
            "independent sanitized package builds are not byte-identical",
        )
        prove_runtime_equivalence(args.deployment_evaluator, args.source_package, package_a)
        archive_a, manifest_a = build_tree(
            root=root,
            destination=args.artifact_root / "build-a",
            package=package_a,
            contract=contract,
            source_commit=source_commit,
        )
        archive_b, manifest_b = build_tree(
            root=root,
            destination=args.artifact_root / "build-b",
            package=package_b,
            contract=contract,
            source_commit=source_commit,
        )
        require(archive_a.read_bytes() == archive_b.read_bytes(), "independent publication archives are not byte-identical")
        require(manifest_a.read_bytes() == manifest_b.read_bytes(), "independent publication manifests are not byte-identical")
        final_archive = args.artifact_root / contract["release"]["artifact_name"]
        final_manifest = args.artifact_root / "publication-manifest.json"
        shutil.copyfile(archive_a, final_archive)
        shutil.copyfile(manifest_a, final_manifest)
        archive_digest = sha256_file(final_archive)
        (args.artifact_root / "SHA256SUMS").write_text(
            f"{archive_digest}  {final_archive.name}\n",
            encoding="utf-8",
        )
        report = {
            "schema_version": "openttd-rl-v1-m13-publication-gate-report-1",
            "status": "PASS",
            "release": {"tag": contract["release"]["tag"], "name": contract["release"]["name"]},
            "source_commit": source_commit,
            "contract_sha256": contract["identity"]["compatibility_sha256"],
            "m12_manifest_sha256": contract["accepted_m12"]["manifest_sha256"],
            "package_id": contract["model_package"]["package_id"],
            "model_sha256": contract["model_package"]["files"]["model.onnx"],
            "archive": {"name": final_archive.name, "sha256": archive_digest, "size": final_archive.stat().st_size},
            "publication_manifest_sha256": sha256_file(final_manifest),
            "publication_manifest_semantic_sha256": json.loads(final_manifest.read_text(encoding="utf-8"))["manifest_sha256"],
            "gates": [{"id": gate, "status": "PASS"} for gate in contract["gates"]],
        }
        write_canonical(args.artifact_root / "publication-gate-report.json", report)
        scan_release_tree(args.artifact_root / "build-a" / contract["release"]["artifact_root"], contract)
        print(
            "M13_PUBLICATION_GATE=PASS "
            f"commit={source_commit} package_id={report['package_id']} "
            f"archive_sha256={archive_digest} gates={len(contract['gates'])}",
            flush=True,
        )
        return report
    except Exception:
        print(f"M13_PUBLICATION_ARTIFACT_ROOT_RETAINED={args.artifact_root}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=absolute_directory, required=True)
    parser.add_argument("--source-package", type=absolute_directory, required=True)
    parser.add_argument("--m12-manifest", type=absolute_file, required=True)
    parser.add_argument("--exporter-python", type=absolute_executable, required=True)
    parser.add_argument("--deployment-evaluator", type=absolute_executable, required=True)
    parser.add_argument("--artifact-root", type=new_absolute_path, required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, PublicationError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"M13_PUBLICATION_GATE=FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
