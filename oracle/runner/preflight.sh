#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly SCRIPT_DIR
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

usage() {
    cat <<'EOF'
Usage: preflight.sh --mode read-only|edit --artifact-root ABSOLUTE_PATH
                    --content-root ABSOLUTE_PATH

read-only permits a detached CI checkout. edit requires a named branch other
than main. Missing verified OpenGFX content is recorded as an approved
acquisition need; an existing but drifted content file is a hard failure.
The documented free-space floor is 10 GiB (10485760 KiB).
EOF
    p0_show_common_help_note
}

MODE=''
ARTIFACT_ROOT=''
CONTENT_ROOT=''
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
        --mode)
            (($# >= 2)) || p0_usage_error '--mode requires a value'
            MODE=$2
            shift 2
            ;;
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --content-root)
            (($# >= 2)) || p0_usage_error '--content-root requires a value'
            CONTENT_ROOT=$2
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            p0_usage_error "unknown argument: $1"
            ;;
    esac
done

[[ "${MODE}" == read-only || "${MODE}" == edit ]] || p0_usage_error '--mode must be read-only or edit'
p0_require_absolute_path "${ARTIFACT_ROOT}" '--artifact-root'
p0_require_absolute_path "${CONTENT_ROOT}" '--content-root'
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
CONTENT_ROOT=$(p0_realpath "${CONTENT_ROOT}")
p0_assert_under_root "${CONTENT_ROOT}" "${ARTIFACT_ROOT}" no
p0_initialize 'preflight' "${ARTIFACT_ROOT}" 'preflight.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/preflight.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"

p0_log INFO 'checking repository identity and immutable source pin'
[[ "$(git -C "${P0_REPOSITORY_ROOT}" rev-parse --show-toplevel)" == "${P0_REPOSITORY_ROOT}" ]] || p0_die 'runner repository-root discovery disagrees with Git' 65
git -C "${P0_REPOSITORY_ROOT}" merge-base --is-ancestor "${P0_EXPECTED_BASE_COMMIT}" HEAD || p0_die "outer repository is not descended from ${P0_EXPECTED_BASE_COMMIT}" 65

outer_remote=$(git -C "${P0_REPOSITORY_ROOT}" remote get-url origin)
if [[ "${outer_remote}" != "${P0_EXPECTED_OUTER_SSH_URL}" && "${outer_remote}" != "${P0_EXPECTED_OUTER_HTTPS_URL}" ]]; then
    p0_die "unexpected outer origin URL: ${outer_remote}" 65
fi

branch=$(git -C "${P0_REPOSITORY_ROOT}" symbolic-ref --quiet --short HEAD || true)
if [[ "${MODE}" == edit ]]; then
    [[ -n "${branch}" ]] || p0_die 'edit mode is forbidden on a detached commit' 65
    [[ "${branch}" != main ]] || p0_die 'edit mode is forbidden on main' 65
fi

submodule_path="${P0_REPOSITORY_ROOT}/openttd-upstream"
submodule_line=$(git -C "${P0_REPOSITORY_ROOT}" submodule status --recursive -- openttd-upstream || true)
[[ -n "${submodule_line}" ]] || p0_die 'openttd-upstream submodule is missing; run: git submodule update --init --recursive' 66
[[ "${submodule_line:0:1}" != '-' ]] || p0_die 'openttd-upstream is uninitialized; run: git submodule update --init --recursive' 66
[[ "${submodule_line:0:1}" != '+' && "${submodule_line:0:1}" != 'U' ]] || p0_die "openttd-upstream submodule worktree differs from the recorded pin: ${submodule_line}" 65

declared_submodule_url=$(git -C "${P0_REPOSITORY_ROOT}" config -f .gitmodules --get submodule.openttd-upstream.url)
[[ "${declared_submodule_url}" == "${P0_EXPECTED_SUBMODULE_URL}" ]] || p0_die "modified submodule URL in .gitmodules: ${declared_submodule_url}" 65
p0_require_sha256 "${P0_REPOSITORY_ROOT}/.gitmodules" "${P0_EXPECTED_GITMODULES_SHA256}" '.gitmodules'
actual_submodule_url=$(git -C "${submodule_path}" remote get-url origin)
[[ "${actual_submodule_url}" == "${P0_EXPECTED_SUBMODULE_URL}" ]] || p0_die "modified submodule origin URL: ${actual_submodule_url}" 65
p0_require_commit "${submodule_path}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
p0_require_clean_submodule "${submodule_path}"

p0_log INFO 'checking staged-path policy without reading staged file contents'
staged_paths=$(git -C "${P0_REPOSITORY_ROOT}" diff --cached --name-only --diff-filter=ACMR || true)
if [[ -n "${staged_paths}" ]]; then
    while IFS= read -r staged_path; do
        case "${staged_path}" in
            *.env|*.pem|*.key|*credentials*|*token*|*id_ed25519*|*hosts.yml*)
                p0_die "credential-like staged path is forbidden: ${staged_path}" 65
                ;;
            */CMakeCache.txt|CMakeCache.txt|*/compile_commands.json|compile_commands.json|build/*|*/build/*|build-p0-*|*/build-p0-*|.p0-artifacts/*|*/.p0-artifacts/*|*.profraw|*.profdata|perf.data|*/perf.data|crash-*|*/crash-*|timeout-*|*/timeout-*|oom-*|*/oom-*|*/fuzz-artifacts/*|*/fuzz-corpus/*)
                p0_die "generated build artifact is staged: ${staged_path}" 65
                ;;
        esac
    done <<<"${staged_paths}"
fi

p0_log INFO 'checking required tools and Ubuntu 24.04 profile minimums'
for tool in git cmake ctest ninja gcc g++ python3 curl unzip zipinfo sha256sum jq realpath find df awk sed grep ldd shellcheck gitleaks dpkg dpkg-query; do
    p0_require_command "${tool}"
done

if [[ -n "${staged_paths}" ]]; then
    p0_log INFO 'scanning staged content with redacted gitleaks output'
    if gitleaks protect --source "${P0_REPOSITORY_ROOT}" --staged --redact --exit-code 1 --no-banner --log-level error \
        >"${ARTIFACT_ROOT}/logs/preflight.gitleaks.stdout.log" \
        2>"${ARTIFACT_ROOT}/logs/preflight.gitleaks.stderr.log"; then
        gitleaks_rc=0
    else
        gitleaks_rc=$?
    fi
    ((gitleaks_rc == 0)) || p0_die 'gitleaks rejected staged content; redacted logs were retained' 65
fi

git_version=$(git --version | sed -E 's/^git version ([0-9]+\.[0-9]+\.[0-9]+).*/\1/')
cmake_version=$(cmake --version | sed -n -E '1s/^cmake version ([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')
ctest_version=$(ctest --version | sed -n -E '1s/^ctest version ([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')
ninja_version=$(ninja --version | sed -n -E '1s/^([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')
gcc_version=$(gcc -dumpfullversion -dumpversion)
gxx_version=$(g++ -dumpfullversion -dumpversion)
python_version=$(python3 -c 'import platform; print(platform.python_version())')
shellcheck_version=$(shellcheck --version | sed -n -E 's/^version: ([0-9]+\.[0-9]+\.[0-9]+)$/\1/p')

[[ -n "${git_version}" && -n "${cmake_version}" && -n "${ctest_version}" && -n "${ninja_version}" && -n "${shellcheck_version}" ]] || p0_die 'unable to parse one or more required tool versions' 69
p0_require_minimum_version git "${git_version}" '2.43.0'
p0_require_minimum_version cmake "${cmake_version}" '3.28.0'
p0_require_minimum_version ctest "${ctest_version}" '3.28.0'
p0_require_minimum_version ninja "${ninja_version}" '1.11.0'
p0_require_minimum_version gcc "${gcc_version}" '13.0.0'
p0_require_minimum_version g++ "${gxx_version}" '13.0.0'
p0_require_minimum_version python3 "${python_version}" '3.12.0'
p0_require_minimum_version shellcheck "${shellcheck_version}" '0.9.0'

toolchain_profile="${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/toolchain-linux-x86_64.json"
p0_json_validate "${toolchain_profile}"
while IFS=$'\t' read -r tool_name actual_version; do
    expected_version=$(jq -er --arg name "${tool_name}" '.tools[] | select(.name == $name) | .version' "${toolchain_profile}") \
        || p0_die "frozen toolchain profile omits ${tool_name}" 70
    [[ "${actual_version}" == "${expected_version}" ]] \
        || p0_die "exact ${tool_name} version drift: expected ${expected_version}, got ${actual_version}" 65
done <<EOF
git	${git_version}
cmake	${cmake_version}
ctest	${ctest_version}
ninja	${ninja_version}
gcc	${gcc_version}
g++	${gxx_version}
python3	${python_version}
EOF

dependency_profile="${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/dependencies-ubuntu-24.04.json"
host_profile_verifier="${P0_REPOSITORY_ROOT}/tools/verify_host_profile.py"
[[ -f "${host_profile_verifier}" && ! -L "${host_profile_verifier}" ]] || p0_die 'host-profile verifier is missing' 66
p0_log INFO 'verifying exact Ubuntu platform and dpkg dependency identities'
if python3 "${host_profile_verifier}" \
    --dependency-profile "${dependency_profile}" \
    --toolchain-profile "${toolchain_profile}" \
    --output "${ARTIFACT_ROOT}/results/preflight-host-profile.json" \
    >"${ARTIFACT_ROOT}/logs/preflight.host-profile.stdout.log" \
    2>"${ARTIFACT_ROOT}/logs/preflight.host-profile.stderr.log"; then
    :
else
    host_profile_rc=$?
    p0_die 'frozen host/dependency profile verification failed; retained log names the drift' "${host_profile_rc}"
fi
p0_json_validate "${ARTIFACT_ROOT}/results/preflight-host-profile.json"

p0_log INFO 'checking artifact-root safety, free space, and credential-file names'
mkdir -p -- "${ARTIFACT_ROOT}" "${CONTENT_ROOT}"
writable_probe=$(mktemp -- "${ARTIFACT_ROOT}/.writable.XXXXXXXX")
p0_assert_under_root "${writable_probe}" "${ARTIFACT_ROOT}" no
rm -- "${writable_probe}"
available_kib=$(df -Pk -- "${ARTIFACT_ROOT}" | awk 'NR == 2 {print $4}')
[[ "${available_kib}" =~ ^[0-9]+$ ]] || p0_die 'unable to determine available artifact-root disk space' 74
((available_kib >= P0_MIN_DISK_KIB)) || p0_die "artifact root has ${available_kib} KiB free; ${P0_MIN_DISK_KIB} KiB required" 74

while IFS= read -r suspicious_path; do
    [[ -z "${suspicious_path}" ]] && continue
    p0_die "credential-like file is forbidden under artifact root: ${suspicious_path}" 65
done < <(find "${ARTIFACT_ROOT}" -type f \( -name '*.pem' -o -name '*.key' -o -name '*.env' -o -name 'id_*' -o -iname '*credential*' -o -iname '*token*' -o -name 'hosts.yml' \) -print)

[[ "${LC_ALL}" == 'C.UTF-8' && "${LANG}" == 'C.UTF-8' && "${TZ}" == UTC ]] || p0_die 'locale or timezone normalization was lost' 70

content_state='ACQUISITION_REQUIRED'
content_sha256=''
content_file="${CONTENT_ROOT}/${P0_OPENGFX_INSTALLED_NAME}"
if [[ -e "${content_file}" ]]; then
    p0_require_sha256 "${content_file}" "${P0_OPENGFX_INSTALLED_SHA256}" 'installed OpenGFX content'
    content_sha256=$(p0_sha256_file "${content_file}")
    content_state='VERIFIED'
fi

python3 - "${ARTIFACT_ROOT}/results/preflight-details.json" \
    "${MODE}" "${branch}" "${outer_remote}" "${P0_EXPECTED_SUBMODULE_COMMIT}" \
    "${available_kib}" "${content_state}" "${content_sha256}" \
    "${git_version}" "${cmake_version}" "${ctest_version}" "${ninja_version}" \
    "${gcc_version}" "${gxx_version}" "${python_version}" "${shellcheck_version}" \
    "${ARTIFACT_ROOT}" "${CONTENT_ROOT}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
value = {
    "authoritative": {
        "content": {"name": "OpenGFX", "sha256": sys.argv[8] or None, "state": sys.argv[7], "version": "8.0"},
        "mode": sys.argv[2],
        "source_commit": sys.argv[5],
        "tool_versions": {
            "cmake": sys.argv[10], "ctest": sys.argv[11], "gcc": sys.argv[13],
            "gxx": sys.argv[14], "git": sys.argv[9], "ninja": sys.argv[12],
            "python3": sys.argv[15], "shellcheck": sys.argv[16],
        },
    },
    "diagnostics": {
        "artifact_root": sys.argv[17], "branch": sys.argv[3],
        "content_root": sys.argv[18], "free_disk_kib": int(sys.argv[6]),
        "outer_remote": sys.argv[4],
    },
    "status": "PASS",
}
path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

p0_finish 'PASS' 0 "preflight passed; OpenGFX state: ${content_state}"
