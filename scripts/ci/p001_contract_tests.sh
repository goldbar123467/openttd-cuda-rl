#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC
export PYTHONHASHSEED=0

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly SCRIPT_DIR
REPOSITORY_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)
readonly REPOSITORY_ROOT

usage() {
    cat <<'EOF'
Usage: p001_contract_tests.sh --tools-python ABSOLUTE_PATH
                              [--work-root ABSOLUTE_PATH]
                              [--schedule-seed INTEGER]
                              [--keep-work]

Runs all 61 mandatory PORT-001 contract tests without network access. Tests use
isolated Git worktrees, synthetic CMake/CTest projects, deterministic local
archives, and fake OpenTTD executables. No mandatory ID is skipped. A missing
required local tool or repository material is a test failure.

The default work root is a fresh directory below the system temporary directory.
--work-root must
name a non-existing or empty directory outside the repository and submodule.
The tools Python must be the hash-locked P0 environment containing jsonschema
and rfc8785; create it from tools/requirements-p0.txt before this offline test.
EOF
}

WORK_ROOT=''
KEEP_WORK=0
TOOLS_PYTHON=''
SCHEDULE_SEED=''
while (($# > 0)); do
    case "$1" in
        --work-root)
            (($# >= 2)) || { printf 'ERROR: --work-root requires a value\n' >&2; exit 64; }
            WORK_ROOT=$2
            shift 2
            ;;
        --keep-work)
            KEEP_WORK=1
            shift
            ;;
        --tools-python)
            (($# >= 2)) || { printf 'ERROR: --tools-python requires a value\n' >&2; exit 64; }
            TOOLS_PYTHON=$2
            shift 2
            ;;
        --schedule-seed)
            (($# >= 2)) || { printf 'ERROR: --schedule-seed requires a value\n' >&2; exit 64; }
            SCHEDULE_SEED=$2
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'ERROR: unknown argument: %s\n' "$1" >&2
            exit 64
            ;;
    esac
done

[[ "${TOOLS_PYTHON}" == /* ]] || { printf 'ERROR: --tools-python must be an absolute path\n' >&2; exit 64; }
[[ -x "${TOOLS_PYTHON}" && -f "${TOOLS_PYTHON}" ]] || { printf 'ERROR: --tools-python is not an executable regular file\n' >&2; exit 64; }
if [[ -n "${SCHEDULE_SEED}" && ! "${SCHEDULE_SEED}" =~ ^-?[0-9]+$ ]]; then
    printf 'ERROR: --schedule-seed must be an integer\n' >&2
    exit 64
fi

if [[ -z "${WORK_ROOT}" ]]; then
    WORK_ROOT=$(mktemp -d -- "${TMPDIR:-/tmp}/p001-contract-tests.XXXXXXXX")
    CREATED_WORK_ROOT=1
else
    [[ "${WORK_ROOT}" == /* ]] || { printf 'ERROR: --work-root must be absolute\n' >&2; exit 64; }
    WORK_ROOT=$(realpath -m -- "${WORK_ROOT}")
    case "${WORK_ROOT}" in
        /|/workspace|"${REPOSITORY_ROOT}"|"${REPOSITORY_ROOT}/"*|"${REPOSITORY_ROOT}/openttd-upstream"|"${REPOSITORY_ROOT}/openttd-upstream/"*)
            printf 'ERROR: unsafe --work-root: %s\n' "${WORK_ROOT}" >&2
            exit 64
            ;;
    esac
    if [[ -e "${WORK_ROOT}" ]]; then
        [[ -d "${WORK_ROOT}" && ! -L "${WORK_ROOT}" ]] || { printf 'ERROR: work root must be a directory\n' >&2; exit 64; }
        [[ -z "$(find "${WORK_ROOT}" -mindepth 1 -print -quit)" ]] || { printf 'ERROR: work root must be empty\n' >&2; exit 64; }
    else
        mkdir -p -- "${WORK_ROOT}"
    fi
    CREATED_WORK_ROOT=0
fi
readonly WORK_ROOT CREATED_WORK_ROOT

cleanup() {
    local return_code=$?
    if ((return_code == 0 && KEEP_WORK == 0 && CREATED_WORK_ROOT == 1)) && [[ -d "${WORK_ROOT}" && ! -L "${WORK_ROOT}" ]]; then
        find "${WORK_ROOT}" -mindepth 1 -depth -delete
        rmdir -- "${WORK_ROOT}"
    elif [[ -d "${WORK_ROOT}" ]]; then
        printf 'PORT-001 test work retained at %s\n' "${WORK_ROOT}" >&2
    fi
    exit "${return_code}"
}
trap cleanup EXIT

for command_name in bash cmake ctest git ninja python3 realpath shellcheck timeout; do
    command -v -- "${command_name}" >/dev/null 2>&1 || {
        printf 'ERROR: required PORT-001 test command not found: %s\n' "${command_name}" >&2
        exit 69
    }
done

declare -a harness_command=(
    "${TOOLS_PYTHON}"
    "${REPOSITORY_ROOT}/oracle/tests/port001/port001_contract_tests.py"
    --repository-root "${REPOSITORY_ROOT}"
    --work-root "${WORK_ROOT}"
    --tools-python "${TOOLS_PYTHON}"
)
if [[ -n "${SCHEDULE_SEED}" ]]; then
    harness_command+=(--schedule-seed "${SCHEDULE_SEED}")
fi
timeout --signal=TERM --kill-after=10s 900s "${harness_command[@]}"
