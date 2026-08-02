#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

cd -- "$REPOSITORY_ROOT"
export PYTHONPATH="$REPOSITORY_ROOT/scripts/v1${PYTHONPATH:+:$PYTHONPATH}"
python3 "$REPOSITORY_ROOT/scripts/v1/validate_m07_ppo_contract.py" \
    "$REPOSITORY_ROOT/config/v1/m07-ppo-contract.json" \
    "$REPOSITORY_ROOT/docs/project/schema/v1-m07-ppo-contract.schema.json"
python3 "$REPOSITORY_ROOT/scripts/v1/validate_m07_metrics.py" \
    --schema "$REPOSITORY_ROOT/docs/project/schema/v1-m07-metric-event.schema.json" \
    --sources "$REPOSITORY_ROOT/config/v1/m07-metric-sources.json"
python3 -m unittest tests.project.traceability.test_v1_m07_ppo
