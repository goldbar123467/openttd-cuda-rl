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
Usage: port001_gate.sh --profile local-release
                       --artifact-root ABSOLUTE_PATH
                       --tools-python ABSOLUTE_VENV_PYTHON
                      [--parallel 1..64]

Runs the complete PORT-001 release closure from a clean, already-pushed branch:
the 61-case offline contract suite under frozen randomized scheduling and CTest
repeat-until-fail, followed by two fresh configure/build/99-test/install/smoke
roots, strict seven-axis comparison, binary-difference inspection, and canonical
evidence/gate emission. The artifact root must be absent or empty.

Dependency acquisition is separated from authoritative execution: each clean
root obtains the approved OpenGFX archive through fetch_opengfx.sh, verifies it
before extraction, and all later build/test/smoke stages use only local bytes.
EOF
    p0_show_common_help_note
}

PROFILE=''
ARTIFACT_ROOT=''
TOOLS_PYTHON=''
PARALLEL=''
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
        --profile)
            (($# >= 2)) || p0_usage_error '--profile requires a value'
            PROFILE=$2
            shift 2
            ;;
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --tools-python)
            (($# >= 2)) || p0_usage_error '--tools-python requires a value'
            TOOLS_PYTHON=$2
            shift 2
            ;;
        --parallel)
            (($# >= 2)) || p0_usage_error '--parallel requires a value'
            PARALLEL=$2
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

[[ "${PROFILE}" == local-release ]] || p0_usage_error 'PORT-001 closure requires --profile local-release'
p0_require_absolute_path "${ARTIFACT_ROOT}" '--artifact-root'
p0_require_absolute_path "${TOOLS_PYTHON}" '--tools-python'
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
[[ -x "${TOOLS_PYTHON}" && -f "${TOOLS_PYTHON}" ]] || p0_usage_error '--tools-python must be an executable regular file'
if [[ -e "${ARTIFACT_ROOT}" ]]; then
    [[ -d "${ARTIFACT_ROOT}" && ! -L "${ARTIFACT_ROOT}" ]] || p0_usage_error '--artifact-root must be a directory, not a link or file'
    [[ -z "$(find "${ARTIFACT_ROOT}" -mindepth 1 -print -quit)" ]] || p0_usage_error '--artifact-root must be empty'
else
    mkdir -p -- "${ARTIFACT_ROOT}"
fi

if [[ -z "${PARALLEL}" ]]; then
    processors=$(getconf _NPROCESSORS_ONLN)
    if ((processors > 16)); then
        PARALLEL=16
    else
        PARALLEL=${processors}
    fi
fi
[[ "${PARALLEL}" =~ ^[0-9]+$ ]] || p0_usage_error '--parallel must be an integer'
((PARALLEL >= 1 && PARALLEL <= 64)) || p0_usage_error '--parallel must be between 1 and 64'

export P0_PROFILE="${PROFILE}"
p0_initialize 'port001-gate' "${ARTIFACT_ROOT}" 'port001-gate.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/port001-gate.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in cmake ctest git getconf gitleaks jq python3 realpath sha256sum; do
    p0_require_command "${tool}"
done
for frozen_binary in /usr/bin/cmake /usr/bin/ctest /usr/bin/objcopy /usr/bin/readelf; do
    [[ -x "${frozen_binary}" && -f "${frozen_binary}" ]] || p0_die "required frozen binary is unavailable: ${frozen_binary}" 69
done

started_at=${P0_STARTED_AT}
branch=$(git -C "${P0_REPOSITORY_ROOT}" symbolic-ref --quiet --short HEAD || true)
[[ "${branch}" == 'port/p0-oracle-contract' ]] || p0_die "PORT-001 closure requires branch port/p0-oracle-contract; got ${branch:-detached}" 65
outer_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ -z "${outer_status}" ]] || p0_die 'PORT-001 authoritative reconstruction requires a clean outer worktree' 65
p0_require_commit "${P0_REPOSITORY_ROOT}/openttd-upstream" "${P0_EXPECTED_SUBMODULE_COMMIT}"
p0_require_clean_submodule "${P0_REPOSITORY_ROOT}/openttd-upstream"
outer_commit=$(git -C "${P0_REPOSITORY_ROOT}" rev-parse HEAD)
if remote_line=$(git -C "${P0_REPOSITORY_ROOT}" ls-remote --exit-code origin 'refs/heads/port/p0-oracle-contract'); then
    :
else
    remote_query_rc=$?
    p0_die 'unable to verify the authoritative branch directly against origin' "${remote_query_rc}"
fi
IFS=$'\t' read -r remote_commit remote_ref <<<"${remote_line}"
[[ "${remote_ref}" == 'refs/heads/port/p0-oracle-contract' && "${remote_commit}" =~ ^[0-9a-f]{40}$ ]] \
    || p0_die 'origin returned an invalid authoritative branch identity' 65
[[ "${outer_commit}" == "${remote_commit}" ]] || p0_die "local branch is not exactly pushed: local ${outer_commit}, remote ${remote_commit}" 65

p0_log INFO 'verifying the hash-locked Python distributions and complete frozen host/toolchain profile'
if "${TOOLS_PYTHON}" "${P0_REPOSITORY_ROOT}/tools/verify_host_profile.py" \
    --dependency-profile "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/dependencies-ubuntu-24.04.json" \
    --toolchain-profile "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/toolchain-linux-x86_64.json" \
    --include-python-distributions \
    --requirements-lock "${P0_REPOSITORY_ROOT}/tools/requirements-p0.txt" \
    --tools-python "${TOOLS_PYTHON}" \
    --output "${ARTIFACT_ROOT}/results/port001-host-profile.json" \
    >"${ARTIFACT_ROOT}/logs/port001-host-profile.stdout.log" \
    2>"${ARTIFACT_ROOT}/logs/port001-host-profile.stderr.log"; then
    :
else
    host_profile_rc=$?
    p0_die 'complete frozen host/toolchain profile verification failed' "${host_profile_rc}"
fi

p0_log INFO 'running full-repository secret scan with redacted output'
if gitleaks detect --source "${P0_REPOSITORY_ROOT}" --redact --exit-code 1 --no-banner --log-level error \
    >"${ARTIFACT_ROOT}/logs/port001-gitleaks.stdout.log" \
    2>"${ARTIFACT_ROOT}/logs/port001-gitleaks.stderr.log"; then
    :
else
    gitleaks_rc=$?
    p0_die 'gitleaks rejected the clean pushed source tree; redacted logs were retained' "${gitleaks_rc}"
fi

contract_build="${ARTIFACT_ROOT}/contract-build"
p0_safe_reset_dir "${contract_build}" "${ARTIFACT_ROOT}"
mkdir -p -- "${ARTIFACT_ROOT}/contract-tests"
declare -a contract_configure=(
    /usr/bin/cmake
    -S "${P0_REPOSITORY_ROOT}"
    -B "${contract_build}"
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    "-DP0_TOOLS_PYTHON=${TOOLS_PYTHON}"
)
declare -a contract_test=(
    /usr/bin/ctest
    --test-dir "${contract_build}"
    --output-on-failure
    --no-tests=error
    --schedule-random
    --repeat until-fail:3
    --timeout 900
    --output-junit "${ARTIFACT_ROOT}/contract-tests/p001-contract.junit.xml"
    -R '^p001_(contract|comparator)$'
)
p0_write_command_array "${ARTIFACT_ROOT}/commands/port001-contract-configure.json" "${contract_configure[@]}"
p0_write_command_array "${ARTIFACT_ROOT}/commands/port001-contract-ctest.json" "${contract_test[@]}"
if "${contract_configure[@]}" \
    >"${ARTIFACT_ROOT}/logs/port001-contract-configure.stdout.log" \
    2>"${ARTIFACT_ROOT}/logs/port001-contract-configure.stderr.log"; then
    :
else
    contract_configure_rc=$?
    p0_die 'PORT-001 contract harness configuration failed' "${contract_configure_rc}"
fi
p0_log INFO 'running the mandatory harness with randomized scheduling and repeat-until-fail:3'
if "${contract_test[@]}" \
    >"${ARTIFACT_ROOT}/contract-tests/p001-contract.log" \
    2>"${ARTIFACT_ROOT}/contract-tests/p001-contract.stderr.log"; then
    :
else
    contract_test_rc=$?
    p0_die 'randomized/repeated PORT-001 mandatory contract suite failed' "${contract_test_rc}"
fi
[[ -s "${ARTIFACT_ROOT}/contract-tests/p001-contract.junit.xml" ]] || p0_die 'CTest omitted mandatory-suite JUnit evidence' 70
contract_repeat_count=$(grep -Fc 'Start 1: p001_contract' "${ARTIFACT_ROOT}/contract-tests/p001-contract.log")
comparator_repeat_count=$(grep -Fc 'Start 2: p001_comparator' "${ARTIFACT_ROOT}/contract-tests/p001-contract.log")
((contract_repeat_count == 3 && comparator_repeat_count == 3)) \
    || p0_die "CTest repeat-until-fail evidence is incomplete: contract=${contract_repeat_count}, comparator=${comparator_repeat_count}" 70

run_clean_reference() {
    local run_root=$1
    local build_root="${run_root}/build"
    local install_root="${run_root}/install"
    mkdir -p -- "${run_root}"
    "${SCRIPT_DIR}/preflight.sh" \
        --mode edit \
        --artifact-root "${run_root}" \
        --content-root "${build_root}/baseset"
    "${SCRIPT_DIR}/configure_reference.sh" \
        --source-root "${P0_REPOSITORY_ROOT}/openttd-upstream" \
        --build-root "${build_root}" \
        --install-root "${install_root}" \
        --artifact-root "${run_root}"
    "${SCRIPT_DIR}/fetch_opengfx.sh" \
        --destination "${build_root}/baseset" \
        --artifact-root "${run_root}"
    "${SCRIPT_DIR}/build_reference.sh" \
        --build-root "${build_root}" \
        --install-root "${install_root}" \
        --artifact-root "${run_root}" \
        --configuration-manifest "${run_root}/manifests/configure-reference.json" \
        --parallel "${PARALLEL}"
    "${SCRIPT_DIR}/test_reference.sh" \
        --build-root "${build_root}" \
        --artifact-root "${run_root}" \
        --baseline-inventory "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/tests-relwithdebinfo.json"
    "${SCRIPT_DIR}/smoke_reference.sh" \
        --install-root "${install_root}" \
        --artifact-root "${run_root}" \
        --build-manifest "${run_root}/manifests/build-reference.json"
}

p0_log INFO 'starting clean reference reconstruction A'
run_clean_reference "${ARTIFACT_ROOT}/run-a"
p0_log INFO 'starting independent clean reference reconstruction B'
run_clean_reference "${ARTIFACT_ROOT}/run-b"

outer_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ -z "${outer_status}" ]] || p0_die 'authoritative reconstruction changed the outer worktree' 65
p0_require_clean_submodule "${P0_REPOSITORY_ROOT}/openttd-upstream"
if post_remote_line=$(git -C "${P0_REPOSITORY_ROOT}" ls-remote --exit-code origin 'refs/heads/port/p0-oracle-contract'); then
    :
else
    post_remote_query_rc=$?
    p0_die 'unable to reverify the authoritative branch directly against origin' "${post_remote_query_rc}"
fi
IFS=$'\t' read -r post_remote_commit post_remote_ref <<<"${post_remote_line}"
[[ "${post_remote_ref}" == 'refs/heads/port/p0-oracle-contract' && "${post_remote_commit}" =~ ^[0-9a-f]{40}$ ]] \
    || p0_die 'origin returned an invalid post-run branch identity' 65
[[ "${post_remote_commit}" == "${outer_commit}" ]] || p0_die 'remote branch changed during authoritative reconstruction' 65

finished_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
p0_log INFO 'comparing the seven required identities and inspecting binary differences'
if "${TOOLS_PYTHON}" "${P0_REPOSITORY_ROOT}/tools/compare_port001_runs.py" \
    --repository-root "${P0_REPOSITORY_ROOT}" \
    --artifact-root "${ARTIFACT_ROOT}" \
    --run-a "${ARTIFACT_ROOT}/run-a" \
    --run-b "${ARTIFACT_ROOT}/run-b" \
    --outer-commit "${outer_commit}" \
    --remote-commit "${post_remote_commit}" \
    --started-at "${started_at}" \
    --finished-at "${finished_at}" \
    --parallel "${PARALLEL}" \
    >"${ARTIFACT_ROOT}/logs/port001-comparator.stdout.log" \
    2>"${ARTIFACT_ROOT}/logs/port001-comparator.stderr.log"; then
    :
else
    comparator_rc=$?
    p0_die 'PORT-001 reconstruction comparison failed' "${comparator_rc}"
fi

evidence_file="${ARTIFACT_ROOT}/comparison/port001-evidence.json"
gate_file="${ARTIFACT_ROOT}/comparison/port001-gate-result.json"
"${TOOLS_PYTHON}" "${P0_REPOSITORY_ROOT}/tools/validate_manifest.py" \
    --schema "${ARTIFACT_ROOT}/schema/evidence.schema.json" \
    "${evidence_file}" \
    >"${ARTIFACT_ROOT}/logs/port001-evidence-validation.log"
"${TOOLS_PYTHON}" "${P0_REPOSITORY_ROOT}/tools/validate_manifest.py" \
    --schema "${ARTIFACT_ROOT}/schema/gate-result.schema.json" \
    "${gate_file}" \
    >"${ARTIFACT_ROOT}/logs/port001-gate-validation.log"
for baseline_file in \
    build-relwithdebinfo.json \
    dependencies-ubuntu-24.04.json \
    opengfx-8.0.json \
    openttd-source.json \
    tests-relwithdebinfo.json \
    toolchain-linux-x86_64.json; do
    declared_schema=$(jq -er '.["$schema"]' "${ARTIFACT_ROOT}/profile/${baseline_file}")
    schema_file=$(realpath -m -- "${ARTIFACT_ROOT}/profile/${declared_schema}")
    [[ -f "${schema_file}" ]] || p0_die "portable baseline schema reference is unresolved: ${baseline_file}" 70
    "${TOOLS_PYTHON}" "${P0_REPOSITORY_ROOT}/tools/validate_manifest.py" \
        --schema "${schema_file}" \
        --profile-lock "${ARTIFACT_ROOT}/profile/P0_PROFILE_LOCK.json" \
        "${ARTIFACT_ROOT}/profile/${baseline_file}" \
        >>"${ARTIFACT_ROOT}/logs/port001-portable-profile-validation.log"
done
jq -e '
    .gate_id == "PORT-001"
    and .profile == "local-release"
    and .status == "PASS"
    and (.checks | all(.status == "PASS"))
    and ([.checks[].id] | length == (unique | length))
    and ([.checks[].id] | sort) == [
        "BASELINE-SCHEMAS", "BINARY-ANALYSIS", "BRANCH-PUSH", "CLEAN-RUN-A", "CLEAN-RUN-B",
        "CONFIGURATION-IDENTITY", "HEADLESS-SMOKE-BEHAVIOR", "MANDATORY-TESTS", "OPENGFX-IDENTITY",
        "RUNTIME-VERSION-OUTPUT", "SOURCE-IDENTITY", "TEST-INVENTORY", "TEST-RESULTS"
    ]
    and (.open_counts | to_entries | all(.value == 0))
    and .branch_push.required
    and .branch_push.verified
    and (.branch_push.local_commit == .branch_push.remote_commit)
' \
    "${gate_file}" >/dev/null || p0_die 'schema-valid PORT-001 gate result does not close every mandatory count' 70

p0_finish 'PASS' 0 "PORT-001 passed from two clean roots at pushed commit ${outer_commit}"
