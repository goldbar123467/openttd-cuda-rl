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

before_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)
export PYTHONPYCACHEPREFIX="${artifact_root}/pycache"

git -C "${P0_REPOSITORY_ROOT}" diff --check HEAD --

"${tools_python}" - "${P0_REPOSITORY_ROOT}" <<'PY'
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import jsonschema

root = pathlib.Path(sys.argv[1])
raw_paths = subprocess.check_output(
    ["git", "-C", str(root), "ls-files", "-z"],
)
paths = [root / pathlib.Path(value.decode("utf-8")) for value in raw_paths.split(b"\0") if value]
text_suffixes = {
    ".c", ".cc", ".cmake", ".cpp", ".h", ".hpp", ".in", ".json",
    ".md", ".py", ".sh", ".txt", ".yaml", ".yml",
}
failures: list[str] = []

def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate key {key!r}")
        value[key] = child
    return value

for path in paths:
    if not path.is_file() or path.is_symlink():
        continue
    if path.suffix.lower() not in text_suffixes and path.name not in {
        ".clang-tidy", ".gitattributes", ".gitignore", ".gitmodules", ".gitleaks.toml",
    }:
        continue
    relative = path.relative_to(root)
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{relative}: invalid UTF-8: {exc}")
        continue
    enforce_layout = relative.parts[0] in {
        ".github", "cmake", "docs", "oracle", "parity", "scripts", "tools",
    } or relative.as_posix() in {
        ".clang-tidy", ".gitattributes", ".gitignore", ".gitmodules",
        ".gitleaks.toml", "CMakeLists.txt", "CMakePresets.json", "README.md",
    }
    if data.startswith(b"\xef\xbb\xbf"):
        failures.append(f"{relative}: UTF-8 BOM is forbidden")
    if enforce_layout and b"\r" in data:
        failures.append(f"{relative}: carriage return is forbidden")
    if enforce_layout and data and not data.endswith(b"\n"):
        failures.append(f"{relative}: missing final newline")
    if enforce_layout:
        for number, line in enumerate(text.splitlines(), start=1):
            if line.endswith((" ", "\t")):
                failures.append(f"{relative}:{number}: trailing whitespace")
    if path.suffix == ".json":
        try:
            value = json.loads(
                text,
                object_pairs_hook=reject_duplicates,
                parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"invalid constant {token}")),
            )
            if isinstance(value, dict) and "$id" in value:
                jsonschema.Draft202012Validator.check_schema(value)
        except (ValueError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
            failures.append(f"{relative}: invalid JSON/schema: {exc}")
if failures:
    raise SystemExit("\n".join(failures))
print(f"checked {len(paths)} tracked paths")
PY

mapfile -d '' shell_files < <(git -C "${P0_REPOSITORY_ROOT}" ls-files -z -- '*.sh')
for relative in "${shell_files[@]}"; do
    bash -n -- "${P0_REPOSITORY_ROOT}/${relative}"
done

mapfile -d '' python_files < <(git -C "${P0_REPOSITORY_ROOT}" ls-files -z -- '*.py')
if ((${#python_files[@]} > 0)); then
    python_paths=()
    for relative in "${python_files[@]}"; do
        python_paths+=("${P0_REPOSITORY_ROOT}/${relative}")
    done
    "${tools_python}" -m py_compile "${python_paths[@]}"
fi

after_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ "${before_status}" == "${after_status}" ]] || p0_die 'format checks changed the source worktree' 70
printf '%s\n' 'P0_FORMAT=PASS'
