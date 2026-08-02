#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
python3 "$repo_root/scripts/v1/validate_m13_publication_contract.py" \
  "$repo_root/config/v1/m13-publication-contract.json" \
  "$repo_root/docs/project/schema/v1-m13-publication-contract.schema.json"
PYTHONPATH="$repo_root/scripts/v1${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m unittest tests.project.traceability.test_v1_m13_publication
