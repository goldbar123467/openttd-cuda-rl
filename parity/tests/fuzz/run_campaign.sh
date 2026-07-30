#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo_root=$(cd -- "$script_dir/../../.." && pwd -P)
artifact_root=""
tools_python=""
parser_runs=1000000
pair_runs=250000
while (($# > 0)); do
  case "$1" in
    --artifact-root) artifact_root=$2; shift 2 ;;
    --tools-python) tools_python=$2; shift 2 ;;
    --parser-runs) parser_runs=$2; shift 2 ;;
    --pair-runs) pair_runs=$2; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 64 ;;
  esac
done
if [[ -z "$artifact_root" || "$artifact_root" != /* ]]; then
  printf '%s\n' '--artifact-root must be absolute' >&2; exit 64
fi
if [[ -z "$tools_python" || "$tools_python" != /* || ! -x "$tools_python" ]]; then
  printf '%s\n' '--tools-python must be an absolute executable' >&2; exit 64
fi
if [[ ! "$parser_runs" =~ ^[1-9][0-9]*$ || ! "$pair_runs" =~ ^[1-9][0-9]*$ ]]; then
  printf '%s\n' 'execution counts must be positive integers' >&2; exit 64
fi
artifact_root=$(realpath -m -- "$artifact_root")
case "$artifact_root" in
  /|/workspace|"$repo_root"|"$repo_root"/*) printf '%s\n' 'unsafe artifact root' >&2; exit 64 ;;
esac
mkdir -p -- "$artifact_root"
artifact_root=$(cd -- "$artifact_root" && pwd -P)
case "$artifact_root" in
  /|/workspace|"$repo_root"|"$repo_root"/*) printf '%s\n' 'unsafe artifact root' >&2; exit 64 ;;
esac
if [[ -n "$(find "$artifact_root" -type l -print -quit)" ]]; then
  printf '%s\n' 'artifact root must not contain symlinks' >&2; exit 64
fi
build="$artifact_root/build"
corpus="$artifact_root/corpus"
"$tools_python" "$repo_root/parity/tests/fuzz/build_corpora.py" \
  --repository-root "$repo_root" --output "$corpus"
cmake -S "$repo_root" -B "$build" -G Ninja \
  -DCMAKE_C_COMPILER=/usr/bin/clang-16 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DBUILD_TESTING=OFF -DP0_ENABLE_FUZZING=ON \
  -DP0_TOOLS_PYTHON="$tools_python" \
  >"$artifact_root/configure.log" 2>&1
cmake --build "$build" --parallel 2 >"$artifact_root/build.log" 2>&1

targets=(fuzz_tape_prefix fuzz_tape_header fuzz_tape_records
  fuzz_projection_payload fuzz_full_tape fuzz_command_input
  fuzz_field_schema_json fuzz_manifest_json fuzz_comparator_pair
  fuzz_minimizer_pair)
ASAN_OPTIONS='abort_on_error=1:detect_leaks=1:halt_on_error=1' \
UBSAN_OPTIONS='abort_on_error=1:halt_on_error=1:print_stacktrace=1' \
  export ASAN_OPTIONS UBSAN_OPTIONS
{
  /usr/bin/clang-16 --version | head -n 1
  printf 'compile_flags=%s\n' '-std=c17 RelWithDebInfo ASan UBSan libFuzzer'
  printf 'asan_options=%s\n' "$ASAN_OPTIONS"
  printf 'ubsan_options=%s\n' "$UBSAN_OPTIONS"
} >"$artifact_root/campaign-manifest.txt"
find "$corpus" -mindepth 2 -maxdepth 2 -type f -print0 | sort -z |
  xargs -0 sha256sum >"$artifact_root/seed-corpus.sha256"
for target in "${targets[@]}"; do
  runs=$parser_runs
  case "$target" in fuzz_comparator_pair|fuzz_minimizer_pair) runs=$pair_runs ;; esac
  printf 'target=%s runs=%s\n' "$target" "$runs" >>"$artifact_root/campaign-manifest.txt"
  "$build/$target" -runs="$runs" -timeout=2 -rss_limit_mb=1024 \
    "$corpus/$target" >"$artifact_root/$target.log" 2>&1
done
find "$corpus" -mindepth 2 -maxdepth 2 -type f -print0 | sort -z | xargs -0 sha256sum \
  >"$artifact_root/final-corpus.sha256"
for target in "${targets[@]}"; do
  while IFS= read -r -d '' member; do
    expected=""
    for replay in {1..10}; do
      set +e
      "$build/$target" -runs=1 "$member" \
        >"$artifact_root/replay-$target.log" 2>&1
      result=$?
      set -e
      if [[ -z "$expected" ]]; then expected=$result; fi
      if [[ "$result" != "$expected" ]] || ((result != 0)); then
        printf 'nondeterministic replay target=%s member=%s iteration=%s status=%s expected=%s\n' \
          "$target" "$member" "$replay" "$result" "$expected" >&2
        exit 1
      fi
    done
  done < <(find "$corpus/$target" -maxdepth 1 -type f -print0 | sort -z)
done
printf 'PORT004_FUZZ=PASS parser_runs=%s pair_runs=%s\n' "$parser_runs" "$pair_runs"
