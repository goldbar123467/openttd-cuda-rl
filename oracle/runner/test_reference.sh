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
Usage: test_reference.sh --build-root ABSOLUTE_PATH
                         --artifact-root ABSOLUTE_PATH
                         --baseline-inventory ABSOLUTE_PATH

Tests may set P0_TEST_MODE=1 and pass --test-timeout 1..300 to exercise the
timeout path without delaying the production suite. Production always uses
the frozen 300-second timeout.

The committed baseline may contain either a test_names array or a tests array
whose objects contain name and properties (the latter is also the raw CTest JSON
shape). Names are de-duplicated, sorted, and compared exactly. When baseline
properties are present they are normalized and compared exactly too. Raw CTest
JSON, normalized inventory, SHA-256, JUnit XML, and plain logs are always kept.

Each upstream test has a 300-second timeout. Upstream tests are not randomized;
the randomized/repeated scheduling release requirement applies to new P0 harness
tests in their own runner because upstream fixtures have ordering/resource
constraints.
EOF
    p0_show_common_help_note
}

BUILD_ROOT=''
ARTIFACT_ROOT=''
BASELINE_INVENTORY=''
TEST_TIMEOUT=300
declare -a ORIGINAL_ARGUMENTS=("$@")

while (($# > 0)); do
    case "$1" in
        --build-root)
            (($# >= 2)) || p0_usage_error '--build-root requires a value'
            BUILD_ROOT=$2
            shift 2
            ;;
        --artifact-root)
            (($# >= 2)) || p0_usage_error '--artifact-root requires a value'
            ARTIFACT_ROOT=$2
            shift 2
            ;;
        --baseline-inventory)
            (($# >= 2)) || p0_usage_error '--baseline-inventory requires a value'
            BASELINE_INVENTORY=$2
            shift 2
            ;;
        --test-timeout)
            (($# >= 2)) || p0_usage_error '--test-timeout requires a value'
            [[ "${P0_TEST_MODE:-0}" == 1 ]] || p0_usage_error '--test-timeout is restricted to P0_TEST_MODE=1'
            TEST_TIMEOUT=$2
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

[[ "${TEST_TIMEOUT}" =~ ^[0-9]+$ ]] || p0_usage_error '--test-timeout must be an integer'
((TEST_TIMEOUT >= 1 && TEST_TIMEOUT <= 300)) || p0_usage_error '--test-timeout must be between 1 and 300'

for path_and_label in \
    "${BUILD_ROOT}|--build-root" \
    "${ARTIFACT_ROOT}|--artifact-root" \
    "${BASELINE_INVENTORY}|--baseline-inventory"; do
    p0_require_absolute_path "${path_and_label%%|*}" "${path_and_label#*|}"
done
ARTIFACT_ROOT=$(p0_validate_generated_root "${ARTIFACT_ROOT}")
BUILD_ROOT=$(p0_realpath "${BUILD_ROOT}")
BASELINE_INVENTORY=$(p0_realpath "${BASELINE_INVENTORY}")
p0_assert_under_root "${BUILD_ROOT}" "${ARTIFACT_ROOT}" no

p0_initialize 'test-reference' "${ARTIFACT_ROOT}" 'test-reference.json'
p0_write_command_array "${ARTIFACT_ROOT}/commands/test-reference.json" "$0" "${ORIGINAL_ARGUMENTS[@]}"
for tool in ctest python3 sha256sum grep; do
    p0_require_command "${tool}"
done
p0_json_validate "${BASELINE_INVENTORY}"
[[ -f "${BUILD_ROOT}/CTestTestfile.cmake" ]] || p0_die 'configured build root has no CTestTestfile.cmake' 66

mkdir -p -- "${ARTIFACT_ROOT}/inventory" "${ARTIFACT_ROOT}/test-results" "${ARTIFACT_ROOT}/commands"
raw_inventory="${ARTIFACT_ROOT}/inventory/ctest-inventory.raw.json"
normalized_inventory="${ARTIFACT_ROOT}/inventory/ctest-inventory.normalized.json"
inventory_compare="${ARTIFACT_ROOT}/inventory/ctest-inventory-comparison.json"
inventory_name_stream="${ARTIFACT_ROOT}/inventory/ctest-inventory.names.txt"

declare -a inventory_command=(ctest --test-dir "${BUILD_ROOT}" -N --show-only=json-v1)
p0_write_command_array "${ARTIFACT_ROOT}/commands/test-reference-inventory.json" "${inventory_command[@]}"
p0_log INFO 'enumerating the complete CTest inventory as JSON v1'
if "${inventory_command[@]}" >"${raw_inventory}" 2>"${ARTIFACT_ROOT}/logs/test-reference.inventory.stderr.log"; then
    inventory_rc=0
else
    inventory_rc=$?
fi
((inventory_rc == 0)) || p0_die "CTest inventory failed with exit ${inventory_rc}" "${inventory_rc}"
p0_json_validate "${raw_inventory}"

python3 - "${raw_inventory}" "${normalized_inventory}" "${BASELINE_INVENTORY}" \
    "${inventory_compare}" "${BUILD_ROOT}" "${P0_EXPECTED_TEST_COUNT}" "${inventory_name_stream}" <<'PY'
import hashlib
import json
import pathlib
import sys

raw_path = pathlib.Path(sys.argv[1])
normalized_path = pathlib.Path(sys.argv[2])
baseline_path = pathlib.Path(sys.argv[3])
comparison_path = pathlib.Path(sys.argv[4])
build_root = sys.argv[5]
expected_count = int(sys.argv[6])
name_stream_path = pathlib.Path(sys.argv[7])

raw = json.loads(raw_path.read_text(encoding="utf-8"))
baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
tests = raw.get("tests")
if not isinstance(tests, list):
    raise SystemExit("CTest inventory has no tests array")

def normalize_value(value):
    if isinstance(value, str):
        return value.replace(build_root, "${BUILD_ROOT}")
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(value[key]) for key in sorted(value)}
    return value

def normalize_properties(properties):
    if not isinstance(properties, list):
        raise SystemExit("test properties must be an array")
    normalized = [normalize_value(item) for item in properties]
    return sorted(normalized, key=lambda item: (str(item.get("name", "")), json.dumps(item, sort_keys=True)))

current = []
for test in tests:
    if not isinstance(test, dict) or not isinstance(test.get("name"), str):
        raise SystemExit("CTest inventory contains a malformed test entry")
    current.append({"name": test["name"], "properties": normalize_properties(test.get("properties", []))})
current.sort(key=lambda item: item["name"])
current_names = [item["name"] for item in current]
if len(current_names) != len(set(current_names)):
    raise SystemExit("CTest inventory contains duplicate test names")
if len(current_names) != expected_count:
    raise SystemExit(f"expected exactly {expected_count} tests, found {len(current_names)}")

baseline_has_properties = False
if isinstance(baseline.get("test_names"), list):
    baseline_names = baseline["test_names"]
    if not all(isinstance(name, str) for name in baseline_names):
        raise SystemExit("baseline test_names must contain only strings")
    if not isinstance(baseline.get("serial_tests"), list) or not all(isinstance(name, str) for name in baseline["serial_tests"]):
        raise SystemExit("test_names baseline must contain a serial_tests string array")
elif isinstance(baseline.get("tests"), list):
    baseline_entries = baseline["tests"]
    if not all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in baseline_entries):
        raise SystemExit("baseline tests array contains a malformed entry")
    baseline_names = [item["name"] for item in baseline_entries]
    baseline_has_properties = all("properties" in item for item in baseline_entries)
else:
    raise SystemExit("baseline must contain test_names or tests")

baseline_names = sorted(baseline_names)
if len(baseline_names) != len(set(baseline_names)):
    raise SystemExit("baseline contains duplicate test names")
if len(baseline_names) != expected_count:
    raise SystemExit(f"baseline must contain exactly {expected_count} tests, found {len(baseline_names)}")
if current_names != baseline_names:
    missing = sorted(set(baseline_names) - set(current_names))
    extra = sorted(set(current_names) - set(baseline_names))
    raise SystemExit(f"CTest inventory drift; missing={missing}, extra={extra}")

name_stream = "".join(name + "\n" for name in current_names).encode("utf-8")
name_stream_path.write_bytes(name_stream)
if isinstance(baseline.get("inventory_sha256"), str):
    actual_digest = hashlib.sha256(name_stream).hexdigest()
    if actual_digest != baseline["inventory_sha256"]:
        raise SystemExit(f"normalized name-stream digest drift: expected {baseline['inventory_sha256']}, got {actual_digest}")
if isinstance(baseline.get("inventory_stream_size_bytes"), int) and len(name_stream) != baseline["inventory_stream_size_bytes"]:
    raise SystemExit("normalized name-stream size drift")

properties_status = "NOT_PRESENT_IN_BASELINE"
if baseline_has_properties:
    expected = []
    for test in baseline_entries:
        expected.append({"name": test["name"], "properties": normalize_properties(test["properties"])})
    expected.sort(key=lambda item: item["name"])
    if current != expected:
        raise SystemExit("CTest property inventory drift")
    properties_status = "EXACT_MATCH"
elif isinstance(baseline.get("test_names"), list):
    serial_names = set(baseline["serial_tests"])
    expected = []
    for name in baseline_names:
        properties = [{"name": "WORKING_DIRECTORY", "value": "${BUILD_ROOT}"}]
        if name in serial_names:
            properties.append({"name": "RUN_SERIAL", "value": True})
        expected.append({"name": name, "properties": normalize_properties(properties)})
    expected.sort(key=lambda item: item["name"])
    if current != expected:
        raise SystemExit("CTest property inventory drift: expected only exact WORKING_DIRECTORY and declared RUN_SERIAL properties")
    properties_status = "EXACT_MATCH_NORMALIZED_BASELINE"

normalized = {"tests": current, "version": {"major": 1, "minor": 0}}
normalized_path.write_text(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
comparison = {"count": len(current_names), "names": "EXACT_MATCH", "properties": properties_status, "status": "PASS"}
comparison_path.write_text(json.dumps(comparison, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

inventory_sha256=$(p0_sha256_file "${inventory_name_stream}")
junit_file="${ARTIFACT_ROOT}/test-results/ctest-results.junit.xml"
writable_probe=$(mktemp -- "${ARTIFACT_ROOT}/test-results/.junit-writable.XXXXXXXX")
p0_assert_under_root "${writable_probe}" "${ARTIFACT_ROOT}" no
rm -- "${writable_probe}"

declare -a test_command=(
    ctest
    --test-dir "${BUILD_ROOT}"
    --output-on-failure
    --no-tests=error
    --timeout "${TEST_TIMEOUT}"
    --output-junit "${junit_file}"
)
p0_write_command_array "${ARTIFACT_ROOT}/commands/test-reference-ctest.json" "${test_command[@]}"
test_started_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
test_started_epoch=$(date -u +%s)
p0_log INFO 'running all 99 upstream tests with output-on-failure, timeout, no-tests error, and JUnit output'
if "${test_command[@]}" >"${ARTIFACT_ROOT}/logs/test-reference.stdout.log" 2>"${ARTIFACT_ROOT}/logs/test-reference.stderr.log"; then
    test_rc=0
else
    test_rc=$?
fi
test_finished_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
test_finished_epoch=$(date -u +%s)
test_duration=$((test_finished_epoch - test_started_epoch))
[[ -f "${junit_file}" && -s "${junit_file}" ]] || p0_die 'CTest did not create a nonempty JUnit result' 70

counts_file="${ARTIFACT_ROOT}/test-results/ctest-counts.json"
python3 - "${junit_file}" "${counts_file}" "${P0_EXPECTED_TEST_COUNT}" \
    "${test_started_at}" "${test_finished_at}" "${test_duration}" "${test_rc}" "${inventory_name_stream}" <<'PY'
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

junit = pathlib.Path(sys.argv[1])
output = pathlib.Path(sys.argv[2])
expected = int(sys.argv[3])
try:
    root = ET.parse(junit).getroot()
except ET.ParseError as exc:
    raise SystemExit(f"malformed JUnit XML: {exc}") from exc
cases = root.findall(".//testcase")
names = [case.attrib.get("name", "") for case in cases]
if not all(names) or len(names) != len(set(names)):
    raise SystemExit("JUnit contains missing or duplicate test names")
expected_names = pathlib.Path(sys.argv[8]).read_text(encoding="utf-8").splitlines()
if sorted(names) != expected_names:
    raise SystemExit("JUnit executed-name set differs from the verified inventory")
failures = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
skipped = sum(case.find("skipped") is not None for case in cases)
passed = len(cases) - failures - skipped
value = {
    "diagnostics": {"duration_seconds": int(sys.argv[6]), "finished_at": sys.argv[5], "started_at": sys.argv[4]},
    "failed": failures,
    "passed": passed,
    "return_code": int(sys.argv[7]),
    "skipped": skipped,
    "test_names": sorted(names),
    "total": len(cases),
}
if len(cases) != expected:
    value["inventory_error"] = f"expected {expected} JUnit test cases, found {len(cases)}"
output.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

readarray -t test_counts < <(python3 - "${counts_file}" <<'PY'
import json
import pathlib
import sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in ("total", "passed", "failed", "skipped"):
    print(value[key])
PY
)
total=${test_counts[0]}
passed=${test_counts[1]}
failed=${test_counts[2]}
skipped=${test_counts[3]}

((total == P0_EXPECTED_TEST_COUNT)) || p0_die "JUnit contains ${total} tests; expected ${P0_EXPECTED_TEST_COUNT}" 65
((skipped == 0)) || p0_die "CTest reported ${skipped} unexpected skipped tests" 65
((failed == 0)) || p0_die "CTest reported ${failed} failed or timed-out tests" 65
((test_rc == 0)) || p0_die "CTest returned nonzero exit ${test_rc}" "${test_rc}"
((passed == P0_EXPECTED_TEST_COUNT)) || p0_die "only ${passed} of ${P0_EXPECTED_TEST_COUNT} tests passed" 65

python3 - "${ARTIFACT_ROOT}/manifests/test-reference.json" \
    "${ARTIFACT_ROOT}/commands/test-reference-inventory.json" \
    "${ARTIFACT_ROOT}/commands/test-reference-ctest.json" "${inventory_sha256}" \
    "${P0_EXPECTED_TEST_COUNT}" "${passed}" "${failed}" "${skipped}" \
    "${raw_inventory}" "${normalized_inventory}" "${BASELINE_INVENTORY}" \
    "${junit_file}" "${ARTIFACT_ROOT}/logs/test-reference.stdout.log" "${counts_file}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
actual_inventory_command = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
actual_test_command = json.loads(pathlib.Path(sys.argv[3]).read_text(encoding="utf-8"))
def normalize(command):
    try:
        build_root = command[command.index("--test-dir") + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit("recorded CTest command omits --test-dir role") from exc
    replacements = [
        (build_root, "$BUILD_ROOT"),
        (str(pathlib.Path(sys.argv[9]).parents[1]), "$ARTIFACT_ROOT"),
    ]
    result = []
    for argument in command:
        for concrete, role in replacements:
            argument = argument.replace(concrete, role)
        result.append(argument)
    return result
value = {
    "authoritative": {
        "counts": {"failed": int(sys.argv[7]), "passed": int(sys.argv[6]), "skipped": int(sys.argv[8]), "total": int(sys.argv[5])},
        "inventory_command": normalize(actual_inventory_command),
        "inventory_sha256": sys.argv[4],
        "test_command": normalize(actual_test_command),
    },
    "diagnostics": {
        "actual_inventory_command": actual_inventory_command, "actual_test_command": actual_test_command,
        "baseline_inventory": sys.argv[11], "counts": sys.argv[14], "junit": sys.argv[12],
        "normalized_inventory": sys.argv[10], "plain_log": sys.argv[13], "raw_inventory": sys.argv[9],
    },
    "return_code": 0,
    "status": "PASS",
}
path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
p0_json_canonicalize_in_place "${ARTIFACT_ROOT}/manifests/test-reference.json" "${ARTIFACT_ROOT}"

python3 - "${ARTIFACT_ROOT}/manifests/test-reference.json" \
    "${P0_REPOSITORY_ROOT}/oracle/manifests/baseline/build-relwithdebinfo.json" <<'PY'
import json
import pathlib
import sys

actual = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["authoritative"]
baseline = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))["invocations"]
if actual.get("inventory_command") != baseline.get("test_inventory"):
    raise SystemExit("recorded inventory command differs from the frozen logical invocation")
if actual.get("test_command") != baseline.get("test"):
    raise SystemExit("recorded test command differs from the frozen logical invocation")
PY

p0_finish 'PASS' 0 "exact inventory matched and all ${P0_EXPECTED_TEST_COUNT} tests passed"
