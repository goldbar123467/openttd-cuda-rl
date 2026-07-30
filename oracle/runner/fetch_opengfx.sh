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
Usage: fetch_opengfx.sh --destination ABSOLUTE_PATH
                        --artifact-root ABSOLUTE_PATH

Downloads the frozen OpenGFX 8.0 HTTPS archive, verifies its SHA-256 before any
extraction, validates every archive member, and atomically installs
opengfx-8.0.tar into the destination. The destination must be below the artifact
root. Existing identical content is accepted; differing content is never
overwritten.

Tests may set P0_TEST_MODE=1 and pass --input-archive ABSOLUTE_PATH. That hook
never performs network access and only accepts an archive below artifact-root.
EOF
    p0_show_common_help_note
}

DESTINATION=''
ARTIFACT_ROOT=''
INPUT_ARCHIVE=''
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
        --destination)
            (($# >= 2)) || p0_usage_error '--destination requires a value'
            DESTINATION=$2
            shift 2
            ;;
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --input-archive)
            (($# >= 2)) || p0_usage_error '--input-archive requires a value'
            INPUT_ARCHIVE=$2
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

p0_require_absolute_path "${ARTIFACT_ROOT}" '--artifact-root'
p0_require_absolute_path "${DESTINATION}" '--destination'
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
DESTINATION=$(p0_realpath "${DESTINATION}")
p0_assert_under_root "${DESTINATION}" "${ARTIFACT_ROOT}" no
if [[ -n "${INPUT_ARCHIVE}" ]]; then
    [[ "${P0_TEST_MODE:-0}" == 1 ]] || p0_usage_error '--input-archive is restricted to P0_TEST_MODE=1'
    p0_require_absolute_path "${INPUT_ARCHIVE}" '--input-archive'
    INPUT_ARCHIVE=$(p0_realpath "${INPUT_ARCHIVE}")
    p0_assert_under_root "${INPUT_ARCHIVE}" "${ARTIFACT_ROOT}" no
fi

p0_initialize 'fetch-opengfx' "${ARTIFACT_ROOT}" 'fetch-opengfx.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/fetch-opengfx.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in curl python3 unzip sha256sum find sort mktemp mv cp; do
    p0_require_command "${tool}"
done

[[ "${P0_OPENGFX_ARCHIVE_URL}" == https://* ]] || p0_die 'frozen OpenGFX URL is not HTTPS' 70
mkdir -p -- "${DESTINATION}"

temp_dir=$(p0_make_temp_dir "${ARTIFACT_ROOT}" 'opengfx')
cleanup() {
    if [[ -n "${temp_dir:-}" && -d "${temp_dir}" ]]; then
        p0_safe_remove_tree "${temp_dir}" "${ARTIFACT_ROOT}"
    fi
}
trap cleanup EXIT

archive_path="${temp_dir}/${P0_OPENGFX_ARCHIVE_NAME}.partial"
if [[ -n "${INPUT_ARCHIVE}" ]]; then
    [[ -f "${INPUT_ARCHIVE}" && ! -L "${INPUT_ARCHIVE}" ]] || p0_die 'test input archive must be a regular non-symlink file' 66
    cp -- "${INPUT_ARCHIVE}" "${archive_path}"
    p0_log INFO 'using the explicit test archive without network access'
else
    declare -a curl_command=(
        curl
        --fail
        --show-error
        --silent
        --location
        --max-redirs 5
        --connect-timeout 15
        --max-time 300
        --retry 3
        --retry-delay 2
        --retry-max-time 180
        --retry-all-errors
        --proto '=https'
        --tlsv1.2
        --output "${archive_path}"
        "${P0_OPENGFX_ARCHIVE_URL}"
    )
    p0_write_command_array "${ARTIFACT_ROOT}/commands/fetch-opengfx-curl.json" "${curl_command[@]}"
    p0_log INFO "downloading ${P0_OPENGFX_ARCHIVE_NAME} from the frozen HTTPS origin"
    if "${curl_command[@]}" >"${ARTIFACT_ROOT}/logs/fetch-opengfx.curl.stdout.log" 2>"${ARTIFACT_ROOT}/logs/fetch-opengfx.curl.stderr.log"; then
        curl_rc=0
    else
        curl_rc=$?
    fi
    ((curl_rc == 0)) || p0_die "OpenGFX download failed with exit ${curl_rc}; partial bytes were not promoted" "${curl_rc}"
fi

p0_require_sha256 "${archive_path}" "${P0_OPENGFX_ARCHIVE_SHA256}" 'OpenGFX archive'
archive_sha256=$(p0_sha256_file "${archive_path}")
p0_log INFO 'archive digest verified; validating archive members before extraction'

python3 - "${archive_path}" "${ARTIFACT_ROOT}/logs/fetch-opengfx.archive-members.json" <<'PY'
import json
import pathlib
import stat
import sys
import zipfile

archive = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
max_entries = 4096
max_expanded_bytes = 64 * 1024 * 1024

with zipfile.ZipFile(archive) as handle:
    members = handle.infolist()
    if not members:
        raise SystemExit("archive is empty")
    if len(members) > max_entries:
        raise SystemExit(f"archive has too many entries: {len(members)}")
    names = [member.filename for member in members]
    if len(names) != len(set(names)):
        raise SystemExit("archive contains duplicate member names")
    expanded = sum(member.file_size for member in members)
    if expanded > max_expanded_bytes:
        raise SystemExit(f"archive expands beyond {max_expanded_bytes} bytes")
    records = []
    for member in members:
        name = member.filename
        if not name or "\\" in name or "\x00" in name:
            raise SystemExit(f"archive contains an ambiguous member name: {name!r}")
        if any(ord(character) < 32 for character in name):
            raise SystemExit(f"archive contains a control character in a member name: {name!r}")
        pure = pathlib.PurePosixPath(name)
        if pure.is_absolute() or name.startswith("/") or any(part == ".." for part in pure.parts):
            raise SystemExit(f"archive member escapes extraction root: {name!r}")
        mode = (member.external_attr >> 16) & 0xFFFF
        if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise SystemExit(f"archive contains a link or special file: {name!r}")
        records.append({"compressed_size": member.compress_size, "name": name, "size": member.file_size})

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps({"expanded_bytes": expanded, "members": records}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

extract_root="${temp_dir}/extract"
mkdir -p -- "${extract_root}"
if unzip -qq "${archive_path}" -d "${extract_root}" >"${ARTIFACT_ROOT}/logs/fetch-opengfx.unzip.stdout.log" 2>"${ARTIFACT_ROOT}/logs/fetch-opengfx.unzip.stderr.log"; then
    unzip_rc=0
else
    unzip_rc=$?
fi
((unzip_rc == 0)) || p0_die "verified OpenGFX archive extraction failed with exit ${unzip_rc}" "${unzip_rc}"

if find "${extract_root}" \( -type l -o \( ! -type d ! -type f \) \) -print -quit | grep -q .; then
    p0_die 'extracted OpenGFX tree contains a link or special file' 65
fi
while IFS= read -r extracted_path; do
    resolved_path=$(p0_realpath "${extracted_path}")
    [[ "${resolved_path}" == "${extract_root}"/* ]] || p0_die "extracted path escaped temporary root: ${extracted_path}" 65
done < <(find "${extract_root}" -mindepth 1 -print)

mapfile -d '' payloads < <(find "${extract_root}" -type f -name "${P0_OPENGFX_INSTALLED_NAME}" -print0)
[[ ${#payloads[@]} -eq 1 ]] || p0_die "archive must contain exactly one ${P0_OPENGFX_INSTALLED_NAME}; found ${#payloads[@]}" 65
payload=${payloads[0]}
p0_require_sha256 "${payload}" "${P0_OPENGFX_INSTALLED_SHA256}" 'installed OpenGFX payload'

digests_path="${ARTIFACT_ROOT}/logs/fetch-opengfx.extracted-files.sha256"
: >"${digests_path}"
while IFS= read -r -d '' extracted_file; do
    relative_path=${extracted_file#"${extract_root}/"}
    printf '%s  %s\n' "$(p0_sha256_file "${extracted_file}")" "${relative_path}" >>"${digests_path}"
done < <(find "${extract_root}" -type f -print0 | sort -z)

destination_file="${DESTINATION}/${P0_OPENGFX_INSTALLED_NAME}"
install_state='INSTALLED'
if [[ -e "${destination_file}" ]]; then
    [[ -f "${destination_file}" && ! -L "${destination_file}" ]] || p0_die "existing OpenGFX destination is not a regular file: ${destination_file}" 65
    existing_sha256=$(p0_sha256_file "${destination_file}")
    [[ "${existing_sha256}" == "${P0_OPENGFX_INSTALLED_SHA256}" ]] || p0_die "existing OpenGFX destination differs and will not be overwritten: ${destination_file}" 65
    install_state='VERIFIED_EXISTING'
else
    mv -- "${payload}" "${destination_file}"
fi
p0_require_sha256 "${destination_file}" "${P0_OPENGFX_INSTALLED_SHA256}" 'promoted OpenGFX content'

python3 - "${ARTIFACT_ROOT}/results/fetch-opengfx-details.json" \
    "${install_state}" "${archive_sha256}" "${P0_OPENGFX_INSTALLED_SHA256}" \
    "${P0_OPENGFX_ARCHIVE_URL}" "${DESTINATION}" "${destination_file}" "${digests_path}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
value = {
    "authoritative": {
        "archive": {"name": "opengfx-8.0-all.zip", "sha256": sys.argv[3], "url": sys.argv[5]},
        "installed": {"name": "opengfx-8.0.tar", "sha256": sys.argv[4], "state": sys.argv[2]},
        "version": "8.0",
    },
    "diagnostics": {"destination": sys.argv[6], "installed_file": sys.argv[7], "installed_file_digest_log": sys.argv[8]},
    "status": "PASS",
}
path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

p0_finish 'PASS' 0 "OpenGFX ${P0_OPENGFX_VERSION} ${install_state} with verified archive and installed digests"
