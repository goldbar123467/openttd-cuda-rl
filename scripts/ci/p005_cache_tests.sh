#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC

usage() { printf '%s\n' 'Usage: p005_cache_tests.sh --tools-python ABSOLUTE_EXECUTABLE' >&2; }
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

cd "$repo_root"
"$tools_python" - <<'PY'
import json
from pathlib import Path

registry = json.loads(Path("parity/schema/fields-v1.json").read_text(encoding="utf-8"))
caches = [field for field in registry["fields"] if field["cache_classification"] != "not_cache"]
if not caches:
    raise SystemExit("P005-CACHE-STATIC-001: registry contains no reviewed caches")
derived = [field["path"] for field in caches if field["cache_classification"] == "derived_rebuild" or field["classification"] == "derived_rebuild"]
if derived:
    raise SystemExit(f"P005-CACHE-STATIC-002: unproved derived cache: {derived[0]}")
for field in caches:
    if field["cache_classification"] == "authoritative_cache" and field["classification"] != "authoritative_full":
        raise SystemExit(f"P005-CACHE-STATIC-003: reached cache is not full: {field['path']}")
print(f"STATIC-ONLY CHECK OK: {len(caches)} reviewed cache fields remain conservative; this is not PORT005 PASS")
PY

"$tools_python" -m unittest \
    parity.tests.port005.test_field_schema.RegistryTest.test_conservative_cache_policy \
    parity.tests.port005.test_field_schema.InvariantTest
