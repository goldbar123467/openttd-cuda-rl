#!/bin/sh
set -eu

if [ "$#" -ne 4 ] || [ "$1" != "--artifact-root" ] || [ "$3" != "--artifact-store" ]; then
    echo "usage: $0 --artifact-root /absolute/new/path --artifact-store /absolute/path" >&2
    exit 2
fi

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec python3 "$repository_root/scripts/v1/audit_g01.py" \
    --root "$repository_root" \
    --artifact-root "$2" \
    --artifact-store "$4" \
    --evidence-index "$repository_root/config/v1/g01-evidence-index.json" \
    --profile-matrix "$repository_root/config/v1/build-profile-matrix.json" \
    --profile-schema "$repository_root/docs/project/schema/v1-build-profile-matrix.schema.json" \
    --resource-schema "$repository_root/docs/project/schema/v1-resource-measurement-report.schema.json" \
    --provenance-schema "$repository_root/docs/project/schema/v1-dependency-provenance-manifest.schema.json" \
    --report-schema "$repository_root/docs/project/schema/v1-g01-audit-report.schema.json"
