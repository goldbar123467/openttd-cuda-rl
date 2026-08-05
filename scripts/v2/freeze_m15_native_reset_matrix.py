#!/usr/bin/env python3
"""Freeze a live complete M15 reset matrix as checked-in compact evidence."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import tempfile

from artifact_context import ArtifactContext, ArtifactContextError
import qualify_m15_native_reset
import run_m15_native_reset_matrix


def freeze(
    root: pathlib.Path,
    matrix: pathlib.Path,
    artifact_base: pathlib.Path,
    output: pathlib.Path,
) -> pathlib.Path:
    root, matrix = root.resolve(), matrix.resolve()
    artifact_base, output = artifact_base.resolve(), output.resolve()
    if output.exists() or output.is_symlink():
        raise run_m15_native_reset_matrix.M15NativeResetMatrixError(
            f"refusing to overwrite {output}"
        )
    run_m15_native_reset_matrix.validate(
        root,
        matrix,
        artifact_context=ArtifactContext.live(artifact_base),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output.parent,
            prefix=f".{output.name}.",
            delete=False,
        ) as stream:
            stream.write(matrix.read_bytes())
            temporary = pathlib.Path(stream.name)
        run_m15_native_reset_matrix.validate(
            root,
            temporary,
            artifact_context=ArtifactContext.offline(),
        )
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--matrix", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-base", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = freeze(args.root, args.matrix, args.artifact_base, args.output)
        print(f"V2_M15_NATIVE_RESET_MATRIX=FROZEN output={output} sha256={run_m15_native_reset_matrix.sha256_file(output)}")
        return 0
    except (
        run_m15_native_reset_matrix.M15NativeResetMatrixError,
        qualify_m15_native_reset.M15NativeResetError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_NATIVE_RESET_MATRIX=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
