#!/usr/bin/env python3
"""Validate M15 native reset matrix evidence offline or from a relocated live tree."""

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
import qualify_m15_native_reset
import run_m15_native_reset_matrix as matrix


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    return matrix.required_live_inputs(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        summary = matrix.validate(
            args.root,
            args.evidence,
            args.schema,
            artifact_context=context,
        )
        print(
            "V2_M15_NATIVE_RESET_MATRIX=PASS "
            f"rectangles={summary.rectangles} generated={summary.generated} "
            f"preflight_rejected={summary.preflight_rejected} "
            f"max_rss_kib={summary.maximum_rss_kib} "
            f"live={str(summary.live).lower()}"
        )
        return 0
    except (
        matrix.M15NativeResetMatrixError,
        qualify_m15_native_reset.M15NativeResetError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_NATIVE_RESET_MATRIX=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
