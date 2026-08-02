#!/usr/bin/env python3
"""Freeze a live-validated M15 map matrix as the checked-in compact evidence index."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import run_m15_map_matrix


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-matrix", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-base", type=pathlib.Path, required=True)
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.root.resolve()
    output = (args.output or root / "config/v2/m15-map-evidence.json").resolve()
    try:
        run_m15_map_matrix.validate(
            root,
            args.artifact_matrix,
            artifact_base=args.artifact_base,
            openttd=args.openttd,
        )
        if output.exists() or output.is_symlink():
            raise run_m15_map_matrix.M15MapMatrixError(f"refusing to overwrite frozen map evidence: {output}")
        value = run_m15_map_matrix.load_json(args.artifact_matrix)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        frozen = run_m15_map_matrix.validate(root, output)
        print(
            f"V2_M15_MAP_EVIDENCE_FROZEN rectangles={frozen.rectangles} generated={frozen.generated} "
            f"preflight_rejected={frozen.preflight_rejected} output={output} sha256={run_m15_map_matrix.sha256_file(output)}"
        )
        return 0
    except (run_m15_map_matrix.M15MapMatrixError, OSError) as exc:
        print(f"V2_M15_MAP_EVIDENCE_FREEZE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
