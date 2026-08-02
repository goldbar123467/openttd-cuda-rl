#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
python3 "$repo_root/scripts/v1/validate_m12_release_contract.py" \
  "$repo_root/config/v1/m12-release-contract.json" \
  "$repo_root/docs/project/schema/v1-m12-release-contract.schema.json"
PYTHONPATH="$repo_root/scripts/v1${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest tests.project.traceability.test_v1_m12_release
