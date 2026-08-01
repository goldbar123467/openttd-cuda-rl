#!/bin/sh
set -eu

if [ "$#" -ne 10 ] || [ "$1" != "--artifact-root" ] || [ "$3" != "--dependency-cache" ] || [ "$5" != "--build-cache" ] || [ "$7" != "--headless-root" ] || [ "$9" != "--playable-root" ]; then
    echo "usage: $0 --artifact-root /absolute/new/path --dependency-cache /absolute/path --build-cache /absolute/path --headless-root /absolute/accepted/root --playable-root /absolute/accepted/root" >&2
    exit 2
fi

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
exec python3 "$repository_root/scripts/v1/generate_dependency_provenance.py" \
    --artifact-root "$2" \
    --dependency-cache "$4" \
    --build-cache "$6" \
    --headless-root "$8" \
    --playable-root "${10}" \
    --dependency-lock "$repository_root/config/v1/dependency-lock.json" \
    --build-lock "$repository_root/config/v1/openttd-build-input-lock.json" \
    --schema "$repository_root/docs/project/schema/v1-dependency-provenance-manifest.schema.json"
