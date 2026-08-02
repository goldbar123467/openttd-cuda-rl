#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

cd -- "$REPOSITORY_ROOT"
export PYTHONPATH="$REPOSITORY_ROOT/scripts/v1${PYTHONPATH:+:$PYTHONPATH}"
python3 "$REPOSITORY_ROOT/scripts/v1/validate_m10_model_package_contract.py" \
  "$REPOSITORY_ROOT/config/v1/m10-model-package-contract.json" \
  "$REPOSITORY_ROOT/docs/project/schema/v1-m10-model-package-contract.schema.json"
python3 -m unittest tests.project.traceability.test_v1_m10_model_package
