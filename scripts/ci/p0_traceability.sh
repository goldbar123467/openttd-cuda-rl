#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck disable=SC1091
source "${script_dir}/../../oracle/runner/common.sh"

tools_python=''
while (($# > 0)); do
    case "$1" in
        --tools-python)
            (($# >= 2)) || p0_usage_error '--tools-python requires a value'
            tools_python=$2
            shift 2
            ;;
        *) p0_usage_error "unknown argument: $1" ;;
    esac
done

p0_require_absolute_path "${tools_python}" '--tools-python'
[[ -x "${tools_python}" ]] || p0_die '--tools-python must be executable' 64
"${tools_python}" "${P0_REPOSITORY_ROOT}/scripts/dev/validate_traceability.py" \
    --root "${P0_REPOSITORY_ROOT}"
PYTHONPATH="${P0_REPOSITORY_ROOT}/scripts/dev" \
    "${tools_python}" -m unittest -v test_validate_traceability
