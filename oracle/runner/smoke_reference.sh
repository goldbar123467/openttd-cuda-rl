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
Usage: smoke_reference.sh --install-root ABSOLUTE_PATH
                          --artifact-root ABSOLUTE_PATH
                          --build-manifest ABSOLUTE_PATH

Verifies executable/content digests and the frozen runtime version before
running exactly:
  openttd -g -v null:ticks=128 -s null -m null -b null -I OpenGFX -Q -x

The exact command is bounded by an external 120-second timeout. Help output is
retained as the version, OpenGFX identity, and available driver inventory.
EOF
    p0_show_common_help_note
}

INSTALL_ROOT=''
ARTIFACT_ROOT=''
BUILD_MANIFEST=''
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
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
        --build-manifest)
            (($# >= 2)) || p0_usage_error '--build-manifest requires a value'
            BUILD_MANIFEST=$2
            shift 2
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
    "${INSTALL_ROOT}|--install-root" \
    "${ARTIFACT_ROOT}|--artifact-root" \
    "${BUILD_MANIFEST}|--build-manifest"; do
    p0_require_absolute_path "${path_and_label%%|*}" "${path_and_label#*|}"
done
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
INSTALL_ROOT=$(p0_realpath "${INSTALL_ROOT}")
BUILD_MANIFEST=$(p0_realpath "${BUILD_MANIFEST}")
p0_assert_under_root "${INSTALL_ROOT}" "${ARTIFACT_ROOT}" no
p0_assert_under_root "${BUILD_MANIFEST}" "${ARTIFACT_ROOT}" no

p0_initialize 'smoke-reference' "${ARTIFACT_ROOT}" 'smoke-reference.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/smoke-reference.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in python3 sha256sum timeout sed grep; do
    p0_require_command "${tool}"
done
p0_require_result_pass "${BUILD_MANIFEST}"

executable="${INSTALL_ROOT}/games/openttd"
content_file="${INSTALL_ROOT}/share/games/openttd/baseset/${P0_OPENGFX_INSTALLED_NAME}"
[[ -x "${executable}" && -f "${executable}" && ! -L "${executable}" ]] || p0_die "missing regular installed OpenTTD executable: ${executable}" 66
p0_require_sha256 "${content_file}" "${P0_OPENGFX_INSTALLED_SHA256}" 'smoke OpenGFX content'
expected_executable_sha256=$(python3 - "${BUILD_MANIFEST}" "${INSTALL_ROOT}" "${P0_EXPECTED_SUBMODULE_COMMIT}" <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("diagnostics", {}).get("install_root") != sys.argv[2]:
    raise SystemExit("build manifest install root does not match")
if value.get("authoritative", {}).get("source_commit") != sys.argv[3]:
    raise SystemExit("build manifest source commit does not match")
digest = value.get("authoritative", {}).get("executable", {}).get("sha256")
if not isinstance(digest, str) or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
    raise SystemExit("build manifest executable digest is malformed or omitted")
print(digest)
PY
)
p0_require_sha256 "${executable}" "${expected_executable_sha256}" 'smoke executable'

help_stdout="${ARTIFACT_ROOT}/logs/smoke-reference.help.stdout.log"
help_stderr="${ARTIFACT_ROOT}/logs/smoke-reference.help.stderr.log"
help_xdg_root="${ARTIFACT_ROOT}/smoke-help-xdg"
p0_safe_reset_dir "${help_xdg_root}" "${ARTIFACT_ROOT}"
mkdir -p -- "${help_xdg_root}/config" "${help_xdg_root}/data"
if XDG_CONFIG_HOME="${help_xdg_root}/config" \
    XDG_DATA_HOME="${help_xdg_root}/data" \
    "${executable}" -h >"${help_stdout}" 2>"${help_stderr}"; then
    help_rc=0
else
    help_rc=$?
fi
((help_rc == 0)) || p0_die "OpenTTD help probe failed with exit ${help_rc}" "${help_rc}"
runtime_version=$(sed -n '1p' "${help_stdout}")
[[ "${runtime_version}" == "${P0_EXPECTED_OPENTTD_VERSION}" ]] || p0_die "runtime version drift: expected ${P0_EXPECTED_OPENTTD_VERSION}, got ${runtime_version}" 65
grep -Fq 'OpenGFX base graphics set for OpenTTD.' "${help_stdout}" || p0_die 'OpenGFX content profile is missing from OpenTTD inventory' 65
grep -Fq '[OpenGFX 8.0]' "${help_stdout}" || p0_die 'installed OpenGFX identity differs from version 8.0' 65

capabilities_file="${ARTIFACT_ROOT}/results/smoke-reference-capabilities.json"
python3 - "${help_stdout}" "${capabilities_file}" <<'PY'
import json
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
sections = {}
for kind in ("music", "sound", "video", "blitter"):
    heading = "List of blitters:" if kind == "blitter" else f"List of {kind} drivers:"
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?:\n\n|\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(f"missing {kind} capability section")
    names = []
    for line in match.group(1).splitlines():
        if ":" in line:
            names.append(line.split(":", 1)[0].strip())
    if "null" not in names:
        raise SystemExit(f"null {kind} capability is unavailable")
    sections[kind] = names
version = text.splitlines()[0] if text.splitlines() else ""
value = {"drivers": sections, "opengfx": {"name": "OpenGFX", "version": "8.0"}, "version": version}
pathlib.Path(sys.argv[2]).write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
p0_json_canonicalize_in_place "${capabilities_file}" "${ARTIFACT_ROOT}"

declare -a smoke_command=(
    "${executable}"
    -g
    -v null:ticks=128
    -s null
    -m null
    -b null
    -I OpenGFX
    -Q
    -x
)
declare -a timeout_command=(timeout --signal=TERM --kill-after=10s 120s "${smoke_command[@]}")
p0_write_command_array "${ARTIFACT_ROOT}/commands/smoke-reference-openttd.json" "${smoke_command[@]}"
p0_write_command_array "${ARTIFACT_ROOT}/commands/smoke-reference-timeout-wrapper.json" "${timeout_command[@]}"
smoke_work="${ARTIFACT_ROOT}/smoke-work"
p0_safe_reset_dir "${smoke_work}" "${ARTIFACT_ROOT}"
smoke_xdg_root="${ARTIFACT_ROOT}/smoke-xdg"
p0_safe_reset_dir "${smoke_xdg_root}" "${ARTIFACT_ROOT}"
mkdir -p -- "${smoke_xdg_root}/config" "${smoke_xdg_root}/data"

smoke_started_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
smoke_started_epoch=$(date -u +%s)
p0_log INFO 'running the exact 128-tick null video/sound/music/blitter headless profile'
if (
    cd -- "${smoke_work}"
    XDG_CONFIG_HOME="${smoke_xdg_root}/config" \
    XDG_DATA_HOME="${smoke_xdg_root}/data" \
        "${timeout_command[@]}"
) >"${ARTIFACT_ROOT}/logs/smoke-reference.stdout.log" 2>"${ARTIFACT_ROOT}/logs/smoke-reference.stderr.log"; then
    smoke_rc=0
else
    smoke_rc=$?
fi
smoke_finished_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
smoke_finished_epoch=$(date -u +%s)
smoke_duration=$((smoke_finished_epoch - smoke_started_epoch))
capabilities_sha256=$(p0_sha256_file "${capabilities_file}")
stdout_sha256=$(p0_sha256_file "${ARTIFACT_ROOT}/logs/smoke-reference.stdout.log")
stderr_sha256=$(p0_sha256_file "${ARTIFACT_ROOT}/logs/smoke-reference.stderr.log")

python3 - "${ARTIFACT_ROOT}/manifests/smoke-reference.json" \
    "${ARTIFACT_ROOT}/commands/smoke-reference-openttd.json" \
    "${expected_executable_sha256}" "${runtime_version}" "${P0_OPENGFX_INSTALLED_SHA256}" \
    "${smoke_rc}" "${smoke_started_at}" "${smoke_finished_at}" "${smoke_duration}" \
    "${executable}" "${content_file}" "${capabilities_file}" \
    "${ARTIFACT_ROOT}/logs/smoke-reference.stdout.log" \
    "${ARTIFACT_ROOT}/logs/smoke-reference.stderr.log" \
    "${capabilities_sha256}" "${stdout_sha256}" "${stderr_sha256}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
actual_command = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
command = [argument.replace(sys.argv[10], "$INSTALL_ROOT/games/openttd") for argument in actual_command]
value = {
    "authoritative": {
        "command": command,
        "behavior": {
            "capabilities_sha256": sys.argv[15], "return_code": int(sys.argv[6]),
            "stderr_sha256": sys.argv[17], "stdout_sha256": sys.argv[16],
        },
        "content": {"name": "OpenGFX", "sha256": sys.argv[5], "version": "8.0"},
        "executable": {"sha256": sys.argv[3], "version": sys.argv[4]},
    },
    "diagnostics": {
        "actual_command": actual_command,
        "capabilities": sys.argv[12], "content_file": sys.argv[11],
        "duration_seconds": int(sys.argv[9]), "executable_path": sys.argv[10],
        "finished_at": sys.argv[8], "started_at": sys.argv[7],
        "runtime_environment": {"XDG_CONFIG_HOME": "$ARTIFACT_ROOT/smoke-xdg/config", "XDG_DATA_HOME": "$ARTIFACT_ROOT/smoke-xdg/data"},
        "stderr": sys.argv[14], "stdout": sys.argv[13],
    },
    "return_code": int(sys.argv[6]),
    "status": "PASS" if int(sys.argv[6]) == 0 else "FAIL",
}
path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
p0_json_canonicalize_in_place "${ARTIFACT_ROOT}/manifests/smoke-reference.json" "${ARTIFACT_ROOT}"

python3 - "${ARTIFACT_ROOT}/manifests/smoke-reference.json" \
    "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/build-relwithdebinfo.json" <<'PY'
import json
import pathlib
import sys

actual = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["authoritative"]
baseline = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))["invocations"]
if actual.get("command") != baseline.get("smoke"):
    raise SystemExit("recorded smoke command differs from the frozen logical invocation")
PY

((smoke_rc == 0)) || p0_die "headless smoke failed with exit ${smoke_rc}; logs were retained" "${smoke_rc}"
p0_finish 'PASS' 0 "exact headless smoke passed in ${smoke_duration} seconds"
