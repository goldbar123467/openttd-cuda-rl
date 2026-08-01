#!/bin/sh
set -eu

if [ "$#" -ne 6 ] || [ "$1" != "--artifact-root" ] || [ "$3" != "--headless-root" ] || [ "$5" != "--playable-root" ]; then
    echo "usage: $0 --artifact-root /absolute/new/path --headless-root /absolute/accepted/root --playable-root /absolute/accepted/root" >&2
    exit 2
fi

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec python3 "$repository_root/scripts/v1/measure_runtime_resources.py" \
    --artifact-root "$2" \
    --headless-root "$4" \
    --playable-root "$6" \
    --plan "$repository_root/config/v1/resource-measurement-plan.json" \
    --plan-schema "$repository_root/docs/project/schema/v1-resource-measurement-plan.schema.json" \
    --report-schema "$repository_root/docs/project/schema/v1-resource-measurement-report.schema.json"
