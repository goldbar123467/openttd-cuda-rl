#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly SCRIPT_DIR
REPOSITORY_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd -P)
readonly REPOSITORY_ROOT
# shellcheck disable=SC1091
source "${REPOSITORY_ROOT}/oracle/runner/common.sh"

readonly EXPECTED_FIXTURE_SHA256='74c9be53902598061e1e82835c394a37b77bfc71c818de1df8456cdfc2804d20'
readonly EXPECTED_FIXTURE_SIZE=10008
readonly EXPECTED_MAP_SHA256='5a933bc43d59c05b0d8fda519aec0aafa71b16d50a03aea83aefade7a57c9dd6'
readonly EXPECTED_MAP_SIZE=49152
readonly BUILDER_PATCH_SHA256='ffb34c53680adb1cf1649b84ea1ca4c66449c210ade143ece61e6547ac87cd9e'

usage() {
    cat <<'EOF'
Usage: build_fixture.sh --artifact-root ABSOLUTE_PATH
                        --opengfx-tar ABSOLUTE_PATH
                        [--jobs POSITIVE_INTEGER]

Applies the reviewed fixture-builder patch to a disposable worktree at the
pinned OpenTTD commit, builds the frozen RelWithDebInfo profile, and creates the
fixture twice in isolated XDG trees and distinct wall-clock seconds. Both save
files and both canonical map-plane streams must equal each other and the
committed immutable artifacts. The normal openttd-upstream worktree is never
patched or built in place.
EOF
    p0_show_common_help_note
}

ARTIFACT_ROOT=''
OPENGFX_TAR=''
JOBS=8
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --opengfx-tar)
            (($# >= 2)) || p0_usage_error '--opengfx-tar requires a value'
            OPENGFX_TAR=$2
            shift 2
            ;;
        --jobs)
            (($# >= 2)) || p0_usage_error '--jobs requires a value'
            JOBS=$2
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
p0_require_absolute_path "${OPENGFX_TAR}" '--opengfx-tar'
[[ "${JOBS}" =~ ^[1-9][0-9]*$ ]] || p0_usage_error '--jobs must be a positive integer'
((JOBS <= 64)) || p0_usage_error '--jobs must not exceed 64'

ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
OPENGFX_TAR=$(p0_realpath "${OPENGFX_TAR}")
p0_initialize 'build-p002-fixture' "${ARTIFACT_ROOT}" 'build-p002-fixture.json'
mkdir -p -- "${ARTIFACT_ROOT}/commands" "${ARTIFACT_ROOT}/evidence"
p0_write_command_array "${ARTIFACT_ROOT}/commands/build-fixture.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"

for tool in cmake cmp cp date git ninja python3 sha256sum sleep timeout wc; do
    p0_require_command "${tool}"
done

readonly SOURCE_REPOSITORY="${REPOSITORY_ROOT}/openttd-upstream"
readonly BUILDER_PATCH="${SCRIPT_DIR}/0001-deterministic-road-freight-fixture-builder.patch"
readonly TRACKED_FIXTURE="${SCRIPT_DIR}/../fixture.sav"
readonly TRACKED_MAP="${SCRIPT_DIR}/../map-planes-v1.bin"
readonly SOURCE_WORKTREE="${ARTIFACT_ROOT}/source"
readonly BUILD_ROOT="${ARTIFACT_ROOT}/build"
readonly INSTALL_ROOT="${ARTIFACT_ROOT}/install"

p0_require_commit "${SOURCE_REPOSITORY}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
p0_require_clean_submodule "${SOURCE_REPOSITORY}"
p0_require_sha256 "${BUILDER_PATCH}" "${BUILDER_PATCH_SHA256}" 'fixture-builder patch'
p0_require_sha256 "${OPENGFX_TAR}" "${P0_OPENGFX_INSTALLED_SHA256}" 'OpenGFX installed tar'
p0_require_sha256 "${TRACKED_FIXTURE}" "${EXPECTED_FIXTURE_SHA256}" 'committed fixture'
p0_require_sha256 "${TRACKED_MAP}" "${EXPECTED_MAP_SHA256}" 'committed map planes'
[[ "$(wc -c <"${TRACKED_FIXTURE}")" -eq ${EXPECTED_FIXTURE_SIZE} ]] || p0_die 'committed fixture size mismatch' 65
[[ "$(wc -c <"${TRACKED_MAP}")" -eq ${EXPECTED_MAP_SIZE} ]] || p0_die 'committed map-plane size mismatch' 65

for generated_path in "${SOURCE_WORKTREE}" "${BUILD_ROOT}" "${INSTALL_ROOT}"; do
    p0_assert_under_root "${generated_path}" "${ARTIFACT_ROOT}" no
    [[ ! -e "${generated_path}" ]] || p0_die "generated path must not already exist: ${generated_path}" 64
done

p0_log INFO 'creating a detached disposable worktree at the pinned OpenTTD commit'
git -C "${SOURCE_REPOSITORY}" worktree add --detach "${SOURCE_WORKTREE}" "${P0_EXPECTED_SUBMODULE_COMMIT}" \
    >"${ARTIFACT_ROOT}/logs/worktree.stdout.log" 2>"${ARTIFACT_ROOT}/logs/worktree.stderr.log"
git -C "${SOURCE_WORKTREE}" apply --check "${BUILDER_PATCH}"
git -C "${SOURCE_WORKTREE}" apply --index "${BUILDER_PATCH}"

declare -a configure_command=(
    /usr/bin/cmake
    -S "${SOURCE_WORKTREE}"
    -B "${BUILD_ROOT}"
    -G Ninja
    -DCMAKE_BUILD_TYPE=RelWithDebInfo
    "-DCMAKE_INSTALL_PREFIX=${INSTALL_ROOT}"
    -DCMAKE_C_COMPILER=/usr/bin/gcc
    -DCMAKE_CXX_COMPILER=/usr/bin/g++
    -DCMAKE_CXX_FLAGS=
    '-DCMAKE_CXX_FLAGS_DEBUG=-g'
    '-DCMAKE_CXX_FLAGS_MINSIZEREL=-Os -DNDEBUG'
    '-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG'
    '-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O2 -g -DNDEBUG'
    -DCMAKE_EXE_LINKER_FLAGS=
    -DCMAKE_MODULE_LINKER_FLAGS=
    -DCMAKE_SHARED_LINKER_FLAGS=
    -DPERSONAL_DIR:STRING=.openttd
    '-DSHARED_DIR:STRING=(not set)'
    "-DGLOBAL_DIR:STRING=${INSTALL_ROOT}/share/games/openttd"
    -DHOST_BINARY_DIR=
    -DOPTION_DEDICATED=OFF
    -DOPTION_INSTALL_FHS=ON
    -DOPTION_PACKAGE_DEPENDENCIES=OFF
    -DOPTION_USE_ASSERTS=ON
    -DOPTION_FORCE_COLORED_OUTPUT=OFF
    -DOPTION_USE_NSIS=OFF
    -DOPTION_TOOLS_ONLY=OFF
    -DOPTION_DOCS_ONLY=OFF
    -DOPTION_ALLOW_INVALID_SIGNATURE=OFF
    -DOPTION_LINE_IN_DOXYGEN_WARNINGS=ON
    -DOPTION_SURVEY_KEY=
    -DOPTION_DOXYGEN_WARN_FILE=
    -DOPTION_DOXYGEN_GS_WARN_FILE=
    -DOPTION_DOXYGEN_AI_WARN_FILE=
)
p0_write_command_array "${ARTIFACT_ROOT}/commands/configure-cmake.json" "${configure_command[@]}"
p0_log INFO 'configuring the exact frozen reference profile with the reviewed builder patch applied'
"${configure_command[@]}" >"${ARTIFACT_ROOT}/logs/configure.stdout.log" 2>"${ARTIFACT_ROOT}/logs/configure.stderr.log"

declare -a build_command=(/usr/bin/cmake --build "${BUILD_ROOT}" --target openttd --parallel "${JOBS}" --verbose)
p0_write_command_array "${ARTIFACT_ROOT}/commands/build-openttd.json" "${build_command[@]}"
p0_log INFO 'building the disposable native fixture creator'
"${build_command[@]}" >"${ARTIFACT_ROOT}/logs/build.stdout.log" 2>"${ARTIFACT_ROOT}/logs/build.stderr.log"

readonly EXECUTABLE="${BUILD_ROOT}/openttd"
[[ -f "${EXECUTABLE}" && -x "${EXECUTABLE}" && ! -L "${EXECUTABLE}" ]] || p0_die 'fixture-builder executable is missing' 66
executable_sha256=$(p0_sha256_file "${EXECUTABLE}")
readonly executable_sha256

run_fixture() {
    local label=$1
    local run_root="${ARTIFACT_ROOT}/${label}"
    local output="${run_root}/fixture.sav"
    local data_root="${run_root}/data"
    local config_root="${run_root}/config"
    local cache_root="${run_root}/cache"
    mkdir -p -- "${data_root}/openttd/baseset" "${config_root}" "${cache_root}"
    cp -- "${OPENGFX_TAR}" "${data_root}/openttd/baseset/${P0_OPENGFX_INSTALLED_NAME}"
    declare -a command=(
        env -i
        LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=UTC SOURCE_DATE_EPOCH="${P0_SOURCE_DATE_EPOCH}"
        XDG_DATA_HOME="${data_root}" XDG_CONFIG_HOME="${config_root}" XDG_CACHE_HOME="${cache_root}"
        /usr/bin/timeout --signal=TERM --kill-after=10s 120s
        "${EXECUTABLE}"
        -c /dev/null -v null:ticks=1 -s null -m null -I opengfx -Z "${output}"
    )
    p0_write_command_array "${ARTIFACT_ROOT}/commands/${label}.json" "${command[@]}"
    "${command[@]}" >"${run_root}/creation.stdout.log" 2>"${run_root}/creation.stderr.log"
    [[ -f "${output}" && ! -L "${output}" ]] || p0_die "${label} did not emit fixture.sav" 66
    [[ -f "${output}.mapplanes.bin" && ! -L "${output}.mapplanes.bin" ]] || p0_die "${label} did not emit map planes" 66
    p0_require_sha256 "${output}" "${EXPECTED_FIXTURE_SHA256}" "${label} fixture"
    p0_require_sha256 "${output}.mapplanes.bin" "${EXPECTED_MAP_SHA256}" "${label} map planes"
    [[ "$(wc -c <"${output}")" -eq ${EXPECTED_FIXTURE_SIZE} ]] || p0_die "${label} fixture size mismatch" 65
    [[ "$(wc -c <"${output}.mapplanes.bin")" -eq ${EXPECTED_MAP_SIZE} ]] || p0_die "${label} map-plane size mismatch" 65
}

first_wallclock_second=$(date -u +%s)
run_fixture run-a
while (($(date -u +%s) <= first_wallclock_second)); do sleep 0.1; done
run_fixture run-b

cmp -- "${ARTIFACT_ROOT}/run-a/fixture.sav" "${ARTIFACT_ROOT}/run-b/fixture.sav"
cmp -- "${ARTIFACT_ROOT}/run-a/fixture.sav.mapplanes.bin" "${ARTIFACT_ROOT}/run-b/fixture.sav.mapplanes.bin"
cmp -- "${ARTIFACT_ROOT}/run-a/fixture.sav" "${TRACKED_FIXTURE}"
cmp -- "${ARTIFACT_ROOT}/run-a/fixture.sav.mapplanes.bin" "${TRACKED_MAP}"

python3 - "${ARTIFACT_ROOT}/evidence/fixture-reproduction.json" "${executable_sha256}" <<'PY'
import json
import pathlib
import sys

output = pathlib.Path(sys.argv[1])
value = {
    "builder_executable": {
        "note": "Raw executable bytes include absolute generated build paths; fixture identity does not depend on reproducing this digest.",
        "sha256": sys.argv[2],
    },
    "fixture": {
        "run_a_equals_run_b": True,
        "run_a_equals_tracked": True,
        "sha256": "74c9be53902598061e1e82835c394a37b77bfc71c818de1df8456cdfc2804d20",
        "size_bytes": 10008,
    },
    "map_planes": {
        "format": "tile-index-order:type,height,m1,m2le,m3,m4,m5,m6,m7,m8le",
        "run_a_equals_run_b": True,
        "run_a_equals_tracked": True,
        "sha256": "5a933bc43d59c05b0d8fda519aec0aafa71b16d50a03aea83aefade7a57c9dd6",
        "size_bytes": 49152,
    },
    "openttd_commit": "29f808ef0022064e6d9a83c8476d1e0f4686af86",
    "result": "PASS",
    "wall_clock_policy": "The two creation processes start in distinct UTC seconds. Wall clock is not an identity input; persisted RNG and savegame identity inputs are explicitly frozen.",
}
output.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

p0_log INFO 'removing only the successful disposable source worktree'
git -C "${SOURCE_REPOSITORY}" worktree remove --force "${SOURCE_WORKTREE}"
p0_finish PASS 0 'PORT002A fixture reproduction produced two byte-identical saves and map-plane streams matching the committed artifacts'
