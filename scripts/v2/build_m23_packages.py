#!/usr/bin/env python3
"""Build both exact M23 checkpoint packages and deterministic deployment packages."""

from __future__ import annotations

import argparse
import pathlib
import sys

import m23_package
import validate_m23_release_contract as contract_validator


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--monolithic-checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--specialist-checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--export-root", type=pathlib.Path, required=True)
    parser.add_argument("--golden-binary", type=pathlib.Path, required=True)
    parser.add_argument("--equivalence-report", type=pathlib.Path, required=True)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        report = m23_package.build_all(
            arguments.root,
            {
                contract_validator.ARCHITECTURES[0]: arguments.monolithic_checkpoint,
                contract_validator.ARCHITECTURES[1]: arguments.specialist_checkpoint,
            },
            arguments.export_root,
            arguments.golden_binary,
            arguments.equivalence_report,
            arguments.output_root,
        )
        print("V2_M23_PACKAGE_BUILD=PASS " + " ".join(
            f"{item['architecture_id']}={item['package_id']}" for item in report["deployment_packages"]
        ))
        return 0
    except (m23_package.M23PackageError, contract_validator.M23ContractError, OSError, RuntimeError, ValueError) as exc:
        print(f"V2_M23_PACKAGE_BUILD=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
