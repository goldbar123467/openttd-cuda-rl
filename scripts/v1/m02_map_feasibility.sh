#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 --artifact-root /absolute/new/path --cache-root /absolute/path --reference-root /absolute/m01-playable-root [--tools-python /absolute/path] [--jobs N]" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
artifact_root=""
cache_root=""
reference_root=""
tools_python="$(command -v python3)"
jobs=4

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
        --reference-root)
            (($# >= 2)) || { usage; exit 2; }
            reference_root="$2"
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

[[ "$artifact_root" = /* && ! -e "$artifact_root" ]] || {
    echo "M02 feasibility: artifact root must be a new absolute path" >&2
    exit 2
}
[[ "$cache_root" = /* && -d "$cache_root" ]] || {
    echo "M02 feasibility: cache root must be an existing absolute directory" >&2
    exit 2
}
[[ "$reference_root" = /* && -d "$reference_root" ]] || {
    echo "M02 feasibility: reference root must be an existing absolute directory" >&2
    exit 2
}
[[ "$tools_python" = /* && -x "$tools_python" ]] || {
    echo "M02 feasibility: tools Python must be an executable absolute path" >&2
    exit 2
}
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || {
    echo "M02 feasibility: jobs must be a positive integer" >&2
    exit 2
}

install -d -m 700 "$artifact_root"

"$tools_python" "$repository_root/scripts/v1/run_m02_map_feasibility.py" \
    --root "$repository_root" \
    --artifact-root "$artifact_root" \
    --cache-root "$cache_root" \
    --reference-root "$reference_root" \
    --plan "$repository_root/config/v1/m02-map-feasibility-plan.json" \
    --plan-schema "$repository_root/docs/project/schema/v1-m02-map-feasibility-plan.schema.json" \
    --report-schema "$repository_root/docs/project/schema/v1-m02-map-feasibility-report.schema.json" \
    --jobs "$jobs"
