#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(cd -- "$script_dir/../.." && pwd -P)
artifact_root=""
tools_python=""

while (($# > 0)); do
  case "$1" in
    --artifact-root) artifact_root=$2; shift 2 ;;
    --tools-python) tools_python=$2; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 64 ;;
  esac
done
if [[ -z "$artifact_root" || "$artifact_root" != /* ]]; then
  printf '%s\n' '--artifact-root must be an absolute dedicated directory' >&2
  exit 64
fi
if [[ -z "$tools_python" || "$tools_python" != /* || ! -x "$tools_python" ]]; then
  printf '%s\n' '--tools-python must be an absolute executable' >&2
  exit 64
fi
artifact_root=$(realpath -m -- "$artifact_root")
case "$artifact_root" in
  /|/workspace|"$repo_root"|"$repo_root"/*)
    printf 'unsafe artifact root: %s\n' "$artifact_root" >&2; exit 64 ;;
esac
mkdir -p -- "$artifact_root"
artifact_root=$(cd -- "$artifact_root" && pwd -P)
case "$artifact_root" in
  /|/workspace|"$repo_root"|"$repo_root"/*)
    printf 'unsafe artifact root: %s\n' "$artifact_root" >&2; exit 64 ;;
esac
if [[ -n "$(find "$artifact_root" -type l -print -quit)" ]]; then
  printf '%s\n' 'artifact root must not contain symlinks' >&2
  exit 64
fi
tracked_before=$(git -C "$repo_root" diff --binary HEAD -- . | sha256sum)

{
  printf 'gcc-version=%s\n' "$(/usr/bin/gcc-13 -dumpfullversion)"
  printf 'clang-version=%s\n' "$(/usr/bin/clang-16 -dumpversion)"
  printf '%s\n' \
    'gcc-debug Debug -O0' \
    'gcc-release Release -O2' \
    'clang-debug Debug -O0' \
    'clang-release Release -O2' \
    'clang-asan-ubsan RelWithDebInfo -O1 ASan UBSan frame-pointers' \
    'clang-coverage Debug source-based-coverage' \
    'clang-fuzz RelWithDebInfo libFuzzer ASan UBSan'
} >"$artifact_root/profile-manifest.txt"

configure_build_test() {
  local name=$1
  local compiler=$2
  local build_type=$3
  shift 3
  local build="$artifact_root/$name"
  cmake -S "$repo_root" -B "$build" -G Ninja \
    -DCMAKE_C_COMPILER="$compiler" \
    -DCMAKE_BUILD_TYPE="$build_type" \
    -DBUILD_TESTING=ON \
    -DP0_TOOLS_PYTHON="$tools_python" "$@" \
    >"$artifact_root/$name-configure.log" 2>&1
  cmake --build "$build" --parallel 2 >"$artifact_root/$name-build.log" 2>&1
  ctest --test-dir "$build" -L port004 --output-on-failure --no-tests=error \
    --output-junit "$artifact_root/$name-ctest.xml" \
    >"$artifact_root/$name-ctest.log" 2>&1
}

configure_build_test gcc-debug /usr/bin/gcc-13 Debug
configure_build_test gcc-release /usr/bin/gcc-13 Release \
  '-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG'
configure_build_test clang-debug /usr/bin/clang-16 Debug
configure_build_test clang-release /usr/bin/clang-16 Release \
  '-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG'
ASAN_OPTIONS='abort_on_error=1:detect_leaks=1:detect_stack_use_after_return=1:halt_on_error=1:strict_string_checks=1' \
UBSAN_OPTIONS='abort_on_error=1:halt_on_error=1:print_stacktrace=1' \
  configure_build_test clang-asan-ubsan /usr/bin/clang-16 RelWithDebInfo \
    '-DCMAKE_C_FLAGS_RELWITHDEBINFO=-O1 -g -DNDEBUG' \
    -DP0_ENABLE_ASAN=ON -DP0_ENABLE_UBSAN=ON

"$repo_root/scripts/ci/p004_coverage.sh" \
  --artifact-root "$artifact_root/clang-coverage" \
  --tools-python "$tools_python"
"$repo_root/parity/tests/fuzz/run_campaign.sh" \
  --artifact-root "$artifact_root/clang-fuzz" \
  --tools-python "$tools_python"

/usr/bin/g++ -std=c++17 -Wall -Wextra -Wpedantic -Wconversion \
  -Wsign-conversion -Wshadow -Werror \
  -I"$repo_root/parity/include" \
  "$repo_root/parity/tests/unit/abi_cpp.cpp" \
  "$artifact_root/gcc-debug/libotrl_tape.a" -lcrypto \
  -o "$artifact_root/gcc-debug/p004_abi_cpp"
"$artifact_root/gcc-debug/p004_abi_cpp"

if ldd "$artifact_root/gcc-release/tape" | grep -Eiq 'python|cuda'; then
  printf '%s\n' 'forbidden Python or CUDA runtime dependency in tape CLI' >&2
  exit 1
fi

"$tools_python" -m py_compile \
  "$repo_root/parity/python_reference/tape_reference.py" \
  "$repo_root/parity/tests/golden/golden.py" \
  "$repo_root/parity/tests/integration/test_port004.py"

shellcheck \
  "$repo_root/scripts/ci/p004_tape_tests.sh" \
  "$repo_root/scripts/ci/p004_coverage.sh" \
  "$repo_root/scripts/ci/p004_mutation.sh" \
  "$repo_root/parity/tests/fuzz/run_campaign.sh"

tracked_after=$(git -C "$repo_root" diff --binary HEAD -- . | sha256sum)
if [[ "$tracked_before" != "$tracked_after" ]]; then
  printf '%s\n' 'PORT004 profiles mutated tracked source files' >&2
  exit 1
fi

printf '%s\n' 'PORT004_TAPE_TESTS=PASS'
