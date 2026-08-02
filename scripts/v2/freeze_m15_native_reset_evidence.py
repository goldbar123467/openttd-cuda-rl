#!/usr/bin/env python3
"""Freeze retained live M15 reset artifacts into a compact checked-in matrix."""

from __future__ import annotations

import argparse
import json
import pathlib

import qualify_m15_native_reset
import validate_m15_native_reset_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-base", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    artifact_base = args.artifact_base.resolve()
    output = args.output.resolve()
    if output.exists() or output.is_symlink():
        raise SystemExit(f"refusing to overwrite {output}")
    source = validate_m15_native_reset_evidence.load_json(root / qualify_m15_native_reset.SOURCE)
    results = [
        validate_m15_native_reset_evidence.result_from_live(artifact_base / artifact_dir, run, artifact_dir)
        for run, artifact_dir, _, _ in validate_m15_native_reset_evidence.EXPECTED
    ]
    value = {
        "$schema": "../../docs/project/schema/v2-m15-native-reset-evidence.schema.json",
        "schema_version": "openttd-rl-v2-m15-native-reset-evidence-1",
        "schema_sha256": validate_m15_native_reset_evidence.sha256_file(root / validate_m15_native_reset_evidence.SCHEMA),
        "snapshot_date": "2026-08-02",
        "contract_sha256": validate_m15_native_reset_evidence.sha256_file(root / qualify_m15_native_reset.CONTRACT),
        "native_source_sha256": validate_m15_native_reset_evidence.sha256_file(root / qualify_m15_native_reset.SOURCE),
        "executable": {key: source["build"]["executable"][key] for key in ("sha256", "size")},
        "artifact_base_hint": str(artifact_base),
        "seed": 1110312784,
        "policy": {
            "native_source_integrated": True, "sandboxed": True, "no_overwrite": True,
            "same_manifest_same_projection": True, "representative_tiers": ["curriculum", "rectangular", "generalization"],
            "g15_pass_claim": False,
        },
        "results": results,
        "summary": validate_m15_native_reset_evidence.expected_summary(results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    validate_m15_native_reset_evidence.validate(root, output, artifact_base=artifact_base)
    print(f"V2_M15_NATIVE_RESET_EVIDENCE=FROZEN output={output} sha256={validate_m15_native_reset_evidence.sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
