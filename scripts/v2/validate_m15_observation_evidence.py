#!/usr/bin/env python3
"""Validate M15 observation evidence offline or against a relocated live tree."""

from __future__ import annotations

import argparse
import pathlib
import sys

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
)
import freeze_m15_observation_evidence as evidence
import qualify_m15_native_reset
import qualify_m15_observation


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    return evidence.required_live_inputs(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        summary = evidence.validate(
            args.root,
            args.config,
            args.schema,
            artifact_context=context,
        )
        print(
            "V2_M15_OBSERVATION_EVIDENCE=PASS "
            f"cases={summary.cases} passed={summary.passed} "
            f"max_rss_kib={summary.maximum_rss_kib} "
            f"live={str(summary.live).lower()}"
        )
        return 0
    except (
        evidence.M15ObservationEvidenceError,
        qualify_m15_observation.M15ObservationError,
        qualify_m15_native_reset.M15NativeResetError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_OBSERVATION_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
