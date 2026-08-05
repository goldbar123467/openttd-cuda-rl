#!/usr/bin/env python3
"""Freeze and validate M15 stateful lifecycle/save-load replay evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import struct
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

from artifact_context import ArtifactContext, ArtifactRequirement

SCHEMA = pathlib.Path("docs/project/schema/v2-m15-episode-evidence.schema.json")
CONFIG = pathlib.Path("config/v2/m15-episode-evidence.json")
CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
ACTION_CONTRACT = pathlib.Path("config/v2/m15-action-contract.json")
ACTION_SOURCE = pathlib.Path("config/v2/m15-action-source.json")
EPISODE_SOURCE = pathlib.Path("config/v2/m15-episode-source.json")
PROGRAM = pathlib.Path("config/v2/m15-episode-program.json")
PROGRAM_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-episode-program.schema.json")
TRACE_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-episode-trace.schema.json")
RUN_DIRS = ["run-a", "run-b"]
FAMILIES = ["WAIT", "SELECT_TOWN_PAIR", "BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS", "SET_ROUTE", "START_VEHICLE", "STOP_VEHICLE", "SEND_TO_DEPOT", "SELL_VEHICLE", "MANAGE_LOAN"]
COMMANDS = {"WAIT": [], "SELECT_TOWN_PAIR": [], "BUILD_ROAD_PATH": ["CMD_BUILD_ROAD"], "BUILD_BUS_STOP": ["CMD_BUILD_ROAD_STOP"], "BUILD_ROAD_DEPOT": ["CMD_BUILD_ROAD_DEPOT"], "BUY_BUS": ["CMD_BUILD_VEHICLE"], "SET_ROUTE": ["CMD_DELETE_ORDER_ALL", "CMD_INSERT_ORDER", "CMD_INSERT_ORDER"], "START_VEHICLE": ["CMD_START_STOP_VEHICLE"], "STOP_VEHICLE": ["CMD_START_STOP_VEHICLE"], "SEND_TO_DEPOT": ["CMD_SEND_VEHICLE_TO_DEPOT"], "SELL_VEHICLE": ["CMD_SELL_VEHICLE"], "MANAGE_LOAN": ["CMD_INCREASE_LOAN"]}
LOGICAL_ARTIFACT_SET = "v2-m15-episode-evidence-a"
LIVE_CONSUMER = "m15-episode-evidence"


class M15EpisodeEvidenceError(ValueError):
    """The frozen M15 episode evidence is missing or inconsistent."""


@dataclass(frozen=True)
class M15EpisodeEvidenceSummary:
    runs: int
    transitions: int
    families: int
    maximum_rss_kib: int
    live: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15EpisodeEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15EpisodeEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15EpisodeEvidenceError(f"cannot hash {path}: {exc}") from exc


def schema_validate(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(instance)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15EpisodeEvidenceError(f"{label} schema failed at {location}: {exc.message}") from exc


def stable_key(family: int, parameters: list[int]) -> str:
    return hashlib.sha256(bytes([family]) + b"".join(struct.pack("<I", value) for value in parameters)).hexdigest()


def resource_values(path: pathlib.Path) -> tuple[int, float]:
    text = path.read_text(encoding="utf-8")
    rss_match = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    wall_match = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([0-9:.]+)", text)
    require(rss_match is not None and wall_match is not None, f"cannot parse resource transcript: {path}")
    parts = [float(item) for item in wall_match.group(1).split(":")]
    seconds = parts[-1] + (parts[-2] * 60 if len(parts) >= 2 else 0) + (parts[-3] * 3600 if len(parts) >= 3 else 0)
    return int(rss_match.group(1)), seconds


def validate_capture(artifact: pathlib.Path, step: dict[str, Any]) -> None:
    label = step["label"]
    save = artifact / f"{label}.sav"
    observation = artifact / f"{label}-observation.json"
    candidates = artifact / f"{label}-candidates.json"
    require(sha256_file(save) == step["save_sha256"], f"capture save drifted: {label}")
    observation_value = load_json(observation)
    candidate_value = load_json(candidates)
    observation_binary = observation.with_suffix(".bin")
    candidate_binary = candidates.with_suffix(".bin")
    require(sha256_file(observation_binary) == step["observation_sha256"] == observation_value["binary"]["sha256"], f"capture observation drifted: {label}")
    require(sha256_file(candidate_binary) == step["candidate_sha256"] == candidate_value["binary"]["sha256"], f"capture candidates drifted: {label}")


def project_run(root: pathlib.Path, artifact_root: pathlib.Path, directory: str) -> dict[str, Any]:
    artifact = artifact_root / directory
    require(artifact.is_dir() and not artifact.is_symlink(), f"episode run artifact is missing or a symlink: {directory}")
    trace_path = artifact / "episode-trace.json"
    trace = load_json(trace_path)
    schema_validate(trace, load_json(root / TRACE_SCHEMA), "M15 episode trace")
    program = load_json(root / PROGRAM)
    schema_validate(program, load_json(root / PROGRAM_SCHEMA), "M15 episode program")
    require(trace["contract_sha256"] == sha256_file(root / CONTRACT), "episode trace contract identity drifted")
    require(trace["program_sha256"] == sha256_file(root / PROGRAM) and trace["program_id"] == program["program_id"], "episode trace program identity drifted")
    require(len(trace["steps"]) == len(program["steps"]), "episode trace/program step count drifted")
    action_steps = 0
    native_commands = 0
    computed_coverage = [0] * len(FAMILIES)
    slots: dict[str, tuple[str, int]] = {}
    captures: list[dict[str, Any]] = []
    rollback: dict[str, Any] | None = None
    for ordinal, (expected, step) in enumerate(zip(program["steps"], trace["steps"], strict=True)):
        require(step["ordinal"] == ordinal and step["operation"] == expected["operation"] and step["label"] == expected["label"], f"episode step ordering drifted at {ordinal}")
        if expected["operation"] == "ACTION":
            action_steps += 1
            family = FAMILIES.index(expected["family"])
            computed_coverage[family] += 1
            require(step["family"] == expected["family"] and step["candidate"]["family_index"] == family and step["candidate"]["parameters"][0] == family, f"episode family mapping drifted at {ordinal}")
            require(step["candidate"]["stable_key"] == stable_key(family, step["candidate"]["parameters"]), f"episode stable key drifted at {ordinal}")
            actual_commands = [item["command"] for item in step["native_commands"]]
            require(actual_commands == COMMANDS[expected["family"]] and all(item["status"] == "SUCCESS" for item in step["native_commands"]), f"episode native command mapping drifted at {ordinal}")
            native_commands += len(actual_commands)
            require(step["tick_after"] - step["tick_before"] == expected["advance_ticks"], f"episode tick delta drifted at {ordinal}")
            if expected["advance_ticks"] == 0 and not actual_commands:
                require(step["state_sha256_before"] == step["state_sha256_after"], f"pure episode action mutated state at {ordinal}")
        elif expected["operation"] == "ROLLBACK":
            family = FAMILIES.index(expected["family"])
            require(step["family"] == "SET_ROUTE" and step["candidate"]["family_index"] == family and step["candidate"]["parameters"][0] == family, "episode rollback family mapping drifted")
            require(step["candidate"]["stable_key"] == stable_key(family, step["candidate"]["parameters"]), "episode rollback stable key drifted")
            expected_commands = [
                ("CMD_DELETE_ORDER_ALL", "EXECUTE", "SUCCESS"), ("CMD_INSERT_ORDER", "EXECUTE", "SUCCESS"),
                ("CMD_INSERT_ORDER", "INJECTED", "REJECTED"), ("CMD_DELETE_ORDER_ALL", "ROLLBACK", "SUCCESS"),
                ("CMD_INSERT_ORDER", "ROLLBACK", "SUCCESS"), ("CMD_INSERT_ORDER", "ROLLBACK", "SUCCESS"),
            ]
            actual_commands = [(item["command"], item["phase"], item["status"]) for item in step["native_commands"]]
            require(actual_commands == expected_commands and step["status"] == "NATIVE_REJECTED" and step["rolled_back"] is True, "episode rollback command sequence drifted")
            require(step["tick_after"] == step["tick_before"] and step["state_sha256_after"] == step["state_sha256_before"], "episode rollback mutated state or ticks")
            native_commands += len(actual_commands)
            rollback = {"family": "SET_ROUTE", "injected_command": "CMD_INSERT_ORDER", "native_commands": len(actual_commands), "rolled_back": True, "state_exact": True, "tick_delta": 0}
        elif expected["operation"] == "SAVE":
            slots[expected["slot"]] = (step["save_sha256"], step["bytes"])
            require(sha256_file(artifact / "artifacts" / f"{expected['slot']}.sav") == step["save_sha256"], "episode checkpoint save drifted")
            require(step["tick_before"] == step["tick_after"], "episode SAVE advanced ticks")
        elif expected["operation"] == "LOAD":
            require(expected["slot"] in slots and step["save_sha256"] == slots[expected["slot"]][0], "episode LOAD checkpoint identity drifted")
        else:
            validate_capture(artifact / "artifacts", step)
            captures.append(step)
            require(step["tick_before"] == step["tick_after"], "episode CAPTURE advanced ticks")
    coverage = [{"executions": count, "family_index": index, "name": name} for index, (name, count) in enumerate(zip(FAMILIES, computed_coverage, strict=True))]
    require(trace["coverage"] == coverage and all(computed_coverage), "episode family coverage drifted")
    require(trace["transitions"] == action_steps == 16, "episode transition count drifted")
    require(rollback is not None, "episode rollback probe is missing")
    require(trace["invariants"] == {"all_action_families_executed": True, "save_load_replay_exact": True}, "episode invariant claim drifted")
    require(len(captures) == 2 and trace["equivalence_groups"] == [{"captures": 2, "group": "save-load-suffix", "status": "EXACT"}], "episode replay group drifted")
    replay_fields = ["save_sha256", "observation_sha256", "candidate_sha256", "candidate_semantic_sha256"]
    require(all(captures[0][key] == captures[1][key] for key in replay_fields) and captures[0]["state_sha256_after"] == captures[1]["state_sha256_after"], "episode replay capture digests differ")
    rss, wall = resource_values(artifact / "resource.txt")
    checkpoint_sha, checkpoint_bytes = slots["route-ready"]
    return {
        "artifact_dir": directory, "outcome": "PASS", "projection_sha256": sha256_file(artifact / "reset-projection.json"), "trace_sha256": sha256_file(trace_path),
        "maximum_rss_kib": rss, "wall_seconds": wall, "transitions": trace["transitions"], "action_steps": action_steps, "native_commands": native_commands,
        "coverage": coverage, "rollback": rollback, "checkpoint": {"slot": "route-ready", "bytes": checkpoint_bytes, "save_sha256": checkpoint_sha, "loads": 2},
        "replay": {"group": "save-load-suffix", "captures": 2, "state_sha256": captures[0]["state_sha256_after"], **{key: captures[0][key] for key in replay_fields}, "status": "EXACT"},
        "initial_state_sha256": trace["initial"]["state_sha256"], "final_state_sha256": trace["final"]["state_sha256"],
    }


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"runs": len(runs), "passed": sum(item["outcome"] == "PASS" for item in runs), "transitions_per_run": runs[0]["transitions"], "action_steps_per_run": runs[0]["action_steps"], "native_commands_per_run": runs[0]["native_commands"], "maximum_rss_kib": max(item["maximum_rss_kib"] for item in runs), "maximum_wall_seconds": max(item["wall_seconds"] for item in runs)}


def _recorded_artifact_set(config: dict[str, Any]) -> str:
    recorded_base = config["artifact_base_hint"]
    parts = recorded_base.split("/")
    require(
        recorded_base.startswith("/")
        and not recorded_base.startswith("//")
        and all(part not in {"", ".", ".."} for part in parts[1:]),
        "M15 episode recorded artifact base is not an absolute normalized POSIX path",
    )
    require(
        config["artifact_root"] == LOGICAL_ARTIFACT_SET,
        "M15 episode logical artifact set drifted",
    )
    return config["artifact_root"]


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    config = load_json(root / CONFIG)
    logical_set = _recorded_artifact_set(config)
    requirements: list[ArtifactRequirement] = []
    for record in config["runs"]:
        directory = record["artifact_dir"]
        fixed_files = (
            ("episode-trace.json", record["trace_sha256"]),
            ("reset-projection.json", record["projection_sha256"]),
            ("resource.txt", None),
            ("artifacts/route-ready.sav", record["checkpoint"]["save_sha256"]),
        )
        replay = record["replay"]
        capture_files = tuple(
            (f"artifacts/capture-branch-{branch}{suffix}", digest)
            for branch in ("a", "b")
            for suffix, digest in (
                (".sav", replay["save_sha256"]),
                ("-observation.json", None),
                ("-observation.bin", replay["observation_sha256"]),
                ("-candidates.json", None),
                ("-candidates.bin", replay["candidate_sha256"]),
            )
        )
        for filename, digest in fixed_files + capture_files:
            requirements.append(ArtifactRequirement(
                logical_set,
                f"{directory}/{filename}",
                "file",
                LIVE_CONSUMER,
                digest,
            ))
    return tuple(requirements)


def freeze(root: pathlib.Path, artifact_root: pathlib.Path, output: pathlib.Path) -> pathlib.Path:
    root, artifact_root, output = root.resolve(), artifact_root.resolve(), output.resolve()
    require(artifact_root.is_dir() and not artifact_root.is_symlink(), "episode artifact root is missing or a symlink")
    require(not output.exists() and not output.is_symlink(), "refusing to overwrite frozen episode evidence")
    runs = [project_run(root, artifact_root, directory) for directory in RUN_DIRS]
    require(runs[0]["trace_sha256"] == runs[1]["trace_sha256"], "episode full-run traces are not byte-identical")
    source = load_json(root / EPISODE_SOURCE)
    recorded = load_json(root / CONFIG)
    value = {
        "$schema": "../../docs/project/schema/v2-m15-episode-evidence.schema.json", "schema_version": "openttd-rl-v2-m15-episode-evidence-1", "schema_sha256": sha256_file(root / SCHEMA), "snapshot_date": "2026-08-02",
        "contract_sha256": sha256_file(root / CONTRACT), "action_contract_sha256": sha256_file(root / ACTION_CONTRACT), "action_source_sha256": sha256_file(root / ACTION_SOURCE), "episode_source_sha256": sha256_file(root / EPISODE_SOURCE),
        "program_schema_sha256": sha256_file(root / PROGRAM_SCHEMA), "trace_schema_sha256": sha256_file(root / TRACE_SCHEMA), "program_sha256": sha256_file(root / PROGRAM),
        "executable": {key: source["build"]["executable"][key] for key in ("sha256", "size")}, "artifact_base_hint": recorded["artifact_base_hint"], "artifact_root": artifact_root.name, "runs": runs,
        "determinism": {"primary_artifact_dir": RUN_DIRS[0], "repeat_artifact_dir": RUN_DIRS[1], "trace_sha256": runs[0]["trace_sha256"], "byte_identical": True},
        "policy": {"all_twelve_families_executed": True, "authoritative_native_commands": True, "exact_tick_advancement": True, "native_save_load": True, "state_save_observation_candidate_replay_exact": True, "full_program_repeat_exact": True, "g15_pass_claim": False},
        "summary": summarize(runs),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    validate(
        root,
        output,
        artifact_context=ArtifactContext.live(artifact_root.parent),
    )
    return output


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15EpisodeEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    schema_validate(config, schema, "M15 episode evidence")
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 episode evidence schema SHA-256 mismatch")
    for field, path in (("contract_sha256", CONTRACT), ("action_contract_sha256", ACTION_CONTRACT), ("action_source_sha256", ACTION_SOURCE), ("episode_source_sha256", EPISODE_SOURCE), ("program_schema_sha256", PROGRAM_SCHEMA), ("trace_schema_sha256", TRACE_SCHEMA), ("program_sha256", PROGRAM)):
        require(config[field] == sha256_file(root / path), f"M15 episode evidence {field} drifted")
    source = load_json(root / EPISODE_SOURCE)
    require(config["executable"] == {key: source["build"]["executable"][key] for key in ("sha256", "size")}, "M15 episode executable identity drifted")
    require([item["artifact_dir"] for item in config["runs"]] == RUN_DIRS, "M15 episode run ordering drifted")
    require(config["summary"] == summarize(config["runs"]), "M15 episode evidence summary drifted")
    require(config["runs"][0]["trace_sha256"] == config["runs"][1]["trace_sha256"] == config["determinism"]["trace_sha256"], "M15 episode deterministic trace lock drifted")
    logical_set = _recorded_artifact_set(config)
    if context.is_live:
        context.preflight(required_live_inputs(root))
        artifact_root = context.artifact_set(logical_set)
        require([project_run(root, artifact_root, directory) for directory in RUN_DIRS] == config["runs"], "M15 episode live runs drifted")
    return M15EpisodeEvidenceSummary(len(config["runs"]), config["summary"]["transitions_per_run"], len(config["runs"][0]["coverage"]), config["summary"]["maximum_rss_kib"], context.is_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.artifact_root is not None:
            require(args.output is not None, "creation requires --output")
            path = freeze(args.root, args.artifact_root, args.output)
            print(f"V2_M15_EPISODE_EVIDENCE=FROZEN path={path} sha256={sha256_file(path)}")
            return 0
        require(args.output is None, "creation requires --artifact-root and --output")
        summary = validate(args.root, artifact_context=ArtifactContext.offline())
        print(f"V2_M15_EPISODE_EVIDENCE=PASS runs={summary.runs} transitions={summary.transitions} families={summary.families} max_rss_kib={summary.maximum_rss_kib} live={str(summary.live).lower()}")
        return 0
    except (M15EpisodeEvidenceError, OSError, ValueError) as exc:
        print(f"V2_M15_EPISODE_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
