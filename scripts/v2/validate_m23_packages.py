#!/usr/bin/env python3
"""Independently validate an M23 checkpoint/deployment package output root."""

from __future__ import annotations

import argparse
import pathlib
import sys

import m23_package
import validate_m23_release_contract as contract_validator


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--package-root", type=pathlib.Path, required=True)
    arguments = parser.parse_args()
    try:
        report = m23_package.validate_output_root(arguments.root, arguments.package_root)
        print("V2_M23_PACKAGES=PASS checkpoints=" + str(len(report["checkpoint_packages"])) +
              " models=" + str(len(report["deployment_packages"])))
        return 0
    except (m23_package.M23PackageError, contract_validator.M23ContractError, OSError, RuntimeError, ValueError) as exc:
        print(f"V2_M23_PACKAGES=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
