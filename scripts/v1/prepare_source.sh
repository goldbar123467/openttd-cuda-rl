#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 --artifact-root /absolute/new/path [--tools-python /absolute/path/to/python]" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
tools_python="$(command -v python3)"
artifact_root=""

while (($#)); do
    case "$1" in
        --artifact-root)
            (($# >= 2)) || { usage; exit 2; }
            artifact_root="$2"
            shift 2
            ;;
        --tools-python)
            (($# >= 2)) || { usage; exit 2; }
            tools_python="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            exit 2
            ;;
    esac
done

[[ "$tools_python" = /* && -x "$tools_python" ]] || {
    echo "v1 source preparation: tools Python must be an executable absolute path" >&2
    exit 2
}
[[ "$artifact_root" = /* && ! -e "$artifact_root" ]] || {
    echo "v1 source preparation: artifact root must be a new absolute path" >&2
    exit 2
}

install -d -m 700 "$artifact_root"

"$tools_python" "$repository_root/scripts/v1/prepare_openttd_source.py" \
    --root "$repository_root" \
    --profile "$repository_root/config/v1/openttd-source-profile.json" \
    --profile-schema "$repository_root/docs/project/schema/v1-source-profile.schema.json" \
    --manifest-schema "$repository_root/docs/project/schema/v1-prepared-source-manifest.schema.json" \
    --output "$artifact_root/source" \
    --manifest "$artifact_root/prepared-source.json"
