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
Usage: build_reference.sh --build-root ABSOLUTE_PATH
                          --install-root ABSOLUTE_PATH
                          --artifact-root ABSOLUTE_PATH
                          --configuration-manifest ABSOLUTE_PATH
                         [--parallel 1..64]

Tests may set P0_TEST_MODE=1 and pass --test-configuration-override for a
deliberately minimal or mutated configuration statement below artifact-root.
Production accepts only the canonical configure-reference manifest emitted by
the preceding stage.

Requires the verified OpenGFX payload at BUILD_ROOT/baseset/opengfx-8.0.tar.
The install root is safely reset below artifact-root, then Ninja builds the
fresh configuration and CMake installs it. Default parallelism is min(CPUs, 16).
EOF
    p0_show_common_help_note
}

BUILD_ROOT=''
INSTALL_ROOT=''
ARTIFACT_ROOT=''
CONFIGURATION_MANIFEST=''
PARALLEL=''
TEST_CONFIGURATION_OVERRIDE=0
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
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
        --configuration-manifest)
            (($# >= 2)) || p0_usage_error '--configuration-manifest requires a value'
            CONFIGURATION_MANIFEST=$2
            shift 2
            ;;
        --parallel)
            (($# >= 2)) || p0_usage_error '--parallel requires a value'
            PARALLEL=$2
            shift 2
            ;;
        --test-configuration-override)
            [[ "${P0_TEST_MODE:-0}" == 1 ]] || p0_usage_error '--test-configuration-override requires P0_TEST_MODE=1'
            TEST_CONFIGURATION_OVERRIDE=1
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
    "${BUILD_ROOT}|--build-root" \
    "${INSTALL_ROOT}|--install-root" \
    "${ARTIFACT_ROOT}|--artifact-root" \
    "${CONFIGURATION_MANIFEST}|--configuration-manifest"; do
    p0_require_absolute_path "${path_and_label%%|*}" "${path_and_label#*|}"
done
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
BUILD_ROOT=$(p0_realpath "${BUILD_ROOT}")
INSTALL_ROOT=$(p0_realpath "${INSTALL_ROOT}")
CONFIGURATION_MANIFEST=$(p0_realpath "${CONFIGURATION_MANIFEST}")
p0_assert_under_root "${BUILD_ROOT}" "${ARTIFACT_ROOT}" no
p0_assert_under_root "${INSTALL_ROOT}" "${ARTIFACT_ROOT}" no
p0_assert_under_root "${CONFIGURATION_MANIFEST}" "${ARTIFACT_ROOT}" no
[[ "${BUILD_ROOT}" != "${INSTALL_ROOT}" ]] || p0_usage_error 'build and install roots must differ'
if ((TEST_CONFIGURATION_OVERRIDE == 0)); then
    [[ "${CONFIGURATION_MANIFEST}" == "${ARTIFACT_ROOT}/manifests/configure-reference.json" ]] \
        || p0_usage_error 'production configuration manifest must be ARTIFACT_ROOT/manifests/configure-reference.json'
fi

if [[ -z "${PARALLEL}" ]]; then
    detected_processors=$(getconf _NPROCESSORS_ONLN)
    if ((detected_processors > 16)); then
        PARALLEL=16
    else
        PARALLEL=${detected_processors}
    fi
fi
[[ "${PARALLEL}" =~ ^[0-9]+$ ]] || p0_usage_error '--parallel must be an integer'
((PARALLEL >= 1 && PARALLEL <= 64)) || p0_usage_error '--parallel must be between 1 and 64'

p0_initialize 'build-reference' "${ARTIFACT_ROOT}" 'build-reference.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/build-reference.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in cmake ninja ldd sha256sum stat python3 grep getconf jq; do
    p0_require_command "${tool}"
done

p0_require_result_pass "${CONFIGURATION_MANIFEST}"
if ((TEST_CONFIGURATION_OVERRIDE == 0)); then
    p0_require_canonical_json "${CONFIGURATION_MANIFEST}" "${ARTIFACT_ROOT}"
fi
python3 - "${CONFIGURATION_MANIFEST}" "${BUILD_ROOT}" "${INSTALL_ROOT}" "${P0_EXPECTED_SUBMODULE_COMMIT}" \
    "${TEST_CONFIGURATION_OVERRIDE}" "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/build-relwithdebinfo.json" \
    "${P0_REPOSITORY_ROOT}/openttd-upstream" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
diagnostics = value.get("diagnostics", {})
authoritative = value.get("authoritative", {})
if diagnostics.get("build_root") != sys.argv[2]:
    raise SystemExit("configuration manifest build root does not match")
if diagnostics.get("install_root") != sys.argv[3]:
    raise SystemExit("configuration manifest install root does not match")
if authoritative.get("source_commit") != sys.argv[4]:
    raise SystemExit("configuration manifest source commit does not match frozen pin")
if sys.argv[5] == "0":
    baseline = json.loads(pathlib.Path(sys.argv[6]).read_text(encoding="utf-8"))
    if diagnostics.get("source_root") != sys.argv[7]:
        raise SystemExit("configuration manifest source root is not the pinned submodule")
    if authoritative.get("command") != baseline.get("invocations", {}).get("configure"):
        raise SystemExit("configuration manifest command differs from frozen build profile")
    expected_options = {
        item["name"]: item["value"] for item in baseline.get("configuration", {}).get("options", [])
    }
    actual_options = dict(authoritative.get("cmake_options", {}))
    actual_options.update(authoritative.get("compiled_directories", {}))
    if actual_options != expected_options:
        raise SystemExit("configuration manifest option projection differs from frozen build profile")
    if authoritative.get("compiled_features") != baseline.get("configuration", {}).get("feature_definitions"):
        raise SystemExit("configuration manifest feature projection differs from frozen build profile")
    if authoritative.get("generator") != baseline.get("configuration", {}).get("generator"):
        raise SystemExit("configuration manifest generator differs from frozen build profile")
    expected_environment = {
        item["name"]: item["value"]
        for item in baseline.get("environment", [])
        if item.get("identity_affecting") is True
    }
    if authoritative.get("environment") != expected_environment:
        raise SystemExit("configuration manifest environment differs from frozen build profile")
PY

cache_file="${BUILD_ROOT}/CMakeCache.txt"
[[ -f "${cache_file}" ]] || p0_die 'valid configuration manifest has no corresponding CMake cache' 66
if ((TEST_CONFIGURATION_OVERRIDE == 0)); then
    p0_require_commit "${P0_REPOSITORY_ROOT}/openttd-upstream" "${P0_EXPECTED_SUBMODULE_COMMIT}"
    p0_require_clean_submodule "${P0_REPOSITORY_ROOT}/openttd-upstream"
    recorded_cache_sha256=$(python3 - "${CONFIGURATION_MANIFEST}" <<'PY'
import json
import pathlib
import sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
digest = value.get("diagnostics", {}).get("cache_sha256")
if not isinstance(digest, str):
    raise SystemExit("configuration manifest omits cache digest")
print(digest)
PY
)
    p0_require_sha256 "${cache_file}" "${recorded_cache_sha256}" 'configured cache chain of custody'
fi
configuration_manifest_sha256=$(p0_sha256_file "${CONFIGURATION_MANIFEST}")
grep -Fxq 'CMAKE_BUILD_TYPE:STRING=RelWithDebInfo' "${cache_file}" || p0_die 'build cache profile drift: CMAKE_BUILD_TYPE' 65
grep -Fxq 'CMAKE_GENERATOR:INTERNAL=Ninja' "${cache_file}" || p0_die 'build cache profile drift: generator' 65
grep -Fxq 'OPTION_DEDICATED:BOOL=OFF' "${cache_file}" || p0_die 'build cache profile drift: dedicated mode' 65
grep -Fxq 'OPTION_INSTALL_FHS:BOOL=ON' "${cache_file}" || p0_die 'build cache profile drift: FHS mode' 65
grep -Fxq 'OPTION_USE_ASSERTS:BOOL=ON' "${cache_file}" || p0_die 'build cache profile drift: assertions' 65
grep -Fxq "CMAKE_INSTALL_PREFIX:PATH=${INSTALL_ROOT}" "${cache_file}" || p0_die 'build cache profile drift: install root' 65

content_file="${BUILD_ROOT}/baseset/${P0_OPENGFX_INSTALLED_NAME}"
p0_require_sha256 "${content_file}" "${P0_OPENGFX_INSTALLED_SHA256}" 'build-tree OpenGFX content'

build_executable="${BUILD_ROOT}/openttd"
[[ ! -e "${build_executable}" ]] || p0_die 'fresh configuration unexpectedly contains a stale OpenTTD executable' 65
p0_safe_reset_dir "${INSTALL_ROOT}" "${ARTIFACT_ROOT}"

declare -a build_command=(/usr/bin/cmake --build "${BUILD_ROOT}" --parallel "${PARALLEL}")
declare -a install_command=(/usr/bin/cmake --install "${BUILD_ROOT}")
p0_write_command_array "${ARTIFACT_ROOT}/commands/build-reference-cmake.json" "${build_command[@]}"
p0_write_command_array "${ARTIFACT_ROOT}/commands/install-reference-cmake.json" "${install_command[@]}"

build_started_epoch=$(date -u +%s)
p0_log INFO "building the reference through Ninja with bounded parallelism ${PARALLEL}"
if "${build_command[@]}" >"${ARTIFACT_ROOT}/logs/build-reference.stdout.log" 2>"${ARTIFACT_ROOT}/logs/build-reference.stderr.log"; then
    build_rc=0
else
    build_rc=$?
fi
((build_rc == 0)) || p0_die "reference build failed with exit ${build_rc}; no stale executable was accepted" "${build_rc}"

[[ -x "${build_executable}" && -f "${build_executable}" && ! -L "${build_executable}" ]] || p0_die 'Ninja reported success without a regular executable' 70
build_mtime=$(stat -c %Y -- "${build_executable}")
((build_mtime >= build_started_epoch - 1)) || p0_die 'built executable predates the current build invocation' 65

p0_log INFO 'installing the just-built reference into the freshly reset FHS root'
if "${install_command[@]}" >"${ARTIFACT_ROOT}/logs/install-reference.stdout.log" 2>"${ARTIFACT_ROOT}/logs/install-reference.stderr.log"; then
    install_rc=0
else
    install_rc=$?
fi
((install_rc == 0)) || p0_die "reference install failed with exit ${install_rc}" "${install_rc}"

installed_executable="${INSTALL_ROOT}/games/openttd"
[[ -x "${installed_executable}" && -f "${installed_executable}" && ! -L "${installed_executable}" ]] || p0_die "installed executable is missing from the frozen FHS path: ${installed_executable}" 70
installed_content="${INSTALL_ROOT}/share/games/openttd/baseset/${P0_OPENGFX_INSTALLED_NAME}"
p0_require_sha256 "${installed_content}" "${P0_OPENGFX_INSTALLED_SHA256}" 'installed OpenGFX content'

installed_tree_manifest="${ARTIFACT_ROOT}/manifests/installed-tree.json"
python3 - "${INSTALL_ROOT}" "${installed_tree_manifest}" <<'PY'
import hashlib
import json
import pathlib
import stat
import sys

root = pathlib.Path(sys.argv[1])
records = []
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    if path.is_symlink():
        raise SystemExit(f"installed tree contains a symlink: {path.relative_to(root)}")
    mode = path.stat().st_mode
    if stat.S_ISDIR(mode):
        continue
    if not stat.S_ISREG(mode):
        raise SystemExit(f"installed tree contains a special file: {path.relative_to(root)}")
    data = path.read_bytes()
    records.append({
        "executable": bool(mode & 0o111),
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    })
value = {"files": records, "root_role": "$INSTALL_ROOT"}
pathlib.Path(sys.argv[2]).write_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
PY
p0_require_canonical_json "${installed_tree_manifest}" "${ARTIFACT_ROOT}"
installed_tree_sha256=$(p0_sha256_file "${installed_tree_manifest}")
installed_tree_file_count=$(jq -er '.files | length' "${installed_tree_manifest}")

ldd_log="${ARTIFACT_ROOT}/logs/build-reference.ldd.log"
if ldd "${installed_executable}" >"${ldd_log}" 2>"${ARTIFACT_ROOT}/logs/build-reference.ldd.stderr.log"; then
    ldd_rc=0
else
    ldd_rc=$?
fi
((ldd_rc == 0)) || p0_die "ldd failed for installed executable with exit ${ldd_rc}" "${ldd_rc}"
if grep -Fq 'not found' "${ldd_log}"; then
    p0_die 'installed executable has an unresolved shared library' 65
fi

binary_sha256=$(p0_sha256_file "${installed_executable}")
binary_size=$(stat -c %s -- "${installed_executable}")
ldd_sha256=$(p0_sha256_file "${ldd_log}")
probe_xdg_root="${ARTIFACT_ROOT}/build-probe-xdg"
p0_safe_reset_dir "${probe_xdg_root}" "${ARTIFACT_ROOT}"
mkdir -p -- "${probe_xdg_root}/config" "${probe_xdg_root}/data"
if XDG_CONFIG_HOME="${probe_xdg_root}/config" \
    XDG_DATA_HOME="${probe_xdg_root}/data" \
    "${installed_executable}" -h >"${ARTIFACT_ROOT}/logs/build-reference.help.stdout.log" 2>"${ARTIFACT_ROOT}/logs/build-reference.help.stderr.log"; then
    help_rc=0
else
    help_rc=$?
fi
((help_rc == 0)) || p0_die "installed executable help/version probe failed with exit ${help_rc}" "${help_rc}"
runtime_version=$(sed -n '1p' "${ARTIFACT_ROOT}/logs/build-reference.help.stdout.log")
[[ "${runtime_version}" == "${P0_EXPECTED_OPENTTD_VERSION}" ]] || p0_die "runtime version drift: expected ${P0_EXPECTED_OPENTTD_VERSION}, got ${runtime_version}" 65

python3 - "${ARTIFACT_ROOT}/manifests/build-reference.json" \
    "${ARTIFACT_ROOT}/commands/build-reference-cmake.json" \
    "${ARTIFACT_ROOT}/commands/install-reference-cmake.json" \
    "${P0_EXPECTED_SUBMODULE_COMMIT}" "${PARALLEL}" "${binary_sha256}" \
    "${binary_size}" "${runtime_version}" "${P0_OPENGFX_INSTALLED_SHA256}" \
    "${BUILD_ROOT}" "${INSTALL_ROOT}" "${installed_executable}" "${ldd_log}" \
    "${ldd_sha256}" "${configuration_manifest_sha256}" \
    "${installed_tree_sha256}" "${installed_tree_file_count}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
actual_build_command = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
actual_install_command = json.loads(pathlib.Path(sys.argv[3]).read_text(encoding="utf-8"))
def normalize(command):
    replacements = [(sys.argv[10], "$BUILD_ROOT"), (sys.argv[11], "$INSTALL_ROOT")]
    result = []
    for argument in command:
        for concrete, role in replacements:
            argument = argument.replace(concrete, role)
        result.append(argument)
    if "--parallel" in result:
        parallel_index = result.index("--parallel") + 1
        if parallel_index >= len(result):
            raise SystemExit("recorded build command omits the parallelism argument")
        result[parallel_index] = "$P0_JOBS"
    return result
value = {
    "authoritative": {
        "build_command": normalize(actual_build_command),
        "executable": {"sha256": sys.argv[6], "size": int(sys.argv[7]), "version": sys.argv[8]},
        "install_command": normalize(actual_install_command),
        "installed_tree": {"file_count": int(sys.argv[17]), "manifest_sha256": sys.argv[16]},
        "opengfx_sha256": sys.argv[9],
        "source_commit": sys.argv[4],
    },
    "diagnostics": {
        "actual_build_command": actual_build_command, "actual_install_command": actual_install_command,
        "build_root": sys.argv[10], "executable_path": sys.argv[12],
        "configuration_manifest_sha256": sys.argv[15],
        "install_root": sys.argv[11], "ldd_log": sys.argv[13], "ldd_log_sha256": sys.argv[14],
        "parallelism": int(sys.argv[5]),
        "runtime_probe_environment": {"XDG_CONFIG_HOME": "$ARTIFACT_ROOT/build-probe-xdg/config", "XDG_DATA_HOME": "$ARTIFACT_ROOT/build-probe-xdg/data"},
    },
    "return_code": 0,
    "status": "PASS",
}
path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
p0_json_canonicalize_in_place "${ARTIFACT_ROOT}/manifests/build-reference.json" "${ARTIFACT_ROOT}"

python3 - "${ARTIFACT_ROOT}/manifests/build-reference.json" \
    "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/build-relwithdebinfo.json" <<'PY'
import json
import pathlib
import sys

actual = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["authoritative"]
baseline = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))["invocations"]
if actual.get("build_command") != baseline.get("build"):
    raise SystemExit("recorded build command differs from the frozen logical invocation")
if actual.get("install_command") != baseline.get("install"):
    raise SystemExit("recorded install command differs from the frozen logical invocation")
PY

p0_finish 'PASS' 0 "reference built and installed; executable SHA-256 ${binary_sha256}"
