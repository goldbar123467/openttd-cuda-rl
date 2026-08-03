#!/usr/bin/env python3
"""Validate the pre-result M23 packaging, playback, reproduction, and publication contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema


CONTRACT = pathlib.Path("config/v2/m23-release-contract.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m23-release-contract.schema.json")
REQUIREMENTS_REGISTRY = pathlib.Path("docs/project/requirements-v2.json")

FOUNDATIONS = [
    ("config/v2/m22-learning-contract.json", "f3ae8f89dfb6edf19b910c55f55845279b77ddd7be5adbd1db244984f968b07b"),
    ("config/v2/m22-native-corpus.json", "0af952bb840bca2a80a577e2a2446845f2db749d7efbaeb06af4b94418ff6725"),
    ("config/v2/m22-training-evidence.json", "1a0019a83816981ca355ae7c51f175fc482b2afecc45413d23d55a9ae2c177b1"),
    ("config/v2/m22-qualification-evidence.json", "192f784c54420f99e01384c4c453e2df651c2d87b479c0bee3dc46bf3b5a3798"),
    ("config/v2/m22-followup-v2-evaluation-evidence.json", "21e53fa3c7f7f5a15fcd9f199f0a59920082f3e03b8292ed968da44e9dc319ec"),
    ("config/v2/m22-followup-runtime-source.json", "bea83243dc68f72ebd14d1d944a800f0087c9283d7c0f3421b854d8c8adba15c"),
    ("docs/project/G22_GATE_REPORT.md", "5043d91b0fafb04c6fef44a57ad8123f3d2c3469b2c5d75fa6c6b81cae35254c"),
    ("config/v2/m14-competition-manifest.json", "2218667f2ca74740bfbe57af3a978eb2ee33f925eb6e2faaed03394a04bb98ee"),
    ("config/v2/m21-content-lock.json", "31d2ebd04f8eea4226e1f50a4dba28b1f11567bc2f7a1b33d059102d2346e266"),
    ("config/v1/m10-model-package-contract.json", "174689b55f7c47a23d5e435b53a889343b07d9f88c3c83df648c011dcb77caf8"),
    ("config/v1/m11-playback-contract.json", "7ae56b5c450bfc4c8d9aa0147a4da5ed182b64f5cc73172a48b62ec586c68bf4"),
    ("config/v1/m12-release-contract.json", "59e56686bbd09a924e64f01958ab8d1d0b41f5625ad857a3976b4a6d67a4dc1c"),
    ("config/v1/m13-publication-contract.json", "5ff5cc2ff085e0b5d3c9af8b0c76af22aadd9f48ac868290e84963c48281bb67"),
]

PROGRAMS = [
    "wait", "road-passenger", "road-cargo", "rail-passenger", "rail-freight", "ship-natural",
    "ship-constructed", "air-service", "air-helicopter", "multimodal-transfer", "mode-router",
    "competition-head-to-head", "calendar-inspect", "authority-economy", "event-recovery",
    "gamescript-response", "content-discovery",
]
ARCHITECTURES = ["monolithic-generalist-v1", "specialist-router-v1"]
CHECKPOINT_INVENTORY = [
    "COMMITTED", "m22.manifest", "model.pt", "optimizer.pt", "runtime.pt", "selection.json", "trainer-state.bin",
]
CHECKPOINTS = {
    "monolithic-generalist-v1": {
        "role": "development-selected-and-g22-accepted-in-game-policy",
        "id": "03894fd1238b69b6724d82eb441380312be4e8226efa602fa5e43972f7fa9f5f",
        "files": [
            ("COMMITTED", 65, "1bce450303dd9c4d7eb43d4b8989edd01078f35cfa1287768ab10772fa7011e0"),
            ("m22.manifest", 806, "82e2d0ed0b49f2a3774b7a8a6187b7b7540d74149941f4e91693f1a8f3e4297e"),
            ("model.pt", 5882820, "ad98f92fa9dfd07b14a49373676746c87419cafcad81bc834dd8bdf435d432c3"),
            ("optimizer.pt", 11530487, "c4c9177f02f4bed840d5f9a671da16381682b74dc02c23bc199734690317eaff"),
            ("runtime.pt", 10863, "5f9869a7ae0e6d9ba8d2b3caeca7ab02d8331f51087ccb336a4cabb25df0c2d7"),
            ("selection.json", 103, "b8301da160f25aa27f759abc4da50f212d90e7bcc03c5f1989e1ca8a690c2cc2"),
            ("trainer-state.bin", 27702, "2250fbbbfbd6a77d8bf06acd6d8db67b7fe642bc7550b3f81efcf11cb5dfce36"),
        ],
    },
    "specialist-router-v1": {
        "role": "matched-learned-architecture-comparison",
        "id": "458b2b1413ca483cb9b061518ce9d80e5e9afc85852a66015d81da07bcc7fd2f",
        "files": [
            ("COMMITTED", 65, "6658855c4fc5a565188474b79cac0f8a0eb8dae2da8d95f452578527e0afb102"),
            ("m22.manifest", 802, "dba54376419477da7f3f7c34ae8c6ca9c9432e9b475955aa2de165df3e115ecf"),
            ("model.pt", 5882820, "97ee5a0ad5ab65df9d729318b0423b55bf7a7b57c09e5aaf1726eceb28990595"),
            ("optimizer.pt", 11538679, "156599a49fa761107cd5ace9861ca451e2d863fbe2891a626eae59570ab462ee"),
            ("runtime.pt", 10863, "f558519ab08348ab70e5d762c33497574a3335ed76c3db0889f4c665b3222ae2"),
            ("selection.json", 103, "b8301da160f25aa27f759abc4da50f212d90e7bcc03c5f1989e1ca8a690c2cc2"),
            ("trainer-state.bin", 27702, "0c258ca38ab998c2580c098479e5e68c9ce1a1851bfdc9b5f645da51bb78d213"),
        ],
    },
}
REQUIREMENTS = [f"V2-RELEASE-{index:03d}" for index in range(1, 10)]
MODES = ["road", "rail", "water", "air", "multimodal", "company", "broad"]
VISIBLE_MODES = ["road", "rail", "water", "air", "multimodal", "company"]
OPPONENTS = ["AAAHogEx", "KrakenAI2", "NoOpAI"]
PLAYBACK_CAMPAIGNS = [
    ("visible-road-passenger-kraken", "road-passenger", "road", "temperate", 128, 128, "KrakenAI2"),
    ("visible-road-cargo-control", "road-cargo", "road", "toyland", 128, 128, "NoOpAI"),
    ("visible-rail-passenger-aaahogex", "rail-passenger", "rail", "arctic", 128, 128, "AAAHogEx"),
    ("visible-rail-freight-kraken", "rail-freight", "rail", "tropic", 512, 128, "KrakenAI2"),
    ("visible-water-aaahogex", "ship-natural", "water", "tropic", 512, 128, "AAAHogEx"),
    ("visible-air-kraken", "air-service", "air", "toyland", 128, 128, "KrakenAI2"),
    ("visible-multimodal-aaahogex", "multimodal-transfer", "multimodal", "temperate", 128, 128, "AAAHogEx"),
    ("visible-company-kraken", "competition-head-to-head", "company", "arctic", 128, 128, "KrakenAI2"),
]


class M23ContractError(ValueError):
    """The M23 contract is incomplete, inconsistent, or no longer frozen."""


@dataclass(frozen=True)
class M23ContractSummary:
    checkpoints: int
    deployment_architectures: int
    equivalence_cases: int
    runtime_results: int
    playback_campaigns: int
    requirements: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M23ContractError(message)


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M23ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M23ContractError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derived_seed(domain: str, ordinal: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{domain}:{ordinal}".encode("ascii")).digest()[:4], "big") & 0x7FFFFFFF


def checkpoint_id(item: dict[str, Any]) -> str:
    files = {entry["name"]: entry["sha256"] for entry in item["files"]}
    identity = "\n".join([
        "v2-m22-generalist-checkpoint-v1",
        FOUNDATIONS[0][1],
        FOUNDATIONS[1][1],
        item["architecture_id"],
        str(item["run_seed"]),
        files["model.pt"],
        files["optimizer.pt"],
        files["runtime.pt"],
        files["trainer-state.bin"],
        files["selection.json"],
        "after-completed-ppo-update-and-retention-check-before-next-rollout",
        "",
    ])
    return hashlib.sha256(identity.encode("ascii")).hexdigest()


def schema_validate(value: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M23ContractError(f"M23 release contract schema failed at {location}: {exc.message}") from exc


def _validate_foundations(root: pathlib.Path, contract: dict[str, Any]) -> None:
    foundations = contract["foundations"]
    require(foundations["accepted_g22_commit"] == "e027ab69a39cbe929db0fddafebbc1696b26e0d7",
            "accepted G22 commit drifted")
    require(foundations["openttd_release"] == "15.3" and
            foundations["openttd_upstream_commit"] == "29f808ef0022064e6d9a83c8476d1e0f4686af86" and
            foundations["corrected_m22_source_tree"] == "f8985045f9ba14bad1e46a81cb58fdbb8037f277",
            "OpenTTD or corrected M22 source foundation drifted")
    actual = [(item["path"], item["sha256"]) for item in foundations["files"]]
    require(actual == FOUNDATIONS, "M23 foundation inventory or declared identity drifted")
    for relative, expected in FOUNDATIONS:
        require(sha256(root / relative) == expected, f"M23 foundation bytes drifted: {relative}")
    require(foundations["v1_boundary"] ==
            "released-v1-tag-and-package-remain-byte-unchanged-and-revalidated-at-g23",
            "V1 preservation boundary weakened")


def _validate_checkpoints(contract: dict[str, Any]) -> None:
    section = contract["checkpoint_packages"]
    require(section["format"] == "openttd-rl-v2-m22-checkpoint-package-1" and
            section["inventory"] == CHECKPOINT_INVENTORY and
            section["copy_policy"] == "exact-byte-copy-no-rewrite-no-symlink-no-extra-file" and
            section["maximum_total_bytes_per_checkpoint"] == 33554432,
            "checkpoint package format, inventory, copy policy, or byte limit drifted")
    architectures = section["architectures"]
    require([item["architecture_id"] for item in architectures] == ARCHITECTURES,
            "checkpoint architecture inventory or order drifted")
    for item in architectures:
        expected = CHECKPOINTS[item["architecture_id"]]
        require(item["role"] == expected["role"] and item["checkpoint_id"] == expected["id"] and
                item["parameter_count"] == 1457520 and item["run_seed"] == 1636894266 and item["update"] == 32,
                f"checkpoint selection metadata drifted: {item['architecture_id']}")
        files = [(entry["name"], entry["bytes"], entry["sha256"]) for entry in item["files"]]
        require(files == expected["files"], f"checkpoint exact file identity drifted: {item['architecture_id']}")
        require(sum(entry[1] for entry in files) <= section["maximum_total_bytes_per_checkpoint"],
                "checkpoint exceeds its frozen byte limit")
        require(checkpoint_id(item) == item["checkpoint_id"],
                f"checkpoint content address does not recompute: {item['architecture_id']}")
    require(section["publication"] == "both-exact-checkpoints-are-required-release-payloads" and
            "both-architectures" in section["load_test"], "checkpoint publication or load-test boundary weakened")


def _validate_deployment(contract: dict[str, Any]) -> None:
    section = contract["deployment_packages"]
    require(section["format"] == "openttd-rl-v2-deployment-package-1" and
            section["compatibility_version"] == 1 and
            section["payload_files"] == ["model.onnx", "golden.jsonl", "evaluation.json", "INSTALL.md", "MODEL_CARD.md"] and
            section["complete_inventory"] == "manifest-plus-exact-payload-list-no-symlinks-no-unknown-files",
            "deployment package format or exact inventory drifted")
    architectures = section["architectures"]
    require([item["architecture_id"] for item in architectures] == ARCHITECTURES,
            "deployment architecture inventory or order drifted")
    require([item["checkpoint_id"] for item in architectures] == [CHECKPOINTS[name]["id"] for name in ARCHITECTURES],
            "deployment source checkpoint identities drifted")
    require(architectures[0]["role"] == "accepted-default-in-game-policy" and
            architectures[1]["role"] == "published-matched-comparison",
            "deployment architecture roles drifted")
    graph = section["graph"]
    require(graph["format"] == "ONNX" and graph["opset"] == 18 and graph["onnxruntime"] == "1.28.0" and
            graph["dynamic_axis"] == "batch-only-positive-bounded-1-through-32" and
            graph["training_nodes"] == "forbidden" and graph["optimizer_state"] == "forbidden",
            "ONNX graph/runtime boundary drifted")
    require(graph["inputs"] == [
        {"name": "public_features", "dtype": "float32", "shape": ["batch", 32]},
        {"name": "program_mask", "dtype": "bool", "shape": ["batch", 17]},
        {"name": "hidden_state", "dtype": "float32", "shape": ["batch", 256]},
        {"name": "recurrent_reset", "dtype": "bool", "shape": ["batch"]},
    ] and graph["outputs"] == [
        {"name": "program_logits", "dtype": "float32", "shape": ["batch", 17]},
        {"name": "program_value", "dtype": "float32", "shape": ["batch"]},
        {"name": "next_hidden", "dtype": "float32", "shape": ["batch", 256]},
    ], "deployment graph signature drifted")
    adapter = section["adapter"]
    require(adapter["learned_scope"] == "recurrent-17-program-selection-only" and
            adapter["reset"] == "true-row-zeros-hidden-before-GRUCell-false-row-carries-hidden" and
            adapter["base_and_program_projection"] == "exact-M22-evaluation-input-construction" and
            adapter["nonfinite"] == "reject-before-inference",
            "deployment adapter semantic boundary drifted")
    dependencies = section["dependency_boundary"]
    require(dependencies["required"] == ["OpenTTD-runtime", "ONNX-Runtime-CPU", "OpenSSL-Crypto"] and
            dependencies["forbidden"] == ["LibTorch", "Python-runtime", "CUDA", "optimizer", "trainer"],
            "inference-only dependency boundary drifted")


def _validate_equivalence(contract: dict[str, Any]) -> int:
    section = contract["equivalence"]
    require(section["runtimes"] == [
        "native-libtorch-cpu", "standalone-onnxruntime-cpu", "source-integrated-ingame-onnxruntime-cpu",
    ] and section["architectures"] == ARCHITECTURES, "runtime or architecture equivalence scope drifted")
    require(section["cases_per_architecture"] == 24 and section["total_architecture_cases"] == 48,
            "equivalence case count drifted")
    require(sum(item["count_per_architecture"] for item in section["case_classes"]) == 24 and
            [item["id"] for item in section["case_classes"]] == [
                "public-final-projection", "recurrent-sequence-and-reset", "finite-boundary-and-mask-adversarial",
            ], "equivalence case classes drifted")
    generation = section["generation"]
    require(generation == {
        "domain": "openttd-rl-v2-m23-golden-v1", "ordinal_start": 0, "seed_count": 48,
        "canonical_encoding": "compact-sorted-json-lines-one-LF-per-record",
        "post_result_case_change": "forbidden",
    }, "golden case generation boundary drifted")
    coverage = section["coverage"]
    require(coverage["batch_sizes"] == [1, 8, 32] and coverage["modes"] == MODES and
            coverage["climates"] == ["temperate", "arctic", "tropic", "toyland"] and
            set(coverage["mask_patterns"]) == {"wait-only", "all-legal", "one-active-plus-wait", "deterministic-sparse"} and
            set(coverage["recurrent"]) == {"zero-reset", "nonzero-carry", "mixed-row-reset", "four-step-carried-sequence"},
            "golden equivalence coverage drifted")
    require(section["outputs"] == ["program_logits", "program_value", "next_hidden", "greedy_legal_program"],
            "equivalence output inventory drifted")
    tolerances = section["tolerances"]
    for name in ("program_logits", "program_value", "next_hidden"):
        require(tolerances[name] == {"absolute": 0.00005, "relative": 0.00005},
                f"equivalence tolerance drifted: {name}")
    require(tolerances["program_mask"] == "byte-exact" and tolerances["greedy_legal_program"] == "exact" and
            tolerances["nonfinite"] == "reject", "exact/nonfinite equivalence boundary drifted")
    rejection = section["rejection_matrix"]
    require(len(rejection) == 28 and len(set(rejection)) == 28 and
            {"checkpoint-id", "recurrent-width", "nonfinite-input", "all-illegal-mask", "batch-over-32"}.issubset(rejection),
            "equivalence rejection matrix drifted")
    runtime_results = len(section["runtimes"]) * section["total_architecture_cases"]
    require(section["success"].startswith(f"all-{runtime_results}-runtime-case-results"),
            "equivalence success count drifted")
    return runtime_results


def _validate_normal_game(root: pathlib.Path, contract: dict[str, Any]) -> None:
    section = contract["normal_game"]
    require(section["source_base"] == {
        "record": "config/v2/m22-followup-runtime-source.json",
        "record_sha256": FOUNDATIONS[5][1],
        "tree": "f8985045f9ba14bad1e46a81cb58fdbb8037f277",
    }, "normal-game source base drifted")
    require(section["entrypoint"] == "openttd -B <absolute-v2-playback-config.json>" and
            section["configuration"]["schema_version"] == "openttd-rl-v2-m23-playback-config-1" and
            section["configuration"]["policy_interval_ticks"] == {"minimum": 128, "maximum": 1024, "multiple": 128},
            "normal-game entrypoint or configuration boundary drifted")
    boundary = section["controller_boundary"]
    require(boundary["learned"] == "select-one-legal-high-level-program-from-public-state-and-carried-hidden-state" and
            boundary["deterministic"] == "reviewed-program-executor-plans-and-submits-normal-OpenTTD-commands" and
            boundary["admin_shortcuts"].startswith("forbidden") and
            boundary["qualification_only_state_injection"] == "forbidden",
            "learned/deterministic controller or no-admin boundary drifted")
    require(section["program_executors"] == PROGRAMS, "normal-game executor inventory or order drifted")
    seed = section["campaign_seed"]
    require(seed == {"domain": "openttd-rl-v2-m23-playback-v1", "ordinal_start": 0},
            "visible campaign seed domain drifted")
    campaigns = section["campaigns"]
    require(len(campaigns) == len(PLAYBACK_CAMPAIGNS), "visible campaign count drifted")
    for index, (item, expected) in enumerate(zip(campaigns, PLAYBACK_CAMPAIGNS, strict=True)):
        actual = (item["id"], item["program"], item["mode"], item["climate"], item["map_width"],
                  item["map_height"], item["opponent"])
        require(actual == expected, f"visible campaign content or order drifted: {index}")
        require(item["seed"] == derived_seed(seed["domain"], index), f"visible campaign seed drifted: {item['id']}")
    acceptance = section["campaign_acceptance"]
    require(acceptance["normal_gui"] is True and acceptance["headless_or_dedicated"] is False and
            acceptance["minimum_policy_boundaries_per_campaign"] == 4 and
            acceptance["required_mode_coverage"] == VISIBLE_MODES and acceptance["required_opponents"] == OPPONENTS and
            acceptance["required_all_campaigns"] is True and "positive-operating-income" in acceptance["required_outcomes"] and
            "screenshot" in acceptance["visible_evidence"] and acceptance["save_load"].startswith("at-least-one-campaign-per-mode"),
            "visible normal-game acceptance weakened")
    roster = load(root / "config/v2/m14-competition-manifest.json")["roster"]
    require([item["name"] for item in roster["tournament"]] + [item["name"] for item in roster["controls"]] == OPPONENTS,
            "visible opponent set no longer matches the admitted M14 roster")
    inspection = section["inspection"]
    require(set(inspection["required_fields"]) == {
        "state", "health", "architecture", "package_id", "checkpoint_id", "program", "confidence", "value",
        "legal_programs", "hidden_norm", "executor_phase", "last_command", "last_error",
    }, "inspection field inventory drifted")
    require(set(section["controls"]) == {"start", "stop", "pause", "step", "reload", "game_pause"},
            "operator control inventory drifted")
    failure = section["failure_policy"]
    require(failure["startup"].startswith("fail-closed") and failure["safe_fallback"] ==
            "wait-program-only-no-construction-vehicle-or-order-command" and
            set(failure["required_rejections"]) == {
                "missing-config", "invalid-config", "missing-package", "incompatible-package", "corrupt-model",
                "bad-graph-signature", "nonfinite-output", "all-illegal-mask", "executor-command-failure",
                "reload-incompatible-package",
            }, "normal-game failure/fallback contract drifted")


def _validate_operator_release(contract: dict[str, Any]) -> None:
    section = contract["operator_release"]
    require(section["guide"]["path"] == "docs/project/V2_RELEASE_REPRODUCTION.md" and
            section["guide"]["one_linear_workflow"] == [
                "prerequisites", "clone", "build", "train", "resume", "evaluate", "export", "install", "play",
                "tournament", "verify", "troubleshoot",
            ], "operator guide workflow drifted")
    require(section["documents"] == [
        "README.md", "docs/project/V2_RELEASE_REPRODUCTION.md", "docs/project/V2_MODEL_CARD.md",
        "docs/project/V2_BENCHMARK.md", "docs/project/V2_PUBLICATION.md", "THIRD_PARTY_NOTICES.md", "LICENSE",
    ], "release documentation inventory drifted")
    manifest = section["release_manifest"]
    require(manifest["schema_version"] == "openttd-rl-v2-m23-release-manifest-1" and
            manifest["required_sections"] == [
                "source", "host", "builds", "dependencies", "contracts", "checkpoints", "models", "seeds",
                "equivalence", "playback", "tournament", "artifacts", "quality", "traceability", "defects",
                "reproduction", "publication",
            ], "release manifest section inventory drifted")
    reproduction = section["reproduction"]
    require(reproduction["roots"] == 2 and reproduction["raw_roots"].startswith("distinct-empty-fresh-local-clones") and
            reproduction["network"].startswith("disabled-after-clone") and
            reproduction["required_matches"] == [
                "source-tree-byte", "native-binary-byte", "ingame-binary-byte", "checkpoint-byte", "onnx-byte",
                "package-id", "golden-byte", "equivalence-semantic", "playback-semantic", "tournament-semantic",
                "release-manifest-byte", "publication-archive-byte",
            ], "two-root semantic/byte reproduction boundary drifted")
    quality = section["quality"]
    require(quality["v2_tests"] == "all-pass" and quality["v1_regression"] == "all-pass-unchanged" and
            quality["nonclosed_defects"] == 0 and all(quality[name] is True for name in (
                "git_diff_check", "credential_scan", "host_path_scan", "symlink_scan",
            )), "release quality or zero-defect boundary drifted")
    publication = section["publication"]
    require(publication["tag"] == "v2.0.0" and publication["branch"] == "main" and
            all(publication[name] is True for name in (
                "require_clean_main", "require_origin_sync", "require_reviewed_commit_equals_tag",
                "require_release_asset_round_trip", "require_hosted_quality", "v1_tag_and_asset_revalidation",
            )), "reviewed-byte publication boundary drifted")
    excluded = set(section["archive"]["excluded"])
    require({"OpenTTD-binaries", "third-party-AI-archives", "NewGRF-archives", "private-unselected-checkpoints"}.issubset(excluded),
            "publication archive exclusion boundary drifted")


def _validate_requirements(root: pathlib.Path, contract: dict[str, Any]) -> None:
    require(contract["requirements"] == REQUIREMENTS, "M23 requirement inventory or order drifted")
    registry = load(root / REQUIREMENTS_REGISTRY)
    rows = {item["id"]: item for item in registry["requirements"]}
    require(all(requirement in rows for requirement in REQUIREMENTS), "M23 requirement missing from registry")
    for requirement in REQUIREMENTS:
        row = rows[requirement]
        require(row["mandatory"] is True and row["milestone"] == "M23" and row["gate"] == "G23" and
                row["status"] in {"PLANNED", "PASS"} and row["test_ids"] == ["V2-TEST-G23"],
                f"M23 registry boundary drifted: {requirement}")


def validate(root: pathlib.Path, contract_path: pathlib.Path | None = None) -> M23ContractSummary:
    root = root.resolve()
    path = contract_path or root / CONTRACT
    contract = load(path)
    schema = load(root / SCHEMA)
    schema_validate(contract, schema)
    require(contract["schema_sha256"] == sha256(root / SCHEMA), "M23 release contract schema SHA-256 mismatch")
    _validate_foundations(root, contract)
    _validate_checkpoints(contract)
    _validate_deployment(contract)
    runtime_results = _validate_equivalence(contract)
    _validate_normal_game(root, contract)
    _validate_operator_release(contract)
    _validate_requirements(root, contract)
    acceptance = contract["acceptance"]
    require(acceptance["freeze_before_export"] is True and
            acceptance["definition_of_done"].startswith("all-86-v2-requirements") and
            acceptance["publication"].startswith("reviewed-main-commit-tag-release"),
            "M23 definition-of-done or publication acceptance weakened")
    return M23ContractSummary(
        checkpoints=len(contract["checkpoint_packages"]["architectures"]),
        deployment_architectures=len(contract["deployment_packages"]["architectures"]),
        equivalence_cases=contract["equivalence"]["total_architecture_cases"],
        runtime_results=runtime_results,
        playback_campaigns=len(contract["normal_game"]["campaigns"]),
        requirements=len(contract["requirements"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--contract", type=pathlib.Path)
    arguments = parser.parse_args()
    try:
        result = validate(arguments.root, arguments.contract)
        print(
            f"V2_M23_RELEASE_CONTRACT=PASS checkpoints={result.checkpoints} "
            f"architectures={result.deployment_architectures} cases={result.equivalence_cases} "
            f"runtime_results={result.runtime_results} playback={result.playback_campaigns} "
            f"requirements={result.requirements}"
        )
        return 0
    except (M23ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M23_RELEASE_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
