#!/bin/sh
set -eu

repository_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
exec python3 "$repository_root/scripts/v1/validate_build_profiles.py" \
    --matrix "$repository_root/config/v1/build-profile-matrix.json" \
    --schema "$repository_root/docs/project/schema/v1-build-profile-matrix.schema.json"
