#!/usr/bin/env python3
"""Shared validation for M23 source-integrated ONNX equivalence evidence."""

from __future__ import annotations

import copy
import math
import pathlib
import re
import subprocess
from collections.abc import Sequence
from typing import Any

import m23_golden
import m23_package
import validate_m23_release_contract as contract_validator


PATCH = pathlib.Path(
    "integration/openttd/patches/15.3/m23/0001-Add-M23-source-integrated-ONNX-runtime.patch"
)
SCHEMA_VERSION = "openttd-rl-v2-m23-ingame-equivalence-foundation-1"
CONFIG_SCHEMA = "openttd-rl-v2-m23-playback-config-1"
REPORT_SCHEMA = "openttd-rl-v2-m23-onnx-equivalence-report-1"
NATIVE_SCHEMA = "openttd-rl-v2-m23-native-golden-report-1"
STANDALONE_RUNTIME = "onnxruntime-1.28.0-cpu"
INGAME_RUNTIME = "source-integrated-ingame-onnxruntime-1.28.0-cpu"
ARCHITECTURES = tuple(contract_validator.ARCHITECTURES)
REPORT_KEYS = {
    "cases", "failure_counts", "golden", "maximum_error", "models", "runtime",
    "schema_version", "status", "tolerance",
}
CASE_KEYS = {
    "action_exact", "batch", "case_id", "hidden_absolute", "hidden_input_absolute",
    "hidden_relative", "logits_absolute", "logits_relative", "passed", "value_absolute",
    "value_relative",
}
ERROR_KEYS = {
    "hidden_absolute", "hidden_input_absolute", "hidden_input_relative", "hidden_relative",
    "logits_absolute", "logits_relative", "value_absolute", "value_relative",
}


class M23InGameError(RuntimeError):
    """The source-integrated runtime or its evidence failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M23InGameError(message)


def file_record(path: pathlib.Path) -> dict[str, Any]:
    require(path.is_absolute() and path.is_file() and not path.is_symlink(),
            f"M23 in-game evidence file is unavailable: {path}")
    return {"bytes": path.stat().st_size, "sha256": m23_package.sha256_file(path)}


def validate_native_report(path: pathlib.Path, golden_path: pathlib.Path) -> dict[str, Any]:
    value = m23_package.load_json(path)
    require(isinstance(value, dict) and set(value) == {
        "architectures", "cases", "file", "rows", "schema_version", "status",
    }, "M23 native golden report inventory drifted")
    require(value == {
        "architectures": list(ARCHITECTURES),
        "cases": 48,
        "file": {"bytes": golden_path.stat().st_size, "sha256": m23_package.sha256_file(golden_path)},
        "rows": 580,
        "schema_version": NATIVE_SCHEMA,
        "status": "PASS",
    }, "M23 native golden report semantics drifted")
    return value


def _finite_nonnegative(value: Any, label: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and
            math.isfinite(float(value)) and float(value) >= 0.0,
            f"M23 equivalence {label} is not finite and nonnegative")
    return float(value)


def validate_equivalence_value(
    value: Any,
    runtime: str,
    golden_sha256: str,
    records: Sequence[m23_golden.GoldenRecord],
    package_report: dict[str, Any],
) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == REPORT_KEYS,
            "M23 equivalence report field inventory drifted")
    require(value["schema_version"] == REPORT_SCHEMA and value["runtime"] == runtime and
            value["status"] == "PASS" and value["tolerance"] == {"absolute": 0.00005, "relative": 0.00005},
            "M23 equivalence report compatibility or status drifted")
    require(value["failure_counts"] == {"action": 0, "float": 0, "total": 0},
            "M23 equivalence report contains failures")
    require(value["golden"] == {"sha256": golden_sha256},
            "M23 equivalence golden identity drifted")
    expected_models = {
        "monolithic_sha256": package_report["deployment_packages"][0]["model_sha256"],
        "specialist_sha256": package_report["deployment_packages"][1]["model_sha256"],
    }
    require(value["models"] == expected_models, "M23 equivalence model identities drifted")
    cases = value["cases"]
    require(isinstance(cases, list) and len(cases) == len(records) == 48,
            "M23 equivalence case count drifted")
    for index, (item, expected) in enumerate(zip(cases, records, strict=True)):
        require(isinstance(item, dict) and set(item) == CASE_KEYS,
                f"M23 equivalence case inventory drifted at {index}")
        require(item["case_id"] == expected.definition.case_id and
                item["batch"] == expected.definition.batch and
                item["action_exact"] is True and item["passed"] is True,
                f"M23 equivalence case identity/result drifted at {index}")
        for key in CASE_KEYS - {"case_id", "batch", "action_exact", "passed"}:
            _finite_nonnegative(item[key], f"case {index}/{key}")
    require(sum(item["batch"] for item in cases) == 580,
            "M23 equivalence row count drifted")
    maximum = value["maximum_error"]
    require(isinstance(maximum, dict) and set(maximum) == ERROR_KEYS,
            "M23 equivalence maximum-error inventory drifted")
    for key, item in maximum.items():
        _finite_nonnegative(item, f"maximum_error/{key}")
    require(maximum["logits_absolute"] <= 0.00005 and
            maximum["value_absolute"] <= 0.00005 and
            maximum["hidden_absolute"] <= 0.00005 and
            maximum["hidden_input_absolute"] <= 0.00005,
            "M23 equivalence maximum absolute tolerance failed")
    return value


def validate_equivalence_report(
    path: pathlib.Path,
    runtime: str,
    golden_path: pathlib.Path,
    package_report: dict[str, Any],
) -> dict[str, Any]:
    raw = path.read_bytes()
    require(raw.endswith(b"\n") and not raw.endswith(b"\n\n") and b"\r" not in raw,
            "M23 equivalence report line ending drifted")
    value = m23_package.load_json_bytes(raw, path.name)
    try:
        canonical = m23_package.canonical_json(value, newline=True)
    except (TypeError, ValueError) as exc:
        raise M23InGameError("M23 equivalence report is not canonical") from exc
    require(raw == canonical, "M23 equivalence report is not canonical")
    golden_sha256 = m23_package.sha256_file(golden_path)
    records = m23_golden.decode(golden_path)
    return validate_equivalence_value(
        value, runtime, golden_sha256, records, package_report,
    )


def reports_match_except_runtime(standalone: dict[str, Any], ingame: dict[str, Any]) -> bool:
    left, right = copy.deepcopy(standalone), copy.deepcopy(ingame)
    left.pop("runtime", None)
    right.pop("runtime", None)
    return left == right


def dependency_closure(executable: pathlib.Path) -> list[str]:
    completed = subprocess.run(
        ["ldd", str(executable)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(completed.returncode == 0, f"cannot inspect M23 OpenTTD dependencies: {completed.stderr.strip()}")
    lines = [
        re.sub(r"\s+\(0x[0-9a-f]+\)$", "", line.strip())
        for line in completed.stdout.splitlines() if line.strip()
    ]
    lowered = "\n".join(lines).lower()
    require("libonnxruntime.so.1" in lowered and "libcrypto.so.3" in lowered,
            "M23 OpenTTD dependency closure lacks ONNX Runtime or OpenSSL Crypto")
    for forbidden in ("libtorch", "libc10", "libcudart", "libcuda.so", "libpython"):
        require(forbidden not in lowered, f"M23 OpenTTD deployment closure contains {forbidden}")
    return lines


def validate_source_patch(root: pathlib.Path) -> dict[str, Any]:
    path = root / PATCH
    require(path.is_file() and not path.is_symlink(), "M23 OpenTTD source patch is unavailable")
    text = path.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
    expected = [
        "CMakeLists.txt", "cmake/Options.cmake", "src/CMakeLists.txt", "src/openttd.cpp",
        "src/rl_v2_neural_agent.cpp", "src/rl_v2_neural_agent.h",
    ]
    require(touched == expected, f"M23 OpenTTD source patch scope drifted: {touched}")
    for token in (
        "OPTION_RL_V2_NEURAL_AGENT", "WITH_RL_V2_NEURAL_AGENT", "RunRlV2NeuralAgentConfig",
        "source-integrated-ingame-onnxruntime-1.28.0-cpu", "M23_INGAME_EQUIVALENCE=PASS",
        "M11 -A playback mode forbids", "std::string_view(mgo.opt).find(':')",
    ):
        require(token in text, f"M23 OpenTTD source patch lost required token: {token}")
    for forbidden in ("torch", "cuda", "std::system(", "popen(", "fork(", "execve("):
        require(forbidden not in text.lower(), f"M23 OpenTTD source patch contains forbidden token: {forbidden}")
    return {"bytes": path.stat().st_size, "path": PATCH.as_posix(), "sha256": m23_package.sha256_file(path)}


def validate_artifact(
    root: pathlib.Path,
    artifact_root: pathlib.Path,
    package_root: pathlib.Path,
    golden_path: pathlib.Path,
    native_report_path: pathlib.Path,
    standalone_report_path: pathlib.Path,
    executable: pathlib.Path,
    source_tree: str,
) -> dict[str, Any]:
    root, artifact_root, package_root = root.resolve(), artifact_root.resolve(), package_root.resolve()
    contract_validator.validate(root)
    package_report = m23_package.validate_output_root(root, package_root, inspect_graph=False)
    validate_native_report(native_report_path.resolve(), golden_path.resolve())
    standalone = validate_equivalence_report(
        standalone_report_path.resolve(), STANDALONE_RUNTIME, golden_path.resolve(), package_report,
    )
    ingame_path = artifact_root / "ingame-equivalence-report.json"
    ingame = validate_equivalence_report(ingame_path, INGAME_RUNTIME, golden_path.resolve(), package_report)
    require(reports_match_except_runtime(standalone, ingame),
            "standalone and source-integrated reports differ beyond runtime identity")
    foundation_path = artifact_root / "foundation-report.json"
    raw = foundation_path.read_bytes()
    foundation = m23_package.load_json_bytes(raw, foundation_path.name)
    require(raw == m23_package.canonical_json(foundation, newline=True),
            "M23 in-game foundation report is not canonical")
    expected_keys = {
        "dependencies", "executable", "files", "golden", "maximum_absolute", "native_report",
        "network_unshared", "package_build_report", "package_ids", "reports_match_except_runtime",
        "rows_per_runtime", "runtime_results", "schema_version", "source_base_tree", "source_patch",
        "source_result_tree", "standalone_report", "status",
    }
    require(isinstance(foundation, dict) and set(foundation) == expected_keys and
            foundation.get("schema_version") == SCHEMA_VERSION and
            foundation.get("status") == "PASS" and foundation.get("runtime_results") == {
                "ingame": 48, "native": 48, "standalone": 48, "total": 144,
            } and foundation.get("rows_per_runtime") == 580 and
            foundation.get("reports_match_except_runtime") is True and
            foundation.get("network_unshared") is True,
            "M23 in-game foundation summary drifted")
    expected_files = {
        name: file_record(artifact_root / name)
        for name in ("config.json", "ingame-equivalence-report.json", "stderr.log", "stdout.log")
    }
    require(foundation.get("files") == expected_files and
            foundation.get("executable") == file_record(executable.resolve()) and
            foundation.get("dependencies") == dependency_closure(executable.resolve()) and
            foundation.get("golden") == file_record(golden_path.resolve()) and
            foundation.get("native_report") == file_record(native_report_path.resolve()) and
            foundation.get("standalone_report") == file_record(standalone_report_path.resolve()) and
            foundation.get("package_build_report") == file_record(package_root / "package-build-report.json") and
            foundation.get("package_ids") == [
                item["package_id"] for item in package_report["deployment_packages"]
            ] and foundation.get("maximum_absolute") == max(
                ingame["maximum_error"][key]
                for key in ("hidden_absolute", "logits_absolute", "value_absolute")
            ) and foundation.get("source_base_tree") ==
            contract_validator.load(root / contract_validator.CONTRACT)["normal_game"]["source_base"]["tree"] and
            foundation.get("source_result_tree") == source_tree and
            re.fullmatch(r"[0-9a-f]{40}", source_tree) is not None and
            foundation.get("source_patch") == validate_source_patch(root),
            "M23 in-game foundation file identity drifted")
    return foundation
