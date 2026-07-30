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
Usage: configure_reference.sh --source-root ABSOLUTE_PATH
                              --build-root ABSOLUTE_PATH
                              --install-root ABSOLUTE_PATH
                              --artifact-root ABSOLUTE_PATH

Creates a fresh Ninja cache for the frozen GCC RelWithDebInfo profile. Build and
install roots must be distinct proper descendants of artifact-root. Production
source must be the clean pinned openttd-upstream worktree.

Tests may set P0_TEST_MODE=1 and pass --test-source-override for a fixture Git
worktree below ARTIFACT_ROOT/test-fixtures. The override is otherwise rejected.
EOF
    p0_show_common_help_note
}

SOURCE_ROOT=''
BUILD_ROOT=''
INSTALL_ROOT=''
ARTIFACT_ROOT=''
TEST_SOURCE_OVERRIDE=0
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
        --source-root)
            (($# >= 2)) || p0_usage_error '--source-root requires a value'
            SOURCE_ROOT=$2
            shift 2
            ;;
        --build-root)
            (($# >= 2)) || p0_usage_error '--build-root requires a value'
            BUILD_ROOT=$2
            shift 2
            ;;
        --install-root)
            (($# >= 2)) || p0_usage_error '--install-root requires a value'
            INSTALL_ROOT=$2
            shift 2
            ;;
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --test-source-override)
            TEST_SOURCE_OVERRIDE=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            p0_usage_error "unknown argument: $1"
            ;;
    esac
done

for path_and_label in \
    "${SOURCE_ROOT}|--source-root" \
    "${BUILD_ROOT}|--build-root" \
    "${INSTALL_ROOT}|--install-root" \
    "${ARTIFACT_ROOT}|--artifact-root"; do
    p0_require_absolute_path "${path_and_label%%|*}" "${path_and_label#*|}"
done

ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
SOURCE_ROOT=$(p0_realpath "${SOURCE_ROOT}")
BUILD_ROOT=$(p0_realpath "${BUILD_ROOT}")
INSTALL_ROOT=$(p0_realpath "${INSTALL_ROOT}")
p0_assert_under_root "${BUILD_ROOT}" "${ARTIFACT_ROOT}" no
p0_assert_under_root "${INSTALL_ROOT}" "${ARTIFACT_ROOT}" no
[[ "${BUILD_ROOT}" != "${INSTALL_ROOT}" ]] || p0_usage_error 'build and install roots must differ'
[[ "${SOURCE_ROOT}" != "${BUILD_ROOT}" && "${SOURCE_ROOT}" != "${INSTALL_ROOT}" ]] || p0_usage_error 'source, build, and install roots must differ'

p0_initialize 'configure-reference' "${ARTIFACT_ROOT}" 'configure-reference.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/configure-reference.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in git cmake ninja gcc g++ ld python3 sha256sum find; do
    p0_require_command "${tool}"
done

expected_source="${P0_REPOSITORY_ROOT}/openttd-upstream"
if ((TEST_SOURCE_OVERRIDE == 1)); then
    [[ "${P0_TEST_MODE:-0}" == 1 ]] || p0_die '--test-source-override requires P0_TEST_MODE=1' 64
    p0_assert_under_root "${SOURCE_ROOT}" "${ARTIFACT_ROOT}/test-fixtures" yes
    source_commit=$(git -C "${SOURCE_ROOT}" rev-parse HEAD) || p0_die 'test source override is not a Git worktree' 65
    p0_log INFO "using deliberate test source override at commit ${source_commit}"
else
    [[ "${SOURCE_ROOT}" == "${expected_source}" ]] || p0_die "source root must be the pinned submodule: ${expected_source}" 65
    p0_require_commit "${SOURCE_ROOT}" "${P0_EXPECTED_SUBMODULE_COMMIT}"
    p0_require_clean_submodule "${SOURCE_ROOT}"
    source_commit=${P0_EXPECTED_SUBMODULE_COMMIT}
fi

source_changes=$(git -C "${SOURCE_ROOT}" status --porcelain=v1 --untracked-files=all)
if [[ -n "${source_changes}" ]]; then
    p0_log ERROR 'dirty source paths follow (contents are intentionally omitted)'
    printf '%s\n' "${source_changes}" | sed -E 's/^.. //' >&2
    p0_die 'configuration source tree must be clean' 65
fi

p0_log INFO 'resetting only the explicitly dedicated build root for a fresh cache'
p0_safe_reset_dir "${BUILD_ROOT}" "${ARTIFACT_ROOT}"
mkdir -p -- "${INSTALL_ROOT}" "${ARTIFACT_ROOT}/commands" "${ARTIFACT_ROOT}/manifests"

readonly CMAKE_BIN='/usr/bin/cmake'
readonly CC_BIN='/usr/bin/gcc'
readonly CXX_BIN='/usr/bin/g++'
readonly LINKER_BIN='/usr/bin/ld'
[[ -x "${CMAKE_BIN}" && -x "${CC_BIN}" && -x "${CXX_BIN}" && -x "${LINKER_BIN}" ]] || p0_die 'frozen tool paths are unavailable' 69

declare -a configure_command=(
    "${CMAKE_BIN}"
    -S "${SOURCE_ROOT}"
    -B "${BUILD_ROOT}"
    -G Ninja
    -DCMAKE_BUILD_TYPE=RelWithDebInfo
    "-DCMAKE_INSTALL_PREFIX=${INSTALL_ROOT}"
    "-DCMAKE_C_COMPILER=${CC_BIN}"
    "-DCMAKE_CXX_COMPILER=${CXX_BIN}"
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
p0_write_command_array "${ARTIFACT_ROOT}/commands/configure-reference-cmake.json" "${configure_command[@]}"
p0_log INFO 'configuring the frozen OpenTTD reference profile with a CMake argument array'
if "${configure_command[@]}" >"${ARTIFACT_ROOT}/logs/configure-reference.stdout.log" 2>"${ARTIFACT_ROOT}/logs/configure-reference.stderr.log"; then
    configure_rc=0
else
    configure_rc=$?
fi
((configure_rc == 0)) || p0_die "CMake configuration failed with exit ${configure_rc}" "${configure_rc}"

cache_file="${BUILD_ROOT}/CMakeCache.txt"
[[ -f "${cache_file}" ]] || p0_die 'CMake reported success without producing CMakeCache.txt' 70
grep -Fxq 'CMAKE_BUILD_TYPE:STRING=RelWithDebInfo' "${cache_file}" || p0_die 'configured build type differs from RelWithDebInfo' 65
grep -Fxq "CMAKE_INSTALL_PREFIX:PATH=${INSTALL_ROOT}" "${cache_file}" || p0_die 'configured install prefix differs from the explicit install root' 65
grep -Fxq 'CMAKE_GENERATOR:INTERNAL=Ninja' "${cache_file}" || p0_die 'configured generator differs from Ninja' 65
grep -Fxq 'OPTION_DEDICATED:BOOL=OFF' "${cache_file}" || p0_die 'dedicated-only mode must be OFF' 65
grep -Fxq 'OPTION_INSTALL_FHS:BOOL=ON' "${cache_file}" || p0_die 'FHS installation must be ON' 65
grep -Fxq 'OPTION_USE_ASSERTS:BOOL=ON' "${cache_file}" || p0_die 'assertions must be ON' 65
grep -Fxq 'OPTION_PACKAGE_DEPENDENCIES:BOOL=OFF' "${cache_file}" || p0_die 'dependency packaging must be OFF' 65
grep -Fxq 'OPTION_FORCE_COLORED_OUTPUT:BOOL=OFF' "${cache_file}" || p0_die 'colored-output option drift' 65
grep -Fxq 'OPTION_USE_NSIS:BOOL=OFF' "${cache_file}" || p0_die 'NSIS option drift' 65
grep -Fxq 'OPTION_TOOLS_ONLY:BOOL=OFF' "${cache_file}" || p0_die 'tools-only option drift' 65
grep -Fxq 'OPTION_DOCS_ONLY:BOOL=OFF' "${cache_file}" || p0_die 'docs-only option drift' 65
grep -Fxq 'OPTION_ALLOW_INVALID_SIGNATURE:BOOL=OFF' "${cache_file}" || p0_die 'invalid-signature policy drift' 65
grep -Fxq 'OPTION_LINE_IN_DOXYGEN_WARNINGS:BOOL=ON' "${cache_file}" || p0_die 'Doxygen warning-format option drift' 65
grep -Fxq 'OPTION_SURVEY_KEY:BOOL=' "${cache_file}" || p0_die 'survey-key option must remain empty' 65
grep -Fxq 'OPTION_DOXYGEN_WARN_FILE:BOOL=' "${cache_file}" || p0_die 'Doxygen warning output must remain empty' 65
grep -Fxq 'OPTION_DOXYGEN_GS_WARN_FILE:BOOL=' "${cache_file}" || p0_die 'GameScript Doxygen warning output must remain empty' 65
grep -Fxq 'OPTION_DOXYGEN_AI_WARN_FILE:BOOL=' "${cache_file}" || p0_die 'AI Doxygen warning output must remain empty' 65
grep -Fxq 'PERSONAL_DIR:STRING=.openttd' "${cache_file}" || p0_die 'personal-directory policy drift' 65
grep -Fxq 'SHARED_DIR:STRING=(not set)' "${cache_file}" || p0_die 'shared-directory policy drift' 65
grep -Fxq "GLOBAL_DIR:STRING=${INSTALL_ROOT}/share/games/openttd" "${cache_file}" || p0_die 'compiled global-data role drift' 65
grep -Fxq 'HOST_BINARY_DIR:PATH=' "${cache_file}" || p0_die 'host-binary cross-build path must remain empty' 65
grep -Fxq 'CMAKE_CXX_FLAGS:STRING=' "${cache_file}" || p0_die 'base C++ flags drift' 65
grep -Fxq 'CMAKE_CXX_FLAGS_DEBUG:STRING=-g' "${cache_file}" || p0_die 'debug C++ flags drift' 65
grep -Fxq 'CMAKE_CXX_FLAGS_MINSIZEREL:STRING=-Os -DNDEBUG' "${cache_file}" || p0_die 'MinSizeRel C++ flags drift' 65
grep -Fxq 'CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG' "${cache_file}" || p0_die 'release C++ flags drift' 65
grep -Fxq 'CMAKE_CXX_FLAGS_RELWITHDEBINFO:STRING=-O2 -g -DNDEBUG' "${cache_file}" || p0_die 'RelWithDebInfo C++ flags drift' 65
for linker_flags in \
    CMAKE_EXE_LINKER_FLAGS CMAKE_EXE_LINKER_FLAGS_DEBUG CMAKE_EXE_LINKER_FLAGS_MINSIZEREL CMAKE_EXE_LINKER_FLAGS_RELEASE CMAKE_EXE_LINKER_FLAGS_RELWITHDEBINFO \
    CMAKE_MODULE_LINKER_FLAGS CMAKE_MODULE_LINKER_FLAGS_DEBUG CMAKE_MODULE_LINKER_FLAGS_MINSIZEREL CMAKE_MODULE_LINKER_FLAGS_RELEASE CMAKE_MODULE_LINKER_FLAGS_RELWITHDEBINFO \
    CMAKE_SHARED_LINKER_FLAGS CMAKE_SHARED_LINKER_FLAGS_DEBUG CMAKE_SHARED_LINKER_FLAGS_MINSIZEREL CMAKE_SHARED_LINKER_FLAGS_RELEASE CMAKE_SHARED_LINKER_FLAGS_RELWITHDEBINFO; do
    grep -Fxq "${linker_flags}:STRING=" "${cache_file}" || p0_die "linker flags drift: ${linker_flags}" 65
done
if ! grep -Fxq "CMAKE_C_COMPILER:FILEPATH=${CC_BIN}" "${cache_file}" && \
   ! grep -Fxq "CMAKE_C_COMPILER:STRING=${CC_BIN}" "${cache_file}"; then
    p0_die 'configured C compiler differs from /usr/bin/gcc' 65
fi
if ! grep -Fxq "CMAKE_CXX_COMPILER:FILEPATH=${CXX_BIN}" "${cache_file}" && \
   ! grep -Fxq "CMAKE_CXX_COMPILER:STRING=${CXX_BIN}" "${cache_file}"; then
    p0_die 'configured C++ compiler differs from /usr/bin/g++' 65
fi
grep -Fxq "CMAKE_LINKER:FILEPATH=${LINKER_BIN}" "${cache_file}" || p0_die 'configured linker differs from /usr/bin/ld' 65

declare -a required_packages=(CURL Fluidsynth Fontconfig Freetype Harfbuzz ICU LZO LibLZMA Ogg OpenGL Opus OpusFile PNG ZLIB)
for required_package in "${required_packages[@]}"; do
    grep -Eq "^FIND_PACKAGE_MESSAGE_DETAILS_${required_package}:INTERNAL=.+" "${cache_file}" || p0_die "required feature library was not detected: ${required_package}" 65
done
for feature_definition in WITH_PNG WITH_ZLIB WITH_LIBLZMA WITH_LZO WITH_CURL WITH_FLUIDSYNTH WITH_SDL2 WITH_FREETYPE WITH_FONTCONFIG WITH_HARFBUZZ WITH_ICU_I18N WITH_ICU_UC WITH_OPUSFILE WITH_OPENGL WITH_SSE; do
    grep -Fq -- "-D${feature_definition}" "${ARTIFACT_ROOT}/logs/configure-reference.stdout.log" || p0_die "required compiled feature definition is missing: ${feature_definition}" 65
done
grep -Eq '^SDL2_DIR:PATH=.+$' "${cache_file}" || p0_die 'required SDL2 feature library was not detected' 65
if grep -Eq '^SDL2_DIR:PATH=.*NOTFOUND$' "${cache_file}"; then
    p0_die 'required SDL2 feature library resolved to NOTFOUND' 65
fi

cache_variables="${ARTIFACT_ROOT}/logs/configure-reference.cache-variables.txt"
if "${CMAKE_BIN}" -LAH -N "${BUILD_ROOT}" >"${cache_variables}" 2>"${ARTIFACT_ROOT}/logs/configure-reference.cache.stderr.log"; then
    cache_rc=0
else
    cache_rc=$?
fi
((cache_rc == 0)) || p0_die "failed to enumerate CMake cache variables with exit ${cache_rc}" "${cache_rc}"

dependencies_file="${ARTIFACT_ROOT}/logs/configure-reference.detected-dependencies.txt"
grep -E '(^|_)(DIR|INCLUDE_DIR|INCLUDE_DIRS|LIBRARY|LIBRARIES|VERSION)(:|=)' "${cache_variables}" >"${dependencies_file}" || :

post_changes=$(git -C "${SOURCE_ROOT}" status --porcelain=v1 --untracked-files=all)
[[ -z "${post_changes}" ]] || p0_die 'configuration modified the source worktree' 65

cache_sha256=$(p0_sha256_file "${cache_file}")
cache_variables_sha256=$(p0_sha256_file "${cache_variables}")
dependencies_sha256=$(p0_sha256_file "${dependencies_file}")
cmake_version=$("${CMAKE_BIN}" --version | sed -n -E '1s/^cmake version ([0-9]+\.[0-9]+\.[0-9]+).*/\1/p')
ninja_version=$(ninja --version)
cxx_version=$("${CXX_BIN}" -dumpfullversion -dumpversion)
linker_version=$("${LINKER_BIN}" --version | sed -n '1p')

python3 - "${ARTIFACT_ROOT}/manifests/configure-reference.json" \
    "${ARTIFACT_ROOT}/commands/configure-reference-cmake.json" "${source_commit}" \
    "${cache_sha256}" "${cache_variables_sha256}" "${dependencies_sha256}" \
    "${cmake_version}" "${ninja_version}" "${cxx_version}" "${linker_version}" \
    "${SOURCE_ROOT}" "${BUILD_ROOT}" "${INSTALL_ROOT}" "${cache_file}" \
    "${cache_variables}" "${dependencies_file}" <<'PY'
import json
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
actual_command = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
replacements = [
    (sys.argv[11], "$SOURCE_ROOT"),
    (sys.argv[12], "$BUILD_ROOT"),
    (sys.argv[13], "$INSTALL_ROOT"),
]
role_command = []
for argument in actual_command:
    for concrete, role in replacements:
        argument = argument.replace(concrete, role)
    role_command.append(argument)
value = {
    "authoritative": {
        "compiled_directories": {
            "GLOBAL_DIR": "$INSTALL_ROOT/share/games/openttd",
            "HOST_BINARY_DIR": "",
            "PERSONAL_DIR": ".openttd",
            "SHARED_DIR": "(not set)",
        },
        "compiled_features": [
            "WITH_CURL", "WITH_FLUIDSYNTH", "WITH_FONTCONFIG", "WITH_FREETYPE", "WITH_HARFBUZZ",
            "WITH_ICU_I18N", "WITH_ICU_UC", "WITH_LIBLZMA", "WITH_LZO", "WITH_OPENGL",
            "WITH_OPUSFILE", "WITH_PNG", "WITH_SDL2", "WITH_SSE", "WITH_ZLIB",
        ],
        "cmake_options": {
            "CMAKE_C_COMPILER": "/usr/bin/gcc",
            "CMAKE_BUILD_TYPE": "RelWithDebInfo",
            "CMAKE_CXX_COMPILER": "/usr/bin/g++",
            "CMAKE_INSTALL_PREFIX": "$INSTALL_ROOT",
            "CMAKE_CXX_FLAGS": "",
            "CMAKE_CXX_FLAGS_DEBUG": "-g",
            "CMAKE_CXX_FLAGS_MINSIZEREL": "-Os -DNDEBUG",
            "CMAKE_CXX_FLAGS_RELEASE": "-O3 -DNDEBUG",
            "CMAKE_CXX_FLAGS_RELWITHDEBINFO": "-O2 -g -DNDEBUG",
            "CMAKE_EXE_LINKER_FLAGS": "",
            "CMAKE_MODULE_LINKER_FLAGS": "",
            "CMAKE_SHARED_LINKER_FLAGS": "",
            "OPTION_ALLOW_INVALID_SIGNATURE": False,
            "OPTION_DEDICATED": False,
            "OPTION_DOCS_ONLY": False,
            "OPTION_DOXYGEN_AI_WARN_FILE": "",
            "OPTION_DOXYGEN_GS_WARN_FILE": "",
            "OPTION_DOXYGEN_WARN_FILE": "",
            "OPTION_FORCE_COLORED_OUTPUT": False,
            "OPTION_INSTALL_FHS": True,
            "OPTION_LINE_IN_DOXYGEN_WARNINGS": True,
            "OPTION_PACKAGE_DEPENDENCIES": False,
            "OPTION_SURVEY_KEY": "",
            "OPTION_TOOLS_ONLY": False,
            "OPTION_USE_ASSERTS": True,
            "OPTION_USE_NSIS": False,
        },
        "command": role_command,
        "environment": {
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "P0_PROFILE": os.environ["P0_PROFILE"],
            "PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": os.environ["SOURCE_DATE_EPOCH"], "TZ": "UTC",
        },
        "generator": "Ninja",
        "source_commit": sys.argv[3],
        "toolchain": {"cmake": sys.argv[7], "cxx": sys.argv[9], "linker": sys.argv[10], "ninja": sys.argv[8]},
    },
    "diagnostics": {
        "actual_command": actual_command,
        "build_root": sys.argv[12], "cache_file": sys.argv[14], "cache_sha256": sys.argv[4],
        "cache_variables": sys.argv[15], "cache_variables_sha256": sys.argv[5],
        "dependencies": sys.argv[16], "dependencies_sha256": sys.argv[6],
        "install_root": sys.argv[13], "source_root": sys.argv[11],
    },
    "return_code": 0,
    "status": "PASS",
}
path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
p0_json_canonicalize_in_place "${ARTIFACT_ROOT}/manifests/configure-reference.json" "${ARTIFACT_ROOT}"

p0_finish 'PASS' 0 'fresh frozen reference configuration completed and verified'
