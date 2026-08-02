#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPOSITORY_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)

cd -- "$REPOSITORY_ROOT"
export PYTHONPATH="$REPOSITORY_ROOT/scripts/v1${PYTHONPATH:+:$PYTHONPATH}"
python3 "$REPOSITORY_ROOT/scripts/v1/validate_m08_architecture_contract.py" \
    "$REPOSITORY_ROOT/config/v1/m08-architecture-cuda-contract.json" \
    "$REPOSITORY_ROOT/docs/project/schema/v1-m08-architecture-cuda-contract.schema.json"
python3 -m unittest tests.project.traceability.test_v1_m08_architecture_cuda

evidence_variables=(
    M08_CUDA_REPORT
    M08_CPU_SMOKE_REPORT
    M08_CUDA_SMOKE_REPORT
    M08_LIVE_MANIFEST
)
provided=0
for variable in "${evidence_variables[@]}"; do
    [[ -z ${!variable:-} ]] || ((provided += 1))
done
if ((provided != 0 && provided != ${#evidence_variables[@]})); then
    echo "all M08 evidence variables must be supplied together" >&2
    exit 2
fi
if ((provided > 0)); then
    python3 "$REPOSITORY_ROOT/scripts/v1/validate_m08_cuda_report.py" \
        "$M08_CUDA_REPORT" \
        "$REPOSITORY_ROOT/docs/project/schema/v1-m08-cuda-gate-report.schema.json"
    python3 "$REPOSITORY_ROOT/scripts/v1/validate_m08_architecture_smoke.py" \
        --cpu "$M08_CPU_SMOKE_REPORT" \
        --cuda "$M08_CUDA_SMOKE_REPORT" \
        --schema "$REPOSITORY_ROOT/docs/project/schema/v1-m08-architecture-smoke.schema.json"
    python3 "$REPOSITORY_ROOT/scripts/v1/validate_m08_live_architectures.py" \
        "$M08_LIVE_MANIFEST" \
        "$REPOSITORY_ROOT/docs/project/schema/v1-m08-live-architectures.schema.json"
fi
