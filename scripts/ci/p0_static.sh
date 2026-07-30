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

for command_name in cmake ninja clang-tidy-16 run-clang-tidy-16 scan-build-16 shellcheck gitleaks reuse rg; do
    p0_require_command "${command_name}"
done

mapfile -d '' shell_files < <(git -C "${P0_REPOSITORY_ROOT}" ls-files -z -- '*.sh')
if ((${#shell_files[@]} > 0)); then
    shell_paths=()
    for relative in "${shell_files[@]}"; do
        shell_paths+=("${P0_REPOSITORY_ROOT}/${relative}")
    done
    shellcheck --external-sources "${shell_paths[@]}" \
        >"${artifact_root}/shellcheck.stdout.log" \
        2>"${artifact_root}/shellcheck.stderr.log"
fi

build_root="${artifact_root}/clang-tidy-build"
p0_safe_reset_dir "${build_root}" "${artifact_root}"
cmake -S "${P0_REPOSITORY_ROOT}" -B "${build_root}" -G Ninja \
    -DCMAKE_C_COMPILER=/usr/bin/clang-16 \
    -DCMAKE_BUILD_TYPE=Debug \
    -DBUILD_TESTING=ON \
    -DP0_TOOLS_PYTHON="${tools_python}" \
    >"${artifact_root}/clang-configure.stdout.log" \
    2>"${artifact_root}/clang-configure.stderr.log"
cmake --build "${build_root}" --parallel 2 \
    >"${artifact_root}/clang-build.stdout.log" \
    2>"${artifact_root}/clang-build.stderr.log"
run-clang-tidy-16 -p "${build_root}" -j 2 \
    -header-filter='^.*/parity/(include|src|tools|tests)/.*' \
    '^.*/parity/.*[.]c$' \
    >"${artifact_root}/clang-tidy.stdout.log" \
    2>"${artifact_root}/clang-tidy.stderr.log"
if rg -n '(^|:[0-9]+:[0-9]+: )error:' \
    "${artifact_root}/clang-tidy.stdout.log" "${artifact_root}/clang-tidy.stderr.log"; then
    p0_die 'Clang-Tidy reported an error' 65
fi

analyzer_root="${artifact_root}/clang-analyzer-build"
p0_safe_reset_dir "${analyzer_root}" "${artifact_root}"
scan-build-16 --status-bugs --use-cc=/usr/bin/clang-16 \
    -o "${artifact_root}/clang-analyzer-reports" \
    cmake -S "${P0_REPOSITORY_ROOT}" -B "${analyzer_root}" -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DBUILD_TESTING=ON \
    -DP0_TOOLS_PYTHON="${tools_python}" \
    >"${artifact_root}/analyzer-configure.stdout.log" \
    2>"${artifact_root}/analyzer-configure.stderr.log"
scan-build-16 --status-bugs --use-cc=/usr/bin/clang-16 \
    -o "${artifact_root}/clang-analyzer-reports" \
    cmake --build "${analyzer_root}" --parallel 2 \
    >"${artifact_root}/analyzer-build.stdout.log" \
    2>"${artifact_root}/analyzer-build.stderr.log"

if rg -n --glob '*.sh' --glob '!p0_static.sh' '(^|[;&|[:space:]])eval([;&|[:space:]]|$)' \
    oracle/runner scripts; then
    p0_die 'banned eval use detected' 65
fi
if rg -n --glob '*.{c,h,py,sh}' --glob '!p0_static.sh' \
    '\b(TODO|FIXME|XXX)\b' parity/include parity/src parity/tools oracle/runner scripts; then
    p0_die 'unresolved implementation marker detected' 65
fi
if rg -n --glob '*.{c,h}' 'fwrite[[:space:]]*\([[:space:]]*&' parity; then
    p0_die 'possible raw in-memory object serialization detected' 65
fi
if rg -n --glob '*.sh' --glob '!p0_static.sh' \
    '(mktemp|mkdir)[^\n]*(/tmp|/var/tmp)' oracle/runner scripts; then
    p0_die 'hard-coded shared temporary path detected' 65
fi

gitleaks detect --source "${P0_REPOSITORY_ROOT}" --redact --no-banner --exit-code 1 \
    >"${artifact_root}/gitleaks.stdout.log" \
    2>"${artifact_root}/gitleaks.stderr.log"
reuse --suppress-deprecation lint \
    >"${artifact_root}/reuse.stdout.log" \
    2>"${artifact_root}/reuse.stderr.log"

"${tools_python}" "${P0_REPOSITORY_ROOT}/tools/validate_manifest.py" \
    --schema "${P0_REPOSITORY_ROOT}/oracle/manifests/schema/defect-divergence-ledger.schema.json" \
    "${P0_REPOSITORY_ROOT}/evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json" \
    >"${artifact_root}/ledger-validation.log"
"${P0_REPOSITORY_ROOT}/scripts/ci/p005_schema_tests.sh" \
    --tools-python "${tools_python}" \
    >"${artifact_root}/field-schema-validation.log"

after_status=$(git -C "${P0_REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ "${before_status}" == "${after_status}" ]] || p0_die 'static checks changed the source worktree' 70
printf '%s\n' 'P0_STATIC=PASS'
