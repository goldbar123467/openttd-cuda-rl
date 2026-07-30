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

"$tools_python" \
  "$repo_root/parity/tests/mutation/mutation_runner.py" \
  --repository-root "$repo_root" --artifact-root "$artifact_root/mutants" \
  --python "$tools_python"
