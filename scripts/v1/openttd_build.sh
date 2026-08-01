#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 --variant headless|playable --artifact-root /absolute/new/path --cache-root /absolute/path [--tools-python /absolute/path] [--jobs N]" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
variant=""
artifact_root=""
cache_root=""
tools_python="$(command -v python3)"
jobs=4

while (($#)); do
    case "$1" in
        --variant)
            (($# >= 2)) || { usage; exit 2; }
            variant="$2"
            shift 2
            ;;
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
        --jobs)
            (($# >= 2)) || { usage; exit 2; }
            jobs="$2"
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

[[ "$variant" = headless || "$variant" = playable ]] || {
    echo "v1 OpenTTD build: variant must be headless or playable" >&2
    exit 2
}
[[ "$artifact_root" = /* && ! -e "$artifact_root" ]] || {
    echo "v1 OpenTTD build: artifact root must be a new absolute path" >&2
    exit 2
}
[[ "$cache_root" = /* && -d "$cache_root" ]] || {
    echo "v1 OpenTTD build: cache root must be an existing absolute directory" >&2
    exit 2
}
[[ "$tools_python" = /* && -x "$tools_python" ]] || {
    echo "v1 OpenTTD build: tools Python must be an executable absolute path" >&2
    exit 2
}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || {
    echo "v1 OpenTTD build: jobs must be a positive integer" >&2
    exit 2
}

install -d -m 700 "$artifact_root"

"$tools_python" "$repository_root/scripts/v1/run_openttd_build.py" \
    --root "$repository_root" \
    --variant "$variant" \
    --artifact-root "$artifact_root" \
    --cache-root "$cache_root" \
    --lock "$repository_root/config/v1/openttd-build-input-lock.json" \
    --python "$tools_python" \
    --jobs "$jobs"
