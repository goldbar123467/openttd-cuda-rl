#!/usr/bin/env python3
"""Emit the initial V1 machine traceability registry from its human requirement table.

This is a bootstrap tool, not a status updater. Once implementation, tests, and
evidence are attached to requirements, update the reviewed registry deliberately;
do not overwrite it with this initializer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any


ROW = re.compile(
    r"^\| `(?P<id>(?:SCOPE|LIFE|STACK|PPO|OBS|ACT|REW|AI|MODEL|RUN|MON|"
    r"EVAL|REPRO|TEST|ARCH|DONE|EXP)-[0-9]{3})` \| "
    r"(?P<summary>.+?) \| (?P<acceptance>.+?) \| `(?P<status>[^`]+)` \|$"
)

SOURCE_SECTIONS = {
    "SCOPE": ["short:initial-scope-v1", "full:initial-environment-scope"],
    "LIFE": ["full:core-platform-requirements"],
    "STACK": ["full:implementation-stack"],
    "PPO": ["full:ppo-training-focus"],
    "OBS": ["full:observation-design"],
    "ACT": ["full:action-design"],
    "REW": ["full:reward-design"],
    "AI": ["full:existing-openttd-ais-and-agents"],
    "MODEL": [
        "full:neural-network-model-pipeline",
        "full:onnx-equivalence-requirements",
        "full:in-game-model-playback",
    ],
    "RUN": ["full:headless-training-runtime"],
    "MON": ["full:cli-training-monitor"],
    "EVAL": ["short:success-criteria", "full:evaluation-framework"],
    "REPRO": ["short:engineering-principles", "full:reproducibility-requirements"],
    "TEST": ["short:engineering-principles", "full:testing-requirements"],
    "ARCH": ["full:initial-architecture-comparison"],
    "DONE": ["short:success-criteria", "full:definition-of-done-v1"],
    "EXP": ["short:end-goal", "full:expansion-roadmap", "full:non-goals-v1"],
}


def milestone(identifier: str) -> tuple[str, str]:
    prefix, raw_number = identifier.split("-", 1)
    number = int(raw_number)
    if prefix == "EXP":
        return "POST_V1", "POST_V1"
    if prefix == "SCOPE":
        phase = "M02" if number <= 17 else "M04" if number == 18 else "M05" if number <= 24 else "M06" if number <= 26 else "M09"
    elif prefix == "LIFE":
        mapping = {
            1: "M03", 2: "M03", 3: "M02", 4: "M03", 5: "M03", 6: "M03", 7: "M03",
            8: "M06", 9: "M06", 10: "M07", 11: "M09", 12: "M07", 13: "M10",
            14: "M10", 15: "M11", 16: "M11", 17: "M10",
        }
        phase = mapping[number]
    elif prefix == "STACK":
        mapping = {
            1: "M11", 2: "M08", 3: "M08", 4: "M08", 5: "M11", 6: "M10",
            7: "M10", 8: "M08", 9: "M03", 10: "M11", 11: "M08",
        }
        phase = mapping[number]
    elif prefix == "PPO":
        phase = "M10" if number == 21 else "M07"
    elif prefix == "OBS":
        phase = "M09" if number == 18 else "M04"
    elif prefix == "ACT":
        phase = "M05"
    elif prefix == "REW":
        phase = "M09" if number == 8 else "M06"
    elif prefix == "AI":
        phase = "M09"
    elif prefix == "MODEL":
        phase = "M10" if number <= 9 else "M11"
    elif prefix == "RUN":
        mapping = {1: "M03", 2: "M03", 3: "M03", 4: "M03", 5: "M03", 6: "M07", 7: "M07", 8: "M09", 9: "M08", 10: "M03"}
        phase = mapping[number]
    elif prefix == "MON":
        phase = "M07"
    elif prefix == "EVAL":
        phase = "M09"
    elif prefix == "REPRO":
        phase = "M12"
    elif prefix == "TEST":
        mapping = {
            1: "M02", 2: "M04", 3: "M05", 4: "M06", 5: "M03", 6: "M05",
            7: "M06", 8: "M06", 9: "M07", 10: "M07", 11: "M10", 12: "M10",
            13: "M07", 14: "M07", 15: "M05", 16: "M12",
        }
        phase = mapping[number]
    elif prefix == "ARCH":
        phase = "M07" if number == 1 else "M08" if number <= 3 else "M09"
    elif prefix == "DONE":
        phase = "M12"
    else:  # pragma: no cover - ROW constrains prefixes
        raise ValueError(f"unmapped requirement prefix: {prefix}")
    return phase, "G" + phase[1:]


def parse_rows(markdown: pathlib.Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(markdown.read_text(encoding="utf-8").splitlines(), 1):
        match = ROW.match(line)
        if not match:
            continue
        row = match.groupdict()
        if row["id"] in seen:
            raise ValueError(f"{markdown}:{line_number}: duplicate requirement {row['id']}")
        seen.add(row["id"])
        rows.append(row)
    if not rows:
        raise ValueError(f"{markdown}: no requirement rows found")
    return rows


def build_registry(markdown: pathlib.Path, schema: pathlib.Path) -> dict[str, Any]:
    rows = parse_rows(markdown)
    requirements: list[dict[str, Any]] = []
    by_prefix: dict[str, list[str]] = {}
    for row in rows:
        identifier = row["id"]
        prefix = identifier.split("-", 1)[0]
        assigned_milestone, gate = milestone(identifier)
        test_ids = [f"V1-TEST-{prefix}"]
        if identifier == "TEST-016":
            test_ids.append("V1-TEST-TRACEABILITY-CONTRACT")
        post_v1 = prefix == "EXP"
        reviewer_note = (
            "Sequential post-V1 work remains forbidden until G12 passes."
            if post_v1
            else f"Initial machine mapping; implementation and acceptance evidence remain pending for {gate}."
        )
        if identifier == "STACK-001":
            reviewer_note = (
                "Whole-program C++ ownership can be audited only after the final V1 production "
                "controller exists; implementation and acceptance evidence remain pending for G11."
            )
        elif identifier == "STACK-005":
            reviewer_note = (
                "The auxiliary-only Python boundary can be audited completely only after training, "
                "export, and deployment exist; implementation and acceptance evidence remain pending for G11."
            )
        requirements.append(
            {
                "id": identifier,
                "mandatory": True,
                "release_scope": "POST_V1" if post_v1 else "V1",
                "summary": row["summary"],
                "acceptance": row["acceptance"],
                "source_sections": SOURCE_SECTIONS[prefix],
                "milestone": assigned_milestone,
                "gate": gate,
                "status": row["status"],
                "implementation": [],
                "test_ids": test_ids,
                "evidence": [],
                "legacy_evidence": [],
                "reviewer_note": reviewer_note,
            }
        )
        by_prefix.setdefault(prefix, []).append(identifier)

    tests: list[dict[str, Any]] = []
    for prefix, requirement_ids in by_prefix.items():
        deferred = prefix == "EXP"
        tests.append(
            {
                "id": f"V1-TEST-{prefix}",
                "summary": f"Planned requirement verification suite for {prefix} requirements.",
                "runner": None,
                "requirement_ids": requirement_ids,
                "status": "DEFERRED" if deferred else "PLANNED",
                "evidence": [],
                "mandatory": True,
                "reviewer_note": (
                    "This suite remains deferred with the post-V1 requirements."
                    if deferred
                    else "The owning milestone must replace or implement this planned suite before any linked requirement can pass."
                ),
            }
        )
    tests.append(
        {
            "id": "V1-TEST-TRACEABILITY-CONTRACT",
            "summary": "Validate schemas, Markdown parity, bidirectional mappings, aggregate gates, legacy separation, and defect propagation.",
            "runner": "scripts/v1/traceability.sh",
            "requirement_ids": ["TEST-016"],
            "status": "IMPLEMENTED",
            "evidence": [],
            "mandatory": True,
            "reviewer_note": "The contract runner exists; TEST-016 remains NOT_STARTED because the complete release quality matrix does not yet exist.",
        }
    )

    all_v1_non_done = [
        item["id"] for item in requirements
        if item["release_scope"] == "V1" and not item["id"].startswith("DONE-")
    ]
    model_ids = by_prefix["MODEL"]
    aggregate_dependencies = [
        {"requirement_id": "DONE-001", "dependency_ids": all_v1_non_done, "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-002", "dependency_ids": ["RUN-008", "PPO-018", "PPO-019", "TEST-013"], "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-003", "dependency_ids": ["EVAL-012", "EVAL-013"], "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-004", "dependency_ids": ["ARCH-001", "ARCH-002", "ARCH-003", "ARCH-004", "ARCH-005", "EVAL-007"], "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-005", "dependency_ids": ["AI-001", "AI-002", "AI-003", "AI-004"], "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-006", "dependency_ids": model_ids + ["TEST-011", "TEST-012", "LIFE-013", "LIFE-014", "LIFE-015", "LIFE-016", "LIFE-017"], "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-007", "dependency_ids": ["REPRO-009"], "requires_zero_release_blocking_defects": True},
        {"requirement_id": "DONE-008", "dependency_ids": [], "requires_zero_release_blocking_defects": True},
    ]
    return {
        "$schema": "schema/requirements-v1.schema.json",
        "schema_version": 1,
        "schema_sha256": hashlib.sha256(schema.read_bytes()).hexdigest(),
        "registry_kind": "openttd-rl-project-requirements",
        "scope": "V1-and-sequential-post-V1-roadmap",
        "source_briefs": [
            {
                "id": "short",
                "filename": "pasted-text-1.txt",
                "size_bytes": 2124,
                "line_count": 106,
                "sha256": "03d14e26b4e0b438e419d6f834ca99025c5a980eecee4c536c0cda5f7243b92a",
                "role": "Conservative bus-only V1 scope, engineering principles, expansion, and reliable-profitability goal.",
            },
            {
                "id": "full",
                "filename": "pasted-text-2.txt",
                "size_bytes": 19339,
                "line_count": 759,
                "sha256": "a7da553035e44468f29184a69c014f16bd1439fcbdf77275d0762073da306492",
                "role": "Complete C++/CUDA PPO lifecycle, observations/actions/rewards, evaluation, ONNX, monitoring, and in-game playback.",
            },
        ],
        "requirements": requirements,
        "tests": tests,
        "aggregate_dependencies": aggregate_dependencies,
        "legacy_evidence_policy": {
            "legacy_prefix": "evidence/p0/",
            "fresh_v1_evidence_required_for_pass": True,
            "legacy_artifacts_cannot_close_bus_requirements": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", type=pathlib.Path, required=True)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        registry = build_registry(args.markdown.resolve(strict=True), args.schema.resolve(strict=True))
    except (OSError, ValueError) as exc:
        print(f"V1 registry bootstrap failed: {exc}", file=sys.stderr)
        return 1
    json.dump(registry, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
