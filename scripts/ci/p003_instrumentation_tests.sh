#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly SCRIPT_DIR
REPOSITORY_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)
readonly REPOSITORY_ROOT

usage() {
    cat <<'EOF'
Usage: p003_instrumentation_tests.sh --artifact-root ABSOLUTE_PATH
                                      --tools-python ABSOLUTE_EXECUTABLE
                                      [--foundation-only]
                                      [--keep-work]

Validates that the ordered instrumentation patch series applies and reverses
cleanly in disposable worktrees at the frozen OpenTTD commit. Foundation mode
passes once the implemented patches satisfy that contract. The normal PORT-003
gate remains fail-closed until command replay, all 757 authoritative fields,
determinism, and non-perturbation tests are implemented.
EOF
}

ARTIFACT_ROOT=''
TOOLS_PYTHON=''
FOUNDATION_ONLY=0
KEEP_WORK=0
while (($# > 0)); do
    case "$1" in
        --artifact-root)
            (($# >= 2)) || { printf 'ERROR: --artifact-root requires a value\n' >&2; exit 64; }
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --tools-python)
            (($# >= 2)) || { printf 'ERROR: --tools-python requires a value\n' >&2; exit 64; }
            TOOLS_PYTHON=$2
            shift 2
            ;;
        --foundation-only)
            FOUNDATION_ONLY=1
            shift
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

[[ "${ARTIFACT_ROOT}" == /* ]] || { printf 'ERROR: --artifact-root must be absolute\n' >&2; exit 64; }
[[ "${TOOLS_PYTHON}" == /* && -f "${TOOLS_PYTHON}" && -x "${TOOLS_PYTHON}" ]] || {
    printf 'ERROR: --tools-python must be an absolute executable\n' >&2
    exit 64
}
ARTIFACT_ROOT=$(realpath -m -- "${ARTIFACT_ROOT}")
case "${ARTIFACT_ROOT}" in
    /|/workspace|"${REPOSITORY_ROOT}"|"${REPOSITORY_ROOT}/"*)
        printf 'ERROR: unsafe --artifact-root: %s\n' "${ARTIFACT_ROOT}" >&2
        exit 64
        ;;
esac
[[ ! -L "${ARTIFACT_ROOT}" ]] || { printf 'ERROR: artifact root must not be a symlink\n' >&2; exit 64; }
mkdir -p -- "${ARTIFACT_ROOT}"
ARTIFACT_ROOT=$(cd -- "${ARTIFACT_ROOT}" && pwd -P)

for command_name in awk git grep mktemp realpath sha256sum; do
    command -v -- "${command_name}" >/dev/null 2>&1 || {
        printf 'ERROR: required command not found: %s\n' "${command_name}" >&2
        exit 69
    }
done

readonly SOURCE_ROOT="${REPOSITORY_ROOT}/openttd-upstream"
readonly EXPECTED_COMMIT='29f808ef0022064e6d9a83c8476d1e0f4686af86'
readonly CREATE_RUNNER="${REPOSITORY_ROOT}/oracle/runner/create_instrumented_worktree.sh"
readonly APPLY_RUNNER="${REPOSITORY_ROOT}/oracle/runner/apply_instrumentation.sh"
readonly SERIES_FILE="${REPOSITORY_ROOT}/oracle/instrumentation/patches/series"

RUN_ROOT=$(mktemp -d -- "${ARTIFACT_ROOT}/p003-foundation.XXXXXXXX")
readonly RUN_ROOT
WORKTREE="${RUN_ROOT}/worktrees/instrumented"
WRONG_WORKTREE="${RUN_ROOT}/worktrees/wrong-commit"
readonly WORKTREE WRONG_WORKTREE

# ShellCheck cannot see that EXIT invokes this function.
# shellcheck disable=SC2317
cleanup() {
    local return_code=$?
    trap - EXIT
    if ((KEEP_WORK == 0)); then
        if [[ -e "${WORKTREE}" ]]; then
            git -C "${SOURCE_ROOT}" worktree remove --force "${WORKTREE}" >/dev/null 2>&1 || true
        fi
        if [[ -e "${WRONG_WORKTREE}" ]]; then
            git -C "${SOURCE_ROOT}" worktree remove --force "${WRONG_WORKTREE}" >/dev/null 2>&1 || true
        fi
        git -C "${SOURCE_ROOT}" worktree prune >/dev/null 2>&1 || true
    else
        printf 'PORT-003 worktrees retained under %s\n' "${RUN_ROOT}" >&2
    fi
    exit "${return_code}"
}
trap cleanup EXIT

primary_status_before=$(git -C "${SOURCE_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ -z "${primary_status_before}" ]] || { printf 'ERROR: primary OpenTTD submodule is dirty\n' >&2; exit 65; }
[[ "$(git -C "${SOURCE_ROOT}" rev-parse HEAD)" == "${EXPECTED_COMMIT}" ]] || {
    printf 'ERROR: primary OpenTTD submodule is not at the frozen commit\n' >&2
    exit 65
}
[[ -x "${CREATE_RUNNER}" && -x "${APPLY_RUNNER}" ]] || {
    printf 'ERROR: instrumentation runners must be executable\n' >&2
    exit 66
}
[[ -s "${SERIES_FILE}" && ! -L "${SERIES_FILE}" ]] || {
    printf 'ERROR: instrumentation series is missing, empty, or linked\n' >&2
    exit 66
}
printf '%s  series\n' "$(sha256sum -- "${SERIES_FILE}" | awk '{print $1}')" \
    >"${RUN_ROOT}/patch-manifest.sha256"
while IFS= read -r patch_name; do
    patch_path="${REPOSITORY_ROOT}/oracle/instrumentation/patches/${patch_name}"
    [[ -f "${patch_path}" && ! -L "${patch_path}" ]] || {
        printf 'ERROR: series patch is missing or linked: %s\n' "${patch_name}" >&2
        exit 66
    }
    printf '%s  %s\n' "$(sha256sum -- "${patch_path}" | awk '{print $1}')" "${patch_name}" \
        >>"${RUN_ROOT}/patch-manifest.sha256"
done <"${SERIES_FILE}"

"${CREATE_RUNNER}" --artifact-root "${RUN_ROOT}" --worktree "${WORKTREE}"
"${APPLY_RUNNER}" --artifact-root "${RUN_ROOT}" --worktree "${WORKTREE}"

for expected_path in \
    cmake/Options.cmake \
    src/CMakeLists.txt \
    src/p0_trace_journal.cpp \
    src/p0_trace_journal.h \
    src/p0_trace_sink.cpp \
    src/p0_trace_sink.h \
    src/tests/CMakeLists.txt \
    src/tests/p0_trace_journal.cpp \
    src/tests/p0_trace_sink.cpp; do
    [[ -e "${WORKTREE}/${expected_path}" && ! -L "${WORKTREE}/${expected_path}" ]] || {
        printf 'ERROR: applied instrumentation path is missing or linked: %s\n' "${expected_path}" >&2
        exit 1
    }
done
grep -Fq 'OPTION_P0_ORACLE_TRACE' "${WORKTREE}/cmake/Options.cmake" || {
    printf 'ERROR: trace build option was not applied\n' >&2
    exit 1
}
grep -Fq 'P0 trace sink writes canonical little-endian primitives and closes a durable journal' \
    "${WORKTREE}/src/tests/p0_trace_sink.cpp" || {
    printf 'ERROR: trace sink unit test was not applied\n' >&2
    exit 1
}
grep -Fq 'P0 trace journal writes a durable partial tape for the C17 finalizer' \
    "${WORKTREE}/src/tests/p0_trace_journal.cpp" || {
    printf 'ERROR: trace journal unit test was not applied\n' >&2
    exit 1
}

set +e
"${APPLY_RUNNER}" --artifact-root "${RUN_ROOT}" --worktree "${WORKTREE}" \
    >"${RUN_ROOT}/double-apply.stdout.log" 2>"${RUN_ROOT}/double-apply.stderr.log"
double_apply_rc=$?
set -e
[[ ${double_apply_rc} -eq 65 ]] || {
    printf 'ERROR: second instrumentation apply returned %d instead of 65\n' "${double_apply_rc}" >&2
    exit 1
}
grep -Fq 'requires a clean pinned worktree' "${RUN_ROOT}/double-apply.stderr.log" || {
    printf 'ERROR: second instrumentation apply did not explain the clean-worktree requirement\n' >&2
    exit 1
}

"${APPLY_RUNNER}" --artifact-root "${RUN_ROOT}" --worktree "${WORKTREE}" --reverse
[[ -z "$(git -C "${WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] || {
    printf 'ERROR: patch reversal did not restore a clean worktree\n' >&2
    exit 1
}

set +e
"${APPLY_RUNNER}" --artifact-root "${RUN_ROOT}" --worktree "${WORKTREE}" --reverse \
    >"${RUN_ROOT}/double-reverse.stdout.log" 2>"${RUN_ROOT}/double-reverse.stderr.log"
double_reverse_rc=$?
set -e
[[ ${double_reverse_rc} -eq 65 ]] || {
    printf 'ERROR: second instrumentation reverse returned %d instead of 65\n' "${double_reverse_rc}" >&2
    exit 1
}
grep -Fq 'reverse requires an applied series' "${RUN_ROOT}/double-reverse.stderr.log" || {
    printf 'ERROR: second instrumentation reverse did not explain the applied-series requirement\n' >&2
    exit 1
}

mkdir -p -- "$(dirname -- "${WRONG_WORKTREE}")"
git -C "${SOURCE_ROOT}" worktree add --detach "${WRONG_WORKTREE}" "${EXPECTED_COMMIT}^" \
    >"${RUN_ROOT}/wrong-worktree.stdout.log" 2>"${RUN_ROOT}/wrong-worktree.stderr.log"
set +e
"${APPLY_RUNNER}" --artifact-root "${RUN_ROOT}" --worktree "${WRONG_WORKTREE}" \
    >"${RUN_ROOT}/wrong-apply.stdout.log" 2>"${RUN_ROOT}/wrong-apply.stderr.log"
wrong_apply_rc=$?
set -e
[[ ${wrong_apply_rc} -eq 65 ]] || {
    printf 'ERROR: wrong-commit apply returned %d instead of 65\n' "${wrong_apply_rc}" >&2
    exit 1
}
grep -Fq 'commit mismatch' "${RUN_ROOT}/wrong-apply.stderr.log" || {
    printf 'ERROR: wrong-commit apply did not report the commit mismatch\n' >&2
    exit 1
}
[[ -z "$(git -C "${WRONG_WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] || {
    printf 'ERROR: rejected wrong-commit worktree was modified\n' >&2
    exit 1
}

primary_status_after=$(git -C "${SOURCE_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ "${primary_status_after}" == "${primary_status_before}" ]] || {
    printf 'ERROR: instrumentation tests modified the primary OpenTTD submodule\n' >&2
    exit 1
}

"${TOOLS_PYTHON}" -m py_compile \
    "${REPOSITORY_ROOT}/scripts/dev/command_input_v1.py" \
    "${REPOSITORY_ROOT}/oracle/tests/port003/test_command_input_v1.py"
PYTHONPATH="${REPOSITORY_ROOT}" "${TOOLS_PYTHON}" -m unittest -v \
    oracle.tests.port003.test_command_input_v1 \
    >"${RUN_ROOT}/command-input-tests.stdout.log" \
    2>"${RUN_ROOT}/command-input-tests.stderr.log"

instrumentation_sha256=$(sha256sum -- "${RUN_ROOT}/patch-manifest.sha256" | awk '{print $1}')
printf 'instrumentation_sha256=%s\ncommit=%s\nfoundation=PASS\n' \
    "${instrumentation_sha256}" "${EXPECTED_COMMIT}" >"${RUN_ROOT}/foundation-result.txt"
printf '%s\n' 'PORT003_FOUNDATION=PASS command_input_tests=PASS'

if ((FOUNDATION_ONLY == 1)); then
    exit 0
fi

printf '%s\n' \
    'PORT003=IN_PROGRESS: command replay, 757-field projection, runtime determinism, and non-perturbation remain mandatory' >&2
exit 1
