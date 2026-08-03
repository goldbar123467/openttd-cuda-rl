#!/usr/bin/env python3
"""Independently validate an M23 source-integrated equivalence artifact."""

from __future__ import annotations

import argparse
import pathlib
import sys

import m23_ingame
import m23_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--package-root", type=pathlib.Path, required=True)
    parser.add_argument("--golden", type=pathlib.Path, required=True)
    parser.add_argument("--native-report", type=pathlib.Path, required=True)
    parser.add_argument("--standalone-report", type=pathlib.Path, required=True)
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--source-tree", required=True)
    args = parser.parse_args()
    try:
        value = m23_ingame.validate_artifact(
            args.root, args.artifact_root, args.package_root, args.golden,
            args.native_report, args.standalone_report, args.openttd, args.source_tree,
        )
        print(
            f"V2_M23_INGAME_ARTIFACT=PASS runtime_results={value['runtime_results']['total']} "
            f"rows={value['rows_per_runtime']} tree={value['source_result_tree']}",
        )
        return 0
    except (m23_ingame.M23InGameError, m23_package.M23PackageError,
            OSError, ValueError, KeyError, TypeError) as exc:
        print(f"V2_M23_INGAME_ARTIFACT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
