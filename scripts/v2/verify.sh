#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "$script_dir/../.." && pwd -P)"
tools_python="$(command -v python3)"
tier="full"
artifact_root=""
tier_seen=0
python_seen=0
artifact_seen=0

usage() {
    cat <<EOF
usage: scripts/v2/verify.sh [--tier fast|contract|full]
                            [--tools-python /absolute/python]
                            [--artifact-root /absolute/openttd-rl-artifacts]
EOF
}

argument_error() {
    echo "v2 verify: $1" >&2
    usage >&2
    exit 2
}

while (($#)); do
    case "$1" in
        --help)
            usage
            exit 0
            ;;
        --tier)
            ((tier_seen == 0)) || argument_error "duplicate --tier"
            (($# >= 2)) || argument_error "missing value for --tier"
            case "$2" in
                fast|contract|full) tier="$2" ;;
                *) argument_error "tier must be one of: fast, contract, full" ;;
            esac
            tier_seen=1
            shift 2
            ;;
        --tools-python)
            ((python_seen == 0)) || argument_error "duplicate --tools-python"
            (($# >= 2)) || argument_error "missing value for --tools-python"
            tools_python="$2"
            python_seen=1
            shift 2
            ;;
        --artifact-root)
            ((artifact_seen == 0)) || argument_error "duplicate --artifact-root"
            (($# >= 2)) || argument_error "missing value for --artifact-root"
            artifact_root="$2"
            artifact_seen=1
            shift 2
            ;;
        *)
            argument_error "unknown argument: $1"
            ;;
    esac
done

[[ "$tools_python" = /* && -f "$tools_python" && -x "$tools_python" ]] || \
    argument_error "Python must be an executable absolute path"
if ((artifact_seen)); then
    [[ "$artifact_root" = /* ]] || argument_error "artifact root must be an absolute path"
    artifact_args=(--artifact-root "$artifact_root")
else
    artifact_args=()
fi

PYTHONPATH="$repository_root/scripts/v2" exec "$tools_python" \
    "$repository_root/scripts/v2/verify_driver.py" \
    --root "$repository_root" --tier "$tier" \
    --tools-python "$tools_python" "${artifact_args[@]}"
