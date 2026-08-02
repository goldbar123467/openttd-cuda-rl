#!/usr/bin/env python3
"""Freeze a live complete M15 reset matrix as checked-in compact evidence."""

from __future__ import annotations

import argparse
import pathlib

import run_m15_native_reset_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--matrix", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-base", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output.exists() or output.is_symlink():
        raise SystemExit(f"refusing to overwrite {output}")
    run_m15_native_reset_matrix.validate(root, args.matrix, artifact_base=args.artifact_base)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(args.matrix.resolve().read_bytes())
    run_m15_native_reset_matrix.validate(root, output)
    print(f"V2_M15_NATIVE_RESET_MATRIX=FROZEN output={output} sha256={run_m15_native_reset_matrix.sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
