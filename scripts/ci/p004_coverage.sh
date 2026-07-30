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
  printf '%s\n' '--artifact-root must be absolute' >&2; exit 64
fi
if [[ -z "$tools_python" || "$tools_python" != /* || ! -x "$tools_python" ]]; then
  printf '%s\n' '--tools-python must be an absolute executable' >&2; exit 64
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
mkdir -p -- "$artifact_root/profiles"
build="$artifact_root/build"
cmake -S "$repo_root" -B "$build" -G Ninja \
  -DCMAKE_C_COMPILER=/usr/bin/clang-16 -DCMAKE_BUILD_TYPE=Debug \
  -DBUILD_TESTING=ON -DP0_ENABLE_COVERAGE=ON \
  -DP0_TOOLS_PYTHON="$tools_python" \
  >"$artifact_root/configure.log" 2>&1
cmake --build "$build" --parallel 2 >"$artifact_root/build.log" 2>&1
LLVM_PROFILE_FILE="$artifact_root/profiles/%p-%m.profraw" \
  ctest --test-dir "$build" -L port004 --output-on-failure --no-tests=error \
  >"$artifact_root/ctest.log" 2>&1
/usr/lib/llvm-16/bin/llvm-profdata merge -sparse "$artifact_root"/profiles/*.profraw \
  -o "$artifact_root/coverage.profdata"
/usr/lib/llvm-16/bin/llvm-cov report "$build/tape" \
  -object "$build/p004_unit" -object "$build/p004_abi_c" \
  -object "$build/p004_fault_inject" \
  -instr-profile="$artifact_root/coverage.profdata" \
  "$repo_root/parity/src" >"$artifact_root/coverage.txt"
/usr/lib/llvm-16/bin/llvm-cov export "$build/tape" \
  -object "$build/p004_unit" -object "$build/p004_abi_c" \
  -object "$build/p004_fault_inject" \
  -instr-profile="$artifact_root/coverage.profdata" \
  -format=text >"$artifact_root/coverage.json"
"$tools_python" - \
  "$artifact_root/coverage.json" <<'PY'
import json, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
for item in data["data"]:
    for f in item["files"]:
        name=f["filename"]
        if "/parity/src/" not in name: continue
        lines=f["summary"]["lines"]["percent"]
        branches=f["summary"]["branches"]["percent"]
        floor_line=100.0 if name.endswith(("checked.c","status.c")) else 95.0
        floor_branch=100.0 if name.endswith("checked.c") else 90.0
        if lines + 1e-9 < floor_line or branches + 1e-9 < floor_branch:
            raise SystemExit(f"coverage below gate: {name}: line={lines} branch={branches}")
print("PORT004_COVERAGE=PASS")
PY
