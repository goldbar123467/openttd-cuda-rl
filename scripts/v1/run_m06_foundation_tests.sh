#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

cd -- "$REPOSITORY_ROOT"
export PYTHONPATH="$REPOSITORY_ROOT/scripts/v1${PYTHONPATH:+:$PYTHONPATH}"
python3 "$REPOSITORY_ROOT/scripts/v1/validate_m06_reward_contract.py" \
  "$REPOSITORY_ROOT/config/v1/m06-reward-trajectory-contract.json" \
  "$REPOSITORY_ROOT/docs/project/schema/v1-m06-reward-trajectory-contract.schema.json"
python3 -m unittest \
  tests.project.traceability.test_v1_m06_reward_contract \
  tests.project.traceability.test_v1_m06_trajectory \
  tests.project.traceability.test_v1_m06_reward_native
