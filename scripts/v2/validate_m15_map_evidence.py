#!/usr/bin/env python3
"""Validate M15 map evidence offline or against one relocated live tree."""

from __future__ import annotations

import argparse
import pathlib
import sys

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    add_artifact_root_argument,
)
import qualify_m15_native_map
import run_m15_map_matrix as matrix


def required_live_inputs(
    root: pathlib.Path,
) -> tuple[ArtifactRequirement | RoleRequirement, ...]:
    return (*matrix.required_live_inputs(root), *matrix.required_live_roles(root))


def required_live_roles(root: pathlib.Path) -> tuple[RoleRequirement, ...]:
    return matrix.required_live_roles(root)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    parser.add_argument("--openttd", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        live_inputs = None if args.artifact_root is None else (
            LiveInputManifest.load(args.artifact_root)
            if args.openttd is None
            else LiveInputManifest.bind(
                context, {"m14-openttd-executable": args.openttd}
            )
        )
        summary = matrix.validate(
            args.root,
            args.evidence,
            args.schema,
            artifact_context=context,
            live_inputs=live_inputs,
        )
        print(
            "V2_M15_MAP_EVIDENCE=PASS "
            f"rectangles={summary.rectangles} generated={summary.generated} "
            f"preflight_rejected={summary.preflight_rejected} "
            f"save_bytes={summary.save_bytes} max_rss_kib={summary.maximum_rss_kib} "
            f"live={str(summary.live_artifacts).lower()}"
        )
        return 0
    except (
        matrix.M15MapMatrixError,
        qualify_m15_native_map.M15MapQualificationError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_MAP_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
