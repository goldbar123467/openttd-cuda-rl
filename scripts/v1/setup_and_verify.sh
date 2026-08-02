#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    'usage: scripts/v1/setup_and_verify.sh [--bootstrap] [--full-source] [--no-submodule-update]' \
    '' \
    '  --bootstrap            Install missing apt-provided quick-check dependencies.' \
    '  --full-source          Also require gitleaks and a clean main synchronized with origin/main.' \
    '  --no-submodule-update  Verify the existing OpenTTD checkout without initializing it.' \
    '' \
    'This source check does not run the dependency-heavy M12/G12 reproduction campaign.'
}

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
bootstrap=false
full_source=false
update_submodule=true

while (($#)); do
  case "$1" in
    --bootstrap) bootstrap=true ;;
    --full-source) full_source=true ;;
    --no-submodule-update) update_submodule=false ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

missing=()
for executable in git python3 shellcheck; do
  command -v "$executable" >/dev/null 2>&1 || missing+=("$executable")
done
python3 -c 'import jsonschema' >/dev/null 2>&1 || missing+=("python3-jsonschema")

if ((${#missing[@]})) && [[ "$bootstrap" == true ]]; then
  command -v apt-get >/dev/null 2>&1 || {
    echo "quick-check dependencies are missing and apt-get is unavailable: ${missing[*]}" >&2
    exit 1
  }
  privilege=()
  if ((EUID != 0)); then
    command -v sudo >/dev/null 2>&1 || {
      echo "quick-check dependency repair requires root or sudo: ${missing[*]}" >&2
      exit 1
    }
    privilege=(sudo)
  fi
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y git shellcheck python3-jsonschema
fi

for executable in git python3 shellcheck; do
  command -v "$executable" >/dev/null 2>&1 || {
    echo "missing executable: $executable (rerun with --bootstrap on Ubuntu)" >&2
    exit 1
  }
done
python3 -c 'import jsonschema' >/dev/null 2>&1 || {
  echo "missing Python module jsonschema (rerun with --bootstrap on Ubuntu)" >&2
  exit 1
}

if [[ "$update_submodule" == true ]]; then
  git -C "$repo_root" submodule update --init openttd-upstream
fi
expected_upstream=29f808ef0022064e6d9a83c8476d1e0f4686af86
observed_upstream=$(git -C "$repo_root/openttd-upstream" rev-parse HEAD)
[[ "$observed_upstream" == "$expected_upstream" ]] || {
  echo "OpenTTD submodule drifted: expected $expected_upstream, observed $observed_upstream" >&2
  exit 1
}

"$repo_root/scripts/v1/traceability.sh"
"$repo_root/scripts/v1/run_m12_foundation_tests.sh"
"$repo_root/scripts/v1/run_m13_foundation_tests.sh"

mapfile -t shell_files < <(git -C "$repo_root" ls-files 'scripts/v1/*.sh')
((${#shell_files[@]})) || { echo "no tracked V1 shell scripts found" >&2; exit 1; }
for index in "${!shell_files[@]}"; do
  shell_files[index]="$repo_root/${shell_files[index]}"
done
shellcheck "${shell_files[@]}"
bash -n "${shell_files[@]}"

mapfile -t python_files < <(git -C "$repo_root" ls-files 'scripts/v1/*.py' 'tests/project/*.py' 'tests/project/**/*.py')
((${#python_files[@]})) || { echo "no tracked V1 Python files found" >&2; exit 1; }
for index in "${!python_files[@]}"; do
  python_files[index]="$repo_root/${python_files[index]}"
done
python3 -m py_compile "${python_files[@]}"
git -C "$repo_root" diff --check

if [[ "$full_source" == true ]]; then
  command -v gitleaks >/dev/null 2>&1 || {
    echo "--full-source requires the gitleaks executable" >&2
    exit 1
  }
  [[ $(git -C "$repo_root" branch --show-current) == main ]] || {
    echo "--full-source requires branch main" >&2
    exit 1
  }
  [[ -z $(git -C "$repo_root" status --short) ]] || {
    echo "--full-source requires a clean repository" >&2
    exit 1
  }
  git -C "$repo_root" fetch --quiet origin main
  [[ $(git -C "$repo_root" rev-parse HEAD) == $(git -C "$repo_root" rev-parse origin/main) ]] || {
    echo "--full-source requires local main equal to origin/main" >&2
    exit 1
  }
  gitleaks detect --redact --no-banner --source "$repo_root"
fi

echo "OPENTTD_RL_SOURCE_VERIFY=PASS mode=$([[ "$full_source" == true ]] && echo full-source || echo quick) upstream=$observed_upstream"
