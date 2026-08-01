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
Usage: apply_instrumentation.sh --artifact-root ABSOLUTE_PATH
                                --worktree ABSOLUTE_PATH
                               [--reverse]

Applies the complete ordered PORT-003 mail patch series to a clean pinned
disposable worktree. --reverse removes the complete series in reverse order.
EOF
    p0_show_common_help_note
}

ARTIFACT_ROOT=''
WORKTREE=''
REVERSE=0
declare -a ORIGINAL_ARGUMENTS=("$@")
while (($# > 0)); do
    case "$1" in
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --worktree)
            (($# >= 2)) || p0_usage_error '--worktree requires a value'
            WORKTREE=$2
            shift 2
            ;;
        --reverse)
            REVERSE=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *) p0_usage_error "unknown argument: $1" ;;
    esac
done

p0_require_absolute_path "${ARTIFACT_ROOT}" '--artifact-root'
p0_require_absolute_path "${WORKTREE}" '--worktree'
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
WORKTREE=$(p0_realpath "${WORKTREE}")
p0_assert_under_root "${WORKTREE}" "${ARTIFACT_ROOT}" no
[[ -d "${WORKTREE}" && ! -L "${WORKTREE}" ]] || p0_usage_error '--worktree must be a non-symlink directory'

p0_initialize 'apply-instrumentation' "${ARTIFACT_ROOT}" 'apply-instrumentation.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/apply-instrumentation.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in git sha256sum; do
    p0_require_command "${tool}"
done

source_root="${P0_REPOSITORY_ROOT}/openttd-upstream"
p0_require_commit "${source_root}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
p0_require_clean_submodule "${source_root}"
p0_require_commit "${WORKTREE}" "${P0_EXPECTED_SUBMODULE_COMMIT}"

patch_root="${P0_REPOSITORY_ROOT}/oracle/instrumentation/patches"
series_file="${patch_root}/series"
[[ -f "${series_file}" && ! -L "${series_file}" ]] || p0_die 'instrumentation series file is missing or linked' 66
mapfile -t patch_names <"${series_file}"
((${#patch_names[@]} > 0)) || p0_die 'instrumentation series is empty' 65

declare -A seen_patch_names=()
declare -a patch_paths=()
for patch_name in "${patch_names[@]}"; do
    [[ "${patch_name}" =~ ^[0-9]{4}-[a-z0-9][a-z0-9-]*[.]patch$ ]] \
        || p0_die "invalid instrumentation patch name: ${patch_name}" 65
    [[ -z "${seen_patch_names["${patch_name}"]+present}" ]] \
        || p0_die "duplicate instrumentation patch name: ${patch_name}" 65
    seen_patch_names["${patch_name}"]=1
    patch_path="${patch_root}/${patch_name}"
    [[ -f "${patch_path}" && ! -L "${patch_path}" ]] \
        || p0_die "instrumentation patch is missing or linked: ${patch_name}" 66
    patch_paths+=("${patch_path}")
done

manifest_root=$(p0_make_temp_dir "${ARTIFACT_ROOT}" 'patch-manifest')
manifest_file="${manifest_root}/sha256.txt"
printf '%s  series\n' "$(p0_sha256_file "${series_file}")" >"${manifest_file}"
for patch_path in "${patch_paths[@]}"; do
    printf '%s  %s\n' "$(p0_sha256_file "${patch_path}")" "$(basename -- "${patch_path}")" >>"${manifest_file}"
done
series_sha256=$(p0_sha256_file "${manifest_file}")
if ((REVERSE == 0)); then
    [[ -z "$(git -C "${WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] \
        || p0_die 'instrumentation apply requires a clean pinned worktree' 65

    validation_root=$(p0_make_temp_dir "${ARTIFACT_ROOT}" 'patch-index')
    validation_index="${validation_root}/index"
    GIT_INDEX_FILE="${validation_index}" git -C "${WORKTREE}" read-tree HEAD
    for patch_path in "${patch_paths[@]}"; do
        if ! GIT_INDEX_FILE="${validation_index}" git -C "${WORKTREE}" apply --cached --check "${patch_path}"; then
            p0_die "instrumentation series precheck failed: $(basename -- "${patch_path}")" 65
        fi
        GIT_INDEX_FILE="${validation_index}" git -C "${WORKTREE}" apply --cached "${patch_path}"
    done

    for patch_path in "${patch_paths[@]}"; do
        git -C "${WORKTREE}" apply "${patch_path}" \
            || p0_die "instrumentation apply failed: $(basename -- "${patch_path}")" 65
    done
    [[ -n "$(git -C "${WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] \
        || p0_die 'instrumentation series applied without changing the worktree' 70
    action='applied'
else
    [[ -n "$(git -C "${WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] \
        || p0_die 'instrumentation reverse requires an applied series' 65
    for ((index = ${#patch_paths[@]} - 1; index >= 0; index--)); do
        git -C "${WORKTREE}" apply --reverse --check "${patch_paths[index]}" \
            || p0_die "instrumentation reverse precheck failed: $(basename -- "${patch_paths[index]}")" 65
        git -C "${WORKTREE}" apply --reverse "${patch_paths[index]}" \
            || p0_die "instrumentation reverse failed: $(basename -- "${patch_paths[index]}")" 65
    done
    [[ -z "$(git -C "${WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] \
        || p0_die 'reversing instrumentation did not restore the clean pinned worktree' 65
    action='reversed'
fi

p0_require_commit "${WORKTREE}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
p0_require_clean_submodule "${source_root}"
p0_finish 'PASS' 0 "${action} instrumentation series ${series_sha256}"
