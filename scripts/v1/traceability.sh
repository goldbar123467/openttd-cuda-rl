#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 [--tools-python /absolute/path/to/python]" >&2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
tools_python="$(command -v python3)"

while (($#)); do
    case "$1" in
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
    echo "v1 traceability: --tools-python must be an executable absolute path" >&2
    exit 2
}

"$tools_python" "$repository_root/scripts/v1/validate_traceability.py" \
    --root "$repository_root"

"$tools_python" "$repository_root/scripts/v1/lint_project_docs.py" \
    --root "$repository_root"

PYTHONPATH="$repository_root/scripts/v1" \
    "$tools_python" -m unittest discover \
    -s "$repository_root/tests/project/traceability" \
    -p 'test_*.py' \
    -v
