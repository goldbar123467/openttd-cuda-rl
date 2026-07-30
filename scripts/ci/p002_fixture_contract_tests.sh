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
Usage: p002_fixture_contract_tests.sh --tools-python ABSOLUTE_PATH
                                       [--work-root ABSOLUTE_PATH]
                                       [--schedule-seed INTEGER]
                                       [--keep-work]

Validates the committed PORT002A-frozen fixture manifest and canonical settings,
then runs all 32 pre-PORT003 PORT-002 contract tests offline: all 30 fixture and
settings cases plus save-bit and wrong-content identity preflight cases.
The committed save/manifest close only PORT002A. Without two-load projection,
native command/replay milestones, and isolation evidence it cannot close PORT002B.
EOF
}

TOOLS_PYTHON=''
WORK_ROOT=''
SCHEDULE_SEED=2002
KEEP_WORK=0
while (($# > 0)); do
    case "$1" in
        --tools-python)
            (($# >= 2)) || { printf 'ERROR: --tools-python requires a value\n' >&2; exit 64; }
            TOOLS_PYTHON=$2
            shift 2
            ;;
        --work-root)
            (($# >= 2)) || { printf 'ERROR: --work-root requires a value\n' >&2; exit 64; }
            WORK_ROOT=$2
            shift 2
            ;;
        --schedule-seed)
            (($# >= 2)) || { printf 'ERROR: --schedule-seed requires a value\n' >&2; exit 64; }
            SCHEDULE_SEED=$2
            shift 2
            ;;
        --keep-work)
            KEEP_WORK=1
            shift
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

[[ "${TOOLS_PYTHON}" == /* ]] || { printf 'ERROR: --tools-python must be absolute\n' >&2; exit 64; }
[[ -f "${TOOLS_PYTHON}" && -x "${TOOLS_PYTHON}" ]] || { printf 'ERROR: tools Python is not executable\n' >&2; exit 64; }
[[ "${SCHEDULE_SEED}" =~ ^-?[0-9]+$ ]] || { printf 'ERROR: --schedule-seed must be an integer\n' >&2; exit 64; }

if [[ -z "${WORK_ROOT}" ]]; then
    WORK_ROOT=$(mktemp -d -- /workspace/p002-contract-tests.XXXXXXXX)
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
        printf 'PORT-002 contract test work retained at %s\n' "${WORK_ROOT}" >&2
    fi
    exit "${return_code}"
}
trap cleanup EXIT

for command_name in bash find realpath timeout; do
    command -v -- "${command_name}" >/dev/null 2>&1 || {
        printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
        exit 69
    }
done

readonly VALIDATOR="${REPOSITORY_ROOT}/oracle/tests/port002/port002_contract.py"
readonly TESTS="${REPOSITORY_ROOT}/oracle/tests/port002/port002_contract_tests.py"
readonly SCHEMA="${REPOSITORY_ROOT}/oracle/manifests/schema/fixture.schema.json"
readonly FIXTURE_ROOT="${REPOSITORY_ROOT}/oracle/fixtures/road_freight_v1"

timeout --signal=TERM --kill-after=5s 30s "${TOOLS_PYTHON}" "${VALIDATOR}" \
    --schema "${SCHEMA}" \
    --settings "${FIXTURE_ROOT}/settings.normalized.json"
timeout --signal=TERM --kill-after=5s 30s "${TOOLS_PYTHON}" "${VALIDATOR}" \
    --schema "${SCHEMA}" \
    --manifest "${FIXTURE_ROOT}/fixture.manifest.json"
timeout --signal=TERM --kill-after=10s 180s "${TOOLS_PYTHON}" "${TESTS}" \
    --repository-root "${REPOSITORY_ROOT}" \
    --work-root "${WORK_ROOT}" \
    --schedule-seed "${SCHEDULE_SEED}"
