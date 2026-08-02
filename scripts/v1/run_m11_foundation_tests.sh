#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPOSITORY_ROOT"
export PYTHONPATH="$REPOSITORY_ROOT/scripts/v1${PYTHONPATH:+:$PYTHONPATH}"

python3 scripts/v1/validate_m11_playback_contract.py \
  config/v1/m11-playback-contract.json \
  docs/project/schema/v1-m11-playback-contract.schema.json
python3 -m unittest tests.project.traceability.test_v1_m11_playback
