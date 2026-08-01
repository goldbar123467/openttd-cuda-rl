#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 --artifact-root /absolute/new/path --cache-root /absolute/path [--tools-python /absolute/path/to/python]" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
artifact_root=""
cache_root=""
tools_python="$(command -v python3)"

while (($#)); do
    case "$1" in
        --artifact-root)
            (($# >= 2)) || { usage; exit 2; }
            artifact_root="$2"
            shift 2
            ;;
        --cache-root)
            (($# >= 2)) || { usage; exit 2; }
            cache_root="$2"
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

[[ "$artifact_root" = /* && ! -e "$artifact_root" ]] || {
    echo "v1 toolchain probe: artifact root must be a new absolute path" >&2
    exit 2
}
[[ "$cache_root" = /* && -d "$cache_root" ]] || {
    echo "v1 toolchain probe: cache root must be an existing absolute directory" >&2
    exit 2
}
[[ "$tools_python" = /* && -x "$tools_python" ]] || {
    echo "v1 toolchain probe: tools Python must be an executable absolute path" >&2
    exit 2
}

install -d -m 700 "$artifact_root"

"$tools_python" "$repository_root/scripts/v1/run_toolchain_probe.py" \
    --root "$repository_root" \
    --artifact-root "$artifact_root" \
    --cache-root "$cache_root" \
    --lock "$repository_root/config/v1/dependency-lock.json" \
    --dependency-schema "$repository_root/docs/project/schema/v1-dependency-lock.schema.json" \
    --manifest-schema "$repository_root/docs/project/schema/v1-toolchain-probe-manifest.schema.json" \
    --python "$tools_python"
