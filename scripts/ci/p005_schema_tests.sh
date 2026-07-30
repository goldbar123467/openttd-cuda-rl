#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

usage() { printf '%s\n' 'Usage: p005_schema_tests.sh --tools-python ABSOLUTE_EXECUTABLE' >&2; }
tools_python=''
while (($#)); do
    case "$1" in
        --tools-python)
            (($# >= 2)) || { usage; exit 64; }
            tools_python=$2
            shift 2
            ;;
        *)
            usage
            exit 64
            ;;
    esac
done
[[ "$tools_python" == /* && -f "$tools_python" && -x "$tools_python" ]] || { usage; exit 64; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
expected_lock_sha256='b353463307b5331a110b8b44c325078e97faaab0388666faf57cbf8cf676efc7'
actual_lock_sha256="$(sha256sum "$repo_root/tools/requirements-p0.txt" | cut -d ' ' -f 1)"
[[ "$actual_lock_sha256" == "$expected_lock_sha256" ]] || { printf '%s\n' 'requirements-p0.txt lock digest mismatch' >&2; exit 65; }
expected_python_sha256='1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118'
actual_python_sha256="$(sha256sum "$tools_python" | cut -d ' ' -f 1)"
[[ "$actual_python_sha256" == "$expected_python_sha256" ]] || { printf '%s\n' 'tools Python binary digest mismatch' >&2; exit 65; }
"$tools_python" -c 'import jsonschema' >/dev/null

artifact_root="$(mktemp -d)"
trap 'rm -rf -- "$artifact_root"' EXIT

cd "$repo_root"
"$tools_python" scripts/dev/generate_field_schema.py --artifact-root "$artifact_root"
cmp parity/schema/fields-v1.json "$artifact_root/parity/schema/fields-v1.json"
cmp parity/schema/fields-v1.sha256 "$artifact_root/parity/schema/fields-v1.sha256"
cmp parity/schema/projection-plan-v1.json "$artifact_root/parity/schema/projection-plan-v1.json"
cmp parity/include/openttd_rl_parity/field_schema.h "$artifact_root/parity/include/openttd_rl_parity/field_schema.h"
cmp parity/src/field_schema.c "$artifact_root/parity/src/field_schema.c"
"$tools_python" scripts/dev/validate_field_schema.py \
    "$artifact_root/parity/schema/fields-v1.json" \
    --schema parity/schema/field-schema.schema.json \
    --source-root openttd-upstream
"$tools_python" -m unittest parity.tests.port005.test_field_schema

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck scripts/ci/p005_schema_tests.sh scripts/ci/p005_cache_tests.sh
fi
