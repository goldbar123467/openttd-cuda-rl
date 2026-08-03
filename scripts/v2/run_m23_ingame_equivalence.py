#!/usr/bin/env python3
"""Run the frozen M23 corpus through the source-integrated OpenTTD binary."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys

import m23_ingame
import m23_package
import validate_m23_release_contract as contract_validator


def require(condition: bool, message: str) -> None:
    if not condition:
        raise m23_ingame.M23InGameError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--package-root", type=pathlib.Path, required=True)
    parser.add_argument("--golden", type=pathlib.Path, required=True)
    parser.add_argument("--native-report", type=pathlib.Path, required=True)
    parser.add_argument("--standalone-report", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--source-tree", required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        executable = args.openttd.resolve()
        package_root = args.package_root.resolve()
        golden = args.golden.resolve()
        native_report = args.native_report.resolve()
        standalone_report = args.standalone_report.resolve()
        artifact_root = args.artifact_root.resolve()
        require(not artifact_root.exists() and not artifact_root.is_symlink(),
                "M23 in-game artifact root must be new")
        require(executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK),
                "M23 OpenTTD executable is unavailable")
        require(re.fullmatch(r"[0-9a-f]{40}", args.source_tree) is not None,
                "M23 OpenTTD source tree is invalid")
        contract_validator.validate(root)
        contract = contract_validator.load(root / contract_validator.CONTRACT)
        package_report = m23_package.validate_output_root(root, package_root, inspect_graph=False)
        m23_ingame.validate_native_report(native_report, golden)
        standalone = m23_ingame.validate_equivalence_report(
            standalone_report, m23_ingame.STANDALONE_RUNTIME, golden, package_report,
        )
        patch_record = m23_ingame.validate_source_patch(root)
        dependencies = m23_ingame.dependency_closure(executable)
        help_result = subprocess.run(
            [str(executable), "-h"], cwd=executable.parent, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        require(help_result.returncode == 0 and "-A playback_config" in help_result.stdout and
                "-B bridge_or_config" in help_result.stdout,
                "M23 OpenTTD help lost the V1/V2 entrypoints")
        artifact_root.mkdir(parents=True, mode=0o700)
        monolithic, specialist = package_report["deployment_packages"]
        config = {
            "contract_sha256": m23_package.sha256_file(root / contract_validator.CONTRACT),
            "equivalence": {
                "golden_path": str(golden),
                "report_path": str(artifact_root / "ingame-equivalence-report.json"),
            },
            "inference": {"interval_ticks": 128, "mode": "greedy"},
            "monolithic_package_path": str(package_root / "models" / monolithic["package_id"]),
            "operation": "equivalence",
            "schema_version": m23_ingame.CONFIG_SCHEMA,
            "specialist_package_path": str(package_root / "models" / specialist["package_id"]),
        }
        config_path = artifact_root / "config.json"
        m23_package.write_new(config_path, m23_package.canonical_json(config, newline=True))
        bwrap_raw = shutil.which("bwrap")
        require(bwrap_raw is not None, "bubblewrap is required for network-isolated M23 in-game equivalence")
        command = [
            str(pathlib.Path(bwrap_raw).resolve()), "--die-with-parent", "--unshare-net",
            "--ro-bind", "/", "/", "--bind", str(artifact_root), str(artifact_root),
            "--dev", "/dev", "--proc", "/proc", "--chdir", str(executable.parent),
            str(executable), "-B", str(config_path), "-v", "null", "-s", "null", "-m", "null",
            "-x", "-X", "-Q",
        ]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        m23_package.write_new(artifact_root / "stdout.log", completed.stdout.encode("utf-8"))
        m23_package.write_new(artifact_root / "stderr.log", completed.stderr.encode("utf-8") or b"\n")
        require(completed.returncode == 0 and
                re.fullmatch(r"M23_INGAME_EQUIVALENCE=PASS cases=48 failures=0 max_abs=[0-9.e+-]+\n",
                             completed.stdout) is not None and completed.stderr == "",
                f"M23 source-integrated OpenTTD execution failed ({completed.returncode}): "
                f"{completed.stderr or completed.stdout}")
        ingame = m23_ingame.validate_equivalence_report(
            artifact_root / "ingame-equivalence-report.json", m23_ingame.INGAME_RUNTIME, golden, package_report,
        )
        require(m23_ingame.reports_match_except_runtime(standalone, ingame),
                "M23 source-integrated outputs differ from standalone outputs")
        files = {
            name: m23_ingame.file_record(artifact_root / name)
            for name in ("config.json", "ingame-equivalence-report.json", "stderr.log", "stdout.log")
        }
        foundation = {
            "dependencies": dependencies,
            "executable": m23_ingame.file_record(executable),
            "files": files,
            "golden": m23_ingame.file_record(golden),
            "maximum_absolute": max(
                ingame["maximum_error"][key]
                for key in ("hidden_absolute", "logits_absolute", "value_absolute")
            ),
            "native_report": m23_ingame.file_record(native_report),
            "network_unshared": True,
            "package_build_report": m23_ingame.file_record(package_root / "package-build-report.json"),
            "package_ids": [monolithic["package_id"], specialist["package_id"]],
            "reports_match_except_runtime": True,
            "rows_per_runtime": 580,
            "runtime_results": {"ingame": 48, "native": 48, "standalone": 48, "total": 144},
            "schema_version": m23_ingame.SCHEMA_VERSION,
            "source_base_tree": contract["normal_game"]["source_base"]["tree"],
            "source_patch": patch_record,
            "source_result_tree": args.source_tree,
            "standalone_report": m23_ingame.file_record(standalone_report),
            "status": "PASS",
        }
        m23_package.write_new(
            artifact_root / "foundation-report.json", m23_package.canonical_json(foundation, newline=True),
        )
        m23_ingame.validate_artifact(
            root, artifact_root, package_root, golden, native_report, standalone_report,
            executable, args.source_tree,
        )
        print(
            f"V2_M23_INGAME_EQUIVALENCE=PASS runtime_results=144 cases=48 rows=580 "
            f"max_abs={foundation['maximum_absolute']}",
        )
        return 0
    except (m23_ingame.M23InGameError, m23_package.M23PackageError, OSError, ValueError,
            KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"V2_M23_INGAME_EQUIVALENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
