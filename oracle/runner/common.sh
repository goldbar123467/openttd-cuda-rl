#!/usr/bin/env bash
# shellcheck disable=SC2034
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

# Shared, fail-closed primitives for the P0 oracle runners. This file is sourced;
# it is not a user-facing command.

# Constants are intentionally consumed by scripts that source this library.
readonly P0_EXPECTED_BASE_COMMIT='58895696c8a75eda2fac2ae553654ba4398f5cda'
readonly P0_EXPECTED_SUBMODULE_COMMIT='29f808ef0022064e6d9a83c8476d1e0f4686af86'
readonly P0_EXPECTED_SUBMODULE_URL='https://github.com/OpenTTD/OpenTTD.git'
readonly P0_EXPECTED_OUTER_SSH_URL='git@github.com:goldbar123467/openttd-cuda-rl.git'
readonly P0_EXPECTED_OUTER_HTTPS_URL='https://github.com/goldbar123467/openttd-cuda-rl.git'
readonly P0_EXPECTED_GITMODULES_SHA256='326fef5383bcf7cc8b5c8a2522dca8a86acdcc653968ae2d5306b111ea49e04b'
readonly P0_OPENGFX_VERSION='8.0'
readonly P0_OPENGFX_ARCHIVE_NAME='opengfx-8.0-all.zip'
readonly P0_OPENGFX_ARCHIVE_URL='https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip'
readonly P0_OPENGFX_ARCHIVE_SHA256='43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be'
readonly P0_OPENGFX_INSTALLED_NAME='opengfx-8.0.tar'
readonly P0_OPENGFX_INSTALLED_SHA256='9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c'
readonly P0_EXPECTED_OPENTTD_VERSION='OpenTTD 20260729--g29f808ef00'
readonly P0_EXPECTED_TEST_COUNT=99
readonly P0_MIN_DISK_KIB=10485760
readonly P0_SOURCE_DATE_EPOCH=1785314342

P0_RUNNER_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly P0_RUNNER_DIR
P0_REPOSITORY_ROOT=$(cd -- "${P0_RUNNER_DIR}/../.." && pwd -P)
readonly P0_REPOSITORY_ROOT

P0_STAGE='uninitialized'
P0_RESULT_FILE=''
P0_RESULT_FINALIZED=0
P0_STARTED_AT=''
P0_STARTED_EPOCH=0
P0_LOG_FILE=''
declare -ag P0_SENSITIVE_VALUES=()

p0_usage_error() {
    printf 'ERROR: %s\n' "$*" >&2
    return 64
}

p0_register_sensitive() {
    local value
    for value in "$@"; do
        if [[ -n "${value}" ]]; then
            P0_SENSITIVE_VALUES+=("${value}")
        fi
    done
}

p0_redact() {
    local value=${1-}
    local sensitive
    for sensitive in "${P0_SENSITIVE_VALUES[@]}"; do
        value=${value//"${sensitive}"/'<redacted>'}
    done
    printf '%s' "${value}"
}

p0_log() {
    local level=$1
    shift
    local message timestamp line
    message=$(p0_redact "$*")
    timestamp=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    line="${timestamp} [${level}] [${P0_STAGE}] ${message}"
    printf '%s\n' "${line}" >&2
    if [[ -n "${P0_LOG_FILE}" ]]; then
        printf '%s\n' "${line}" >>"${P0_LOG_FILE}"
    fi
}

p0_die() {
    local message=$1
    local code=${2:-1}
    p0_log ERROR "${message}"
    if [[ -n "${P0_RESULT_FILE}" && ${P0_RESULT_FINALIZED} -eq 0 ]]; then
        p0_emit_result "${P0_RESULT_FILE}" 'FAIL' "${code}" "${message}"
        P0_RESULT_FINALIZED=1
    fi
    exit "${code}"
}

p0_require_command() {
    local command_name=$1
    command -v -- "${command_name}" >/dev/null 2>&1 || p0_die "required command not found: ${command_name}" 69
}

p0_set_deterministic_environment() {
    export LC_ALL='C.UTF-8'
    export LANG='C.UTF-8'
    export TZ='UTC'
    export PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    if [[ "${P0_TEST_MODE:-0}" == 1 && -n "${P0_TEST_TOOL_DIR:-}" ]]; then
        [[ "${P0_TEST_TOOL_DIR}" == /* && -d "${P0_TEST_TOOL_DIR}" && ! -L "${P0_TEST_TOOL_DIR}" ]] \
            || p0_die 'P0_TEST_TOOL_DIR must be an absolute, non-symlink directory' 64
        export PATH="${P0_TEST_TOOL_DIR}:${PATH}"
    fi
    export PYTHONHASHSEED='0'
    export SOURCE_DATE_EPOCH="${P0_SOURCE_DATE_EPOCH}"
    export P0_PROFILE="${P0_PROFILE:-local-release}"
    [[ "${P0_PROFILE}" == local-release || "${P0_PROFILE}" == ci-smoke ]] || p0_die "unsupported P0_PROFILE: ${P0_PROFILE}" 64
    local variable
    for variable in \
        AR CC CXX NM OBJCOPY RANLIB STRIP \
        CFLAGS CPPFLAGS CXXFLAGS LDFLAGS LDLIBS \
        CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET CMAKE_PREFIX_PATH \
        COMPILER_PATH CPATH CTEST_PARALLEL_LEVEL CTEST_OUTPUT_ON_FAILURE CTEST_PROGRESS_OUTPUT \
        C_INCLUDE_PATH CPLUS_INCLUDE_PATH DESTDIR GCC_EXEC_PREFIX LD_AUDIT LD_LIBRARY_PATH \
        LD_PRELOAD LIBRARY_PATH MAKEFLAGS NINJA_STATUS PKG_CONFIG_LIBDIR PKG_CONFIG_PATH \
        PKG_CONFIG_SYSROOT_DIR PYTHONHOME PYTHONPATH; do
        if [[ -n "${!variable-}" ]]; then
            p0_log INFO "clearing inherited behavior-affecting environment variable: ${variable}"
            unset "${variable}"
        fi
    done
    umask 022
}

p0_realpath() {
    local path=$1
    p0_require_command realpath
    realpath -m -- "${path}"
}

p0_require_absolute_path() {
    local path=$1
    local label=$2
    [[ -n "${path}" ]] || p0_die "${label} must not be empty" 64
    [[ "${path}" == /* ]] || p0_die "${label} must be an absolute path: ${path}" 64
}

p0_validate_generated_root() {
    local root=$1
    local resolved
    p0_require_absolute_path "${root}" 'generated artifact root'
    resolved=$(p0_realpath "${root}")
    case "${resolved}" in
        /|/workspace|"${P0_REPOSITORY_ROOT}"|"${P0_REPOSITORY_ROOT}/"*|"${P0_REPOSITORY_ROOT}/openttd-upstream")
            p0_die "unsafe generated artifact root: ${resolved}" 64
            ;;
    esac
    printf '%s\n' "${resolved}"
}

p0_assert_under_root() {
    local target=$1
    local root=$2
    local allow_equal=${3:-no}
    local resolved_target resolved_root
    resolved_target=$(p0_realpath "${target}")
    resolved_root=$(p0_realpath "${root}")
    if [[ "${resolved_target}" == "${resolved_root}" ]]; then
        [[ "${allow_equal}" == yes ]] || p0_die "target must be a proper descendant of the generated root: ${resolved_target}" 64
        return 0
    fi
    [[ "${resolved_target}" == "${resolved_root}/"* ]] || p0_die "target escapes generated root: ${resolved_target}" 64
}

p0_safe_reset_dir() {
    local target=$1
    local root=$2
    p0_assert_under_root "${target}" "${root}" no
    if [[ -L "${target}" ]]; then
        p0_die "refusing to reset symlinked directory: ${target}" 64
    fi
    if [[ -e "${target}" && ! -d "${target}" ]]; then
        p0_die "expected a directory: ${target}" 64
    fi
    mkdir -p -- "${target}"
    find "${target}" -mindepth 1 -depth -delete
}

p0_safe_remove_tree() {
    local target=$1
    local root=$2
    p0_assert_under_root "${target}" "${root}" no
    [[ ! -L "${target}" ]] || p0_die "refusing to remove symlinked directory: ${target}" 64
    if [[ -d "${target}" ]]; then
        find "${target}" -mindepth 1 -depth -delete
        rmdir -- "${target}"
    elif [[ -e "${target}" ]]; then
        p0_die "refusing tree removal for non-directory: ${target}" 64
    fi
}

p0_make_temp_dir() {
    local root=$1
    local label=$2
    local temp_root
    [[ "${label}" =~ ^[a-z0-9-]+$ ]] || p0_die "invalid temporary-directory label: ${label}" 64
    root=$(p0_validate_generated_root "${root}")
    temp_root="${root}/tmp"
    mkdir -p -- "${temp_root}"
    mktemp -d -- "${temp_root}/${label}.XXXXXXXX"
}

p0_sha256_file() {
    local path=$1
    [[ -f "${path}" && ! -L "${path}" ]] || p0_die "cannot hash missing, non-regular, or symlinked file: ${path}" 66
    sha256sum -- "${path}" | awk '{print $1}'
}

p0_require_sha256() {
    local path=$1
    local expected=$2
    local label=$3
    local actual
    [[ "${expected}" =~ ^[0-9a-f]{64}$ ]] || p0_die "invalid frozen SHA-256 for ${label}" 70
    actual=$(p0_sha256_file "${path}")
    [[ "${actual}" == "${expected}" ]] || p0_die "${label} SHA-256 mismatch: expected ${expected}, got ${actual}" 65
}

p0_json_validate() {
    local path=$1
    p0_require_command python3
    python3 - "${path}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = path.read_bytes()
if data.startswith(b"\xef\xbb\xbf"):
    raise SystemExit("JSON must not contain a UTF-8 byte-order mark")
try:
    text = data.decode("utf-8")
except UnicodeDecodeError as exc:
    raise SystemExit(f"JSON is not UTF-8: {exc}") from exc

def reject_duplicate(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result

try:
    json.loads(text, object_pairs_hook=reject_duplicate)
except (ValueError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid JSON: {exc}") from exc
PY
}

p0_json_canonicalize() {
    local input=$1
    local output=$2
    p0_json_validate "${input}"
    python3 - "${input}" "${output}" <<'PY'
import json
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])

def reject_duplicate(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result

value = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate)

# P0 manifests deliberately prohibit floats. This encoder is therefore the
# integer-only RFC 8785 subset: UTF-16 property ordering, ECMAScript-compatible
# string escaping, no whitespace, and I-JSON safe integers.
def encode(item):
    if item is None:
        return "null"
    if item is True:
        return "true"
    if item is False:
        return "false"
    if isinstance(item, int):
        if not -(2**53 - 1) <= item <= 2**53 - 1:
            raise ValueError("integer is outside the I-JSON exact range")
        return str(item)
    if isinstance(item, float):
        raise ValueError("floating-point values are outside the P0 canonical JSON subset")
    if isinstance(item, str):
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    if isinstance(item, list):
        return "[" + ",".join(encode(child) for child in item) + "]"
    if isinstance(item, dict):
        for key in item:
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
        keys = sorted(item, key=lambda key: key.encode("utf-16be"))
        return "{" + ",".join(encode(key) + ":" + encode(item[key]) for key in keys) + "}"
    raise ValueError(f"unsupported JSON value: {type(item).__name__}")

encoded = encode(value)
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_bytes(encoded.encode("utf-8"))
PY
}

p0_json_canonicalize_in_place() {
    local path=$1
    local generated_root=$2
    local temp_path
    p0_assert_under_root "${path}" "${generated_root}" no
    [[ -f "${path}" && ! -L "${path}" ]] || p0_die "cannot canonicalize missing, non-regular, or symlinked JSON: ${path}" 66
    temp_path=$(mktemp -- "$(dirname -- "${path}")/.canonical.XXXXXXXX")
    p0_assert_under_root "${temp_path}" "${generated_root}" no
    if p0_json_canonicalize "${path}" "${temp_path}"; then
        mv -- "${temp_path}" "${path}"
    else
        local return_code=$?
        rm -f -- "${temp_path}"
        p0_die "failed to canonicalize generated JSON: ${path}" "${return_code}"
    fi
}

p0_require_canonical_json() {
    local path=$1
    local generated_root=$2
    local temp_path
    p0_require_command cmp
    p0_assert_under_root "${path}" "${generated_root}" no
    [[ -f "${path}" && ! -L "${path}" ]] || p0_die "canonical JSON input is missing, non-regular, or symlinked: ${path}" 66
    temp_path=$(mktemp -- "$(dirname -- "${path}")/.canonical-check.XXXXXXXX")
    p0_assert_under_root "${temp_path}" "${generated_root}" no
    if ! p0_json_canonicalize "${path}" "${temp_path}"; then
        rm -f -- "${temp_path}"
        p0_die "invalid canonical JSON input: ${path}" 65
    fi
    if ! cmp -s -- "${path}" "${temp_path}"; then
        rm -f -- "${temp_path}"
        p0_die "JSON input is not in canonical byte form: ${path}" 65
    fi
    rm -- "${temp_path}"
}

p0_require_commit() {
    local repository=$1
    local expected=$2
    local actual
    [[ -d "${repository}" ]] || p0_die "repository directory is missing: ${repository}" 66
    git -C "${repository}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || p0_die "not a Git worktree: ${repository}" 65
    actual=$(git -C "${repository}" rev-parse HEAD)
    [[ "${actual}" == "${expected}" ]] || p0_die "commit mismatch for ${repository}: expected ${expected}, got ${actual}" 65
}

p0_require_clean_submodule() {
    local repository=$1
    local changes
    changes=$(git -C "${repository}" status --porcelain=v1 --untracked-files=all)
    if [[ -n "${changes}" ]]; then
        p0_log ERROR "dirty submodule paths follow (contents are intentionally omitted)"
        printf '%s\n' "${changes}" | sed -E 's/^.. //' >&2
        p0_die "submodule must be clean: ${repository}" 65
    fi
}

p0_version_ge() {
    local actual=$1
    local minimum=$2
    [[ "$(printf '%s\n%s\n' "${minimum}" "${actual}" | sort -V | head -n 1)" == "${minimum}" ]]
}

p0_require_minimum_version() {
    local tool=$1
    local actual=$2
    local minimum=$3
    p0_version_ge "${actual}" "${minimum}" || p0_die "${tool} ${actual} is below required minimum ${minimum}" 69
}

p0_write_command_array() {
    local output=$1
    shift
    [[ ${#} -gt 0 ]] || p0_die 'cannot record an empty command array' 70
    python3 - "${output}" "$@" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(sys.argv[2:], ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}

p0_emit_result() {
    local output=$1
    local status=$2
    local return_code=$3
    local message=$4
    local finished_at finished_epoch duration
    [[ "${status}" == PASS || "${status}" == FAIL || "${status}" == SKIP ]] || return 70
    finished_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    finished_epoch=$(date -u +%s)
    duration=$((finished_epoch - P0_STARTED_EPOCH))
    mkdir -p -- "$(dirname -- "${output}")"
    python3 - "${output}" "${P0_STAGE}" "${status}" "${return_code}" "${message}" "${P0_STARTED_AT}" "${finished_at}" "${duration}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
value = {
    "diagnostics": {
        "duration_seconds": int(sys.argv[8]),
        "finished_at": sys.argv[7],
        "started_at": sys.argv[6],
    },
    "message": sys.argv[5],
    "return_code": int(sys.argv[4]),
    "stage": sys.argv[2],
    "status": sys.argv[3],
}
path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}

p0_finish() {
    local status=$1
    local return_code=$2
    local message=$3
    p0_emit_result "${P0_RESULT_FILE}" "${status}" "${return_code}" "${message}"
    P0_RESULT_FINALIZED=1
    p0_log INFO "${message}"
}

p0_error_trap() {
    local return_code=$1
    local line=$2
    trap - ERR
    set +e
    if [[ ${P0_RESULT_FINALIZED} -eq 0 && -n "${P0_RESULT_FILE}" ]]; then
        p0_emit_result "${P0_RESULT_FILE}" 'FAIL' "${return_code}" "unexpected failure at script line ${line}"
        P0_RESULT_FINALIZED=1
    fi
    p0_log ERROR "unexpected failure at script line ${line} (exit ${return_code})"
    exit "${return_code}"
}

p0_initialize() {
    local stage=$1
    local artifact_root=$2
    local result_name=$3
    artifact_root=$(p0_validate_generated_root "${artifact_root}")
    mkdir -p -- "${artifact_root}/logs" "${artifact_root}/results"
    P0_STAGE=${stage}
    P0_STARTED_AT=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    P0_STARTED_EPOCH=$(date -u +%s)
    P0_LOG_FILE="${artifact_root}/logs/${stage}.log"
    P0_RESULT_FILE="${artifact_root}/results/${result_name}"
    : >"${P0_LOG_FILE}"
    trap 'p0_error_trap "$?" "${LINENO}"' ERR
    p0_set_deterministic_environment
}

p0_require_result_pass() {
    local path=$1
    p0_json_validate "${path}"
    python3 - "${path}" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("status") != "PASS" or value.get("return_code") != 0:
    raise SystemExit("required predecessor result is not PASS")
PY
}

p0_show_common_help_note() {
    cat <<'EOF'
All paths must be absolute. Generated build, install, content, log, and temporary
paths must be proper descendants of --artifact-root. Scripts never rely on the
caller's current working directory.
EOF
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'common.sh is a sourced library, not a standalone command.\n' >&2
    exit 64
fi
