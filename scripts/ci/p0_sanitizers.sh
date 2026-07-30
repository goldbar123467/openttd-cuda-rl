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

artifact_root=''
tools_python=''
while (($# > 0)); do
    case "$1" in
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            artifact_root=$2
            shift 2
            ;;
        --tools-python)
            (($# >= 2)) || p0_usage_error '--tools-python requires a value'
            tools_python=$2
            shift 2
            ;;
        *) p0_usage_error "unknown argument: $1" ;;
    esac
done

p0_require_absolute_path "${artifact_root}" '--artifact-root'
p0_require_absolute_path "${tools_python}" '--tools-python'
[[ -x "${tools_python}" ]] || p0_die '--tools-python must be executable' 64
artifact_root=$(p0_validate_generated_root "${artifact_root}")
mkdir -p -- "${artifact_root}"
build_root="${artifact_root}/clang-asan-ubsan-build"
p0_safe_reset_dir "${build_root}" "${artifact_root}"
before_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)

cmake -S "${P0_REPOSITORY_ROOT}" -B "${build_root}" -G Ninja \
    -DCMAKE_C_COMPILER=/usr/bin/clang-16 \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    '-DCMAKE_C_FLAGS_RELWITHDEBINFO=-O1 -g3 -DNDEBUG' \
    -DBUILD_TESTING=ON \
    -DP0_ENABLE_ASAN=ON \
    -DP0_ENABLE_UBSAN=ON \
    -DP0_TOOLS_PYTHON="${tools_python}" \
    >"${artifact_root}/configure.stdout.log" \
    2>"${artifact_root}/configure.stderr.log"
cmake --build "${build_root}" --parallel 2 \
    >"${artifact_root}/build.stdout.log" \
    2>"${artifact_root}/build.stderr.log"

export ASAN_OPTIONS='abort_on_error=1:check_initialization_order=1:detect_leaks=1:detect_stack_use_after_return=1:halt_on_error=1:strict_string_checks=1'
export UBSAN_OPTIONS='abort_on_error=1:halt_on_error=1:print_stacktrace=1'
export LSAN_OPTIONS='exitcode=23:print_suppressions=1:report_objects=1'
ctest --test-dir "${build_root}" -L p0 --output-on-failure --no-tests=error \
    --output-junit "${artifact_root}/sanitizers.junit.xml" \
    >"${artifact_root}/ctest.stdout.log" \
    2>"${artifact_root}/ctest.stderr.log"

if rg -n 'AddressSanitizer|LeakSanitizer|UndefinedBehaviorSanitizer|runtime error:' \
    "${artifact_root}" --glob '*.log'; then
    p0_die 'sanitizer diagnostic appeared in a passing command log' 65
fi

after_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ "${before_status}" == "${after_status}" ]] || p0_die 'sanitizer gate changed the source worktree' 70
printf '%s\n' 'P0_SANITIZERS=PASS'
