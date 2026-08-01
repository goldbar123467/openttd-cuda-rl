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
Usage: create_instrumented_worktree.sh --artifact-root ABSOLUTE_PATH
                                       --worktree ABSOLUTE_PATH

Creates one new detached disposable worktree at the pinned OpenTTD commit.
The target must not exist and must be a proper descendant of artifact-root.
EOF
    p0_show_common_help_note
}

ARTIFACT_ROOT=''
WORKTREE=''
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
[[ ! -e "${WORKTREE}" && ! -L "${WORKTREE}" ]] || p0_usage_error '--worktree target must not exist'

p0_initialize 'create-instrumented-worktree' "${ARTIFACT_ROOT}" 'create-instrumented-worktree.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/create-instrumented-worktree.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in git realpath mkdir; do
    p0_require_command "${tool}"
done

source_root="${P0_REPOSITORY_ROOT}/openttd-upstream"
p0_require_commit "${source_root}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
p0_require_clean_submodule "${source_root}"

worktree_parent=$(dirname -- "${WORKTREE}")
p0_assert_under_root "${worktree_parent}" "${ARTIFACT_ROOT}" yes
mkdir -p -- "${worktree_parent}"
worktree_parent=$(cd -- "${worktree_parent}" && pwd -P)
p0_assert_under_root "${worktree_parent}" "${ARTIFACT_ROOT}" yes

p0_log INFO 'creating a detached disposable worktree from the exact pinned commit'
if git -C "${source_root}" worktree add --detach "${WORKTREE}" "${P0_EXPECTED_SUBMODULE_COMMIT}" \
    >"${ARTIFACT_ROOT}/logs/create-instrumented-worktree.stdout.log" \
    2>"${ARTIFACT_ROOT}/logs/create-instrumented-worktree.stderr.log"; then
    :
else
    worktree_rc=$?
    p0_die "failed to create disposable worktree with exit ${worktree_rc}" "${worktree_rc}"
fi

p0_require_commit "${WORKTREE}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
[[ -z "$(git -C "${WORKTREE}" status --porcelain=v1 --untracked-files=all)" ]] \
    || p0_die 'new disposable worktree is unexpectedly dirty' 70
p0_require_clean_submodule "${source_root}"
p0_finish 'PASS' 0 "created pinned disposable worktree at ${WORKTREE}"
