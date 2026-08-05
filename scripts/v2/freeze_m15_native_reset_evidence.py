#!/usr/bin/env python3
"""Freeze retained live M15 reset artifacts into a compact checked-in matrix."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile

from artifact_context import ArtifactContext, ArtifactContextError
import qualify_m15_native_reset
import validate_m15_native_reset_evidence


def freeze(
    root: pathlib.Path,
    artifact_base: pathlib.Path,
    output: pathlib.Path,
) -> pathlib.Path:
    root, artifact_base, output = root.resolve(), artifact_base.resolve(), output.resolve()
    validate_m15_native_reset_evidence.require(
        artifact_base.is_dir() and not artifact_base.is_symlink(),
        "M15 native reset artifact set is missing or a symlink",
    )
    validate_m15_native_reset_evidence.require(
        artifact_base.name == validate_m15_native_reset_evidence.LOGICAL_ARTIFACT_SET,
        "M15 native reset artifact set name drifted",
    )
    if output.exists() or output.is_symlink():
        raise validate_m15_native_reset_evidence.M15NativeResetEvidenceError(
            f"refusing to overwrite {output}"
        )
    source = validate_m15_native_reset_evidence.load_json(root / qualify_m15_native_reset.SOURCE)
    recorded = validate_m15_native_reset_evidence.load_json(
        root / validate_m15_native_reset_evidence.EVIDENCE
    )
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
        "artifact_base_hint": recorded["artifact_base_hint"],
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
    temporary: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            delete=False,
        ) as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
            temporary = pathlib.Path(stream.name)
        validate_m15_native_reset_evidence.validate(
            root,
            temporary,
            artifact_context=ArtifactContext.live(artifact_base.parent),
        )
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-base", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = freeze(args.root, args.artifact_base, args.output)
        print(f"V2_M15_NATIVE_RESET_EVIDENCE=FROZEN output={output} sha256={validate_m15_native_reset_evidence.sha256_file(output)}")
        return 0
    except (
        validate_m15_native_reset_evidence.M15NativeResetEvidenceError,
        qualify_m15_native_reset.M15NativeResetError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_NATIVE_RESET_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
