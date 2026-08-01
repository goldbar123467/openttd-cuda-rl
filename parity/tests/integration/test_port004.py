#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "parity/tests/golden"))
sys.path.insert(0, str(ROOT / "parity/python_reference"))

from tape_reference import TapeError, canonical_json, decode_bytes, decode_file  # noqa: E402
from golden import header, projection, record, repair_digest, tape  # noqa: E402

TAPE_CLI: Path


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "TZ": "UTC"})
    return subprocess.run(
        [str(TAPE_CLI), *(str(arg) for arg in args)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        env=environment,
    )


class TapeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="p004-test-")
        self.root = Path(self.temporary.name)
        self.valid = self.root / "valid.tape"
        self.valid.write_bytes(tape())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_c_status(self, data: bytes, status: str) -> None:
        path = self.root / f"case-{hashlib.sha256(data).hexdigest()[:12]}.tape"
        path.write_bytes(data)
        result = run_cli("validate", path)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(status, result.stderr)

    def test_primitive_encoding_and_golden_vectors(self) -> None:
        self.assertEqual(len(tape()), 69280)
        self.assertEqual(hashlib.sha256(tape()).hexdigest(),
                         "b4843f581526a036759a54e635bbbba65624493973d2569143e284503abd1287")
        self.assertEqual(struct.pack("<B", 0) + struct.pack("<B", 1) + struct.pack("<B", 255),
                         bytes.fromhex("0001ff"))
        self.assertEqual(b"".join(struct.pack("<H", x) for x in (0, 1, 0x1234, 0xFFFF)),
                         bytes.fromhex("000001003412ffff"))
        self.assertEqual(struct.pack("<I", 0x12345678), bytes.fromhex("78563412"))
        self.assertEqual(struct.pack("<Q", 0x0123456789ABCDEF),
                         bytes.fromhex("efcdab8967452301"))
        self.assertEqual(struct.pack("<q", -(2**63)), bytes.fromhex("0000000000000080"))
        for remainder in range(8):
            framed = record(6, 0, 0, 0, b"x" * remainder)
            self.assertEqual(len(framed) % 8, 0)
            self.assertEqual(framed[40 + remainder:], b"\0" * ((-remainder) & 7))
        reordered = json.loads(header())
        self.assertEqual(canonical_json(reordered), header())
        self.assertEqual(hashlib.sha256(b"").hexdigest(),
                         "e3b0c44298fc1c149afbf4c8996fb924"
                         "27ae41e4649b934ca495991b7852b855")
        decoded = decode_file(self.valid)
        rng = next(field for field in decoded.records[1].fields
                   if field.field_id == 1030)
        self.assertEqual(rng.value, b"*\0\0\0")

    def test_file_prefix_contract(self) -> None:
        self.assertEqual(len(tape()[:64]), 64)
        for length in range(64):
            with self.assertRaises(TapeError) as raised:
                decode_bytes(tape()[:length])
            self.assertEqual(raised.exception.status, "truncated")
            self.assertEqual(raised.exception.offset, length)
        baseline = tape()
        for index in range(8):
            bad = bytearray(baseline); bad[index] ^= 1
            self.assert_c_status(bytes(bad), "magic")
        for offset, value, expected in (
            (8, 0, "version"), (8, 2, "version"), (12, 2, "endian"),
            (13, 2, "hash_algorithm"), (14, 63, "structure"),
        ):
            bad = bytearray(baseline)
            if offset in (8, 14): struct.pack_into("<H", bad, offset, value)
            else: bad[offset] = value
            self.assert_c_status(bytes(bad), expected)
        bad = bytearray(baseline); struct.pack_into("<I", bad, 16, 1_048_577)
        self.assert_c_status(bytes(bad), "limit")
        bad = bytearray(baseline); struct.pack_into("<Q", bad, 56, 1)
        self.assert_c_status(bytes(bad), "reserved")
        bad = bytearray(baseline); struct.pack_into("<I", bad, 20, 0x10000)
        self.assert_c_status(bytes(bad), "version")

    def test_header_json_contract(self) -> None:
        self.assertEqual(decode_file(self.valid).header["format"], {"major": 1, "minor": 0})
        cases = [
            header().replace(b"{", b"{ ", 1),
            b'{"a":1,"a":2}',
            b"\xef\xbb\xbf" + header(),
            header().replace(b',"source_commit":"' + b"9" * 40 + b'"', b""),
            header().replace(b"9" * 40, b"9" * 39),
            header().replace(b"9" * 40, b"g" + b"9" * 39),
            header().replace(b"6" * 64, b"A" * 64),
            header().replace(b'"native_tick":0', b'"native_tick":-1'),
            header().replace(b'"newgrfs":[]', b'"newgrfs":["x"]'),
        ]
        for malformed in cases:
            with self.subTest(malformed=malformed[:30]):
                data = tape(header_bytes=malformed)
                result = run_cli("validate", self._write("header.tape", data))
                self.assertEqual(result.returncode, 3, result.stderr)
                with self.assertRaises(TapeError): decode_bytes(data)

    def _write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_record_framing_contract(self) -> None:
        baseline = tape()
        decoded = decode_bytes(baseline)
        first_offset = decoded.records[0].offset
        for boundary in range(40):
            shortened = baseline[:first_offset + boundary]
            self.assert_c_status(shortened, "truncated")
        cases: list[tuple[list[bytes], str]] = [
            ([record(1, 1, 0, 0), record(5, 1, 0, 0, projection()), record(11, 2, 0, 0)], "sequence"),
            ([record(1, 0, 1, 1), record(5, 1, 0, 1, projection()), record(11, 2, 0, 1)], "sequence"),
            ([record(6, 0, 0, 0), record(5, 1, 0, 0, projection()), record(11, 2, 0, 0)], "structure"),
            ([record(1, 0, 0, 0), record(5, 1, 0, 0, projection())], "structure"),
            ([record(1, 0, 0, 0), record(11, 1, 0, 0), record(5, 2, 0, 0, projection())], "structure"),
            ([record(1, 0, 0, 0),
              record(2, 1, 0, 0, struct.pack("<HHIIIII", 1, 0, 22, 0, 0, 0, 0)),
              record(4, 2, 0, 0, struct.pack("<HBBIqIIII", 1, 1, 0, 22, 0, 0, 0, 0, 0)),
              record(5, 3, 0, 0, projection()), record(11, 4, 0, 0)], "structure"),
        ]
        for records, expected in cases:
            with self.subTest(expected=expected):
                self.assert_c_status(tape(records), expected)
        optional = tape([record(1, 0, 0, 0), record(99, 1, 0, 0, flags=0),
                         record(5, 2, 0, 0, projection()), record(11, 3, 0, 0)])
        self.assertEqual(run_cli("validate", self._write("optional.tape", optional)).returncode, 0)
        required = bytearray(optional); required[decode_bytes(optional).records[1].offset + 4] = 1
        repair_digest(required)
        self.assert_c_status(bytes(required), "version")
        padded = bytearray(tape([
            record(1, 0, 0, 0), record(7, 1, 0, 0, b"x", flags=0),
            record(5, 2, 0, 0, projection()), record(11, 3, 0, 0)]))
        diagnostic_offset = decode_bytes(bytes(padded)).records[1].offset
        padded[diagnostic_offset + 41] = 1
        repair_digest(padded)
        self.assert_c_status(bytes(padded), "canonical")

    def test_projection_contract(self) -> None:
        fields = decode_file(self.valid).records[1].fields
        self.assertEqual(len(fields), 757)
        self.assertIn(1030, {field.field_id for field in fields})
        variants = []
        empty = bytearray(projection()); struct.pack_into("<I", empty, 4, 0)
        variants.append((bytes(empty), "schema"))
        zero_id = bytearray(projection()); struct.pack_into("<I", zero_id, 24, 0)
        variants.append((bytes(zero_id), "schema"))
        wrong_type = bytearray(projection()); struct.pack_into("<H", wrong_type, 28, 4)
        variants.append((bytes(wrong_type), "schema"))
        wrong_count = bytearray(projection()); struct.pack_into("<I", wrong_count, 32, 2)
        variants.append((bytes(wrong_count), "schema"))
        bad_padding = bytearray(projection())
        offset = 24
        for _ in range(struct.unpack_from("<I", bad_padding, 4)[0]):
            byte_count = struct.unpack_from("<IHHII", bad_padding, offset)[4]
            value_end = offset + 16 + byte_count
            padded_end = (value_end + 7) & ~7
            if value_end < padded_end:
                bad_padding[value_end] = 1
                break
            offset = padded_end
        else:
            self.fail("golden projection contains no field padding to corrupt")
        variants.append((bytes(bad_padding), "canonical"))
        for payload, expected in variants:
            records = [record(1, 0, 0, 0), record(5, 1, 0, 0, payload), record(11, 2, 0, 0)]
            self.assert_c_status(tape(records), expected)
        second = bytearray(projection())
        struct.pack_into("<I", second, 4, 2)
        second.extend(struct.pack("<IHHII", 1030, 3, 0, 1, 4) + b"+\0\0\0" + b"\0" * 4)
        self.assert_c_status(tape([record(1, 0, 0, 0), record(5, 1, 0, 0, bytes(second)), record(11, 2, 0, 0)]), "schema")

        def spans(payload: bytes) -> list[tuple[int, int, int, int]]:
            result: list[tuple[int, int, int, int]] = []
            offset = 24
            for _ in range(struct.unpack_from("<I", payload, 4)[0]):
                current = offset
                current_id, _, _, _, byte_count = struct.unpack_from("<IHHII", payload, offset)
                value_offset = offset + 16
                offset = (value_offset + byte_count + 7) & ~7
                result.append((current_id, current, value_offset, offset))
            return result

        complete = projection()
        locations = spans(complete)
        for label, entry in (("first", locations[0]),
                             ("middle", locations[len(locations) // 2]),
                             ("last", locations[-1])):
            with self.subTest(requirement=f"complete-omission-{label}"):
                omitted = bytearray(complete)
                del omitted[entry[1]:entry[3]]
                struct.pack_into("<I", omitted, 4, len(locations) - 1)
                self.assert_c_status(tape([
                    record(1, 0, 0, 0),
                    record(5, 1, 0, 0, bytes(omitted)),
                    record(11, 2, 0, 0),
                ]), "schema")

        bad_count_source = bytearray(complete)
        source = next(entry for entry in locations if entry[0] == 4005)
        struct.pack_into("<I", bad_count_source, source[2], 1)
        self.assert_c_status(tape([
            record(1, 0, 0, 0),
            record(5, 1, 0, 0, bytes(bad_count_source)),
            record(11, 2, 0, 0),
        ]), "schema")
        bad_backward_source = bytearray(complete)
        backward_source = next(entry for entry in locations if entry[0] == 4000)
        struct.pack_into("<I", bad_backward_source, backward_source[2], 1)
        self.assert_c_status(tape([
            record(1, 0, 0, 0),
            record(5, 1, 0, 0, bytes(bad_backward_source)),
            record(11, 2, 0, 0),
        ]), "schema")

        nested = projection(overrides={4075: 3})
        nested_path = self._write("nested-valid.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, nested),
            record(11, 2, 0, 0),
        ]))
        self.assertEqual(run_cli("validate", nested_path).returncode, 0)
        offset_field = next(entry for entry in spans(nested) if entry[0] == 4080)
        decreasing = bytearray(nested)
        struct.pack_into("<III", decreasing, offset_field[2], 0, 1, 0)
        self.assert_c_status(tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, bytes(decreasing)),
            record(11, 2, 0, 0),
        ]), "schema")
        wrong_final = bytearray(nested)
        struct.pack_into("<III", wrong_final, offset_field[2], 0, 0, 1)
        self.assert_c_status(tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, bytes(wrong_final)),
            record(11, 2, 0, 0),
        ]), "schema")

    def test_trailer_and_digest_contract(self) -> None:
        baseline = tape()
        self.assertEqual(run_cli("validate", self.valid).returncode, 0)
        for length in range(64):
            self.assert_c_status(baseline[:len(baseline) - 64 + length], "truncated")
        bad = bytearray(baseline); bad[-64] ^= 1
        self.assert_c_status(bytes(bad), "magic")
        bad = bytearray(baseline); bad[-56] ^= 1
        self.assert_c_status(bytes(bad), "structure")
        bad = bytearray(baseline); bad[100] ^= 1
        self.assert_c_status(bytes(bad), "checksum")
        bad = bytearray(baseline); bad[-40] ^= 1
        self.assert_c_status(bytes(bad), "checksum")
        bad = bytearray(baseline); bad[-8] = 1
        self.assert_c_status(bytes(bad), "reserved")
        self.assert_c_status(baseline + b"x", "structure")
        self.assert_c_status(baseline * 2, "structure")

    def test_P004_REC_complete_every_byte_truncation(self) -> None:
        baseline = tape()
        # The independent decoder checks every file truncation. C-side record
        # header, payload, padding, and trailer truncations are exercised by the
        # focused loops above and below without spawning 64k subprocesses.
        for length in range(len(baseline)):
            shortened = baseline[:length]
            with self.assertRaises(TapeError, msg=f"length={length}"):
                decode_bytes(shortened)
        replay = record(1, 0, 0, 0)
        for length in range(40, len(replay)):
            self.assert_c_status(tape([replay[:length]]), "truncated")

    def test_P004_LIM_001_configured_sparse_file_rejected_before_mapping(self) -> None:
        sparse = self.root / "oversized-sparse.tape"
        with sparse.open("wb") as stream:
            stream.truncate(1_099_511_627_777)
        self.assertEqual(sparse.stat().st_size, 1_099_511_627_777)
        result = run_cli("validate", sparse)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("limit", result.stderr)

    def test_streaming_file_paths_have_bounded_resident_memory(self) -> None:
        record_total = 200_000
        records = [record(1, 0, 0, 0)]
        records.extend(record(99, sequence, 0, 0, b"", flags=0)
                       for sequence in range(1, record_total + 1))
        records.extend([
            record(5, record_total + 1, 0, 0, projection()),
            record(11, record_total + 2, 0, 0),
        ])
        large = self._write("large-stream.tape", tape(records))
        target_records = records[:-2] + [
            record(5, record_total + 1, 0, 0, projection(43)),
            record(11, record_total + 2, 0, 0),
        ]
        target = self._write("large-stream-target.tape", tape(target_records))
        self.assertGreater(large.stat().st_size, 8_000_000)

        def measured(*arguments: object) -> tuple[subprocess.CompletedProcess[str], int]:
            usage = self.root / f"rss-{len(list(self.root.glob('rss-*')))}.txt"
            environment = os.environ.copy()
            environment.update({"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8", "TZ": "UTC"})
            completed = subprocess.run(
                ["/usr/bin/time", "-q", "-f", "%M", "-o", str(usage),
                 str(TAPE_CLI), *(str(argument) for argument in arguments)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, env=environment,
            )
            return completed, int(usage.read_text().strip())

        validated, validate_rss_kib = measured("validate", large)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertLess(validate_rss_kib, 96 * 1024)
        compared, compare_rss_kib = measured("compare", large, target)
        self.assertEqual(compared.returncode, 1, compared.stderr)
        self.assertLess(compare_rss_kib, 96 * 1024)
        report = json.loads(compared.stdout)
        self.assertEqual(report["record_sequence"], record_total + 1)
        minimum = Path(report["minimal_prefix"]["path"])
        self.assertTrue(minimum.is_file())
        self.assertGreater(minimum.stat().st_size, 8_000_000)

    def test_comparator_contract(self) -> None:
        copy = self._write("copy.tape", self.valid.read_bytes())
        self.assertEqual(run_cli("compare", self.valid, copy).returncode, 0)
        identity = self._write("identity.tape", tape(header_bytes=header(fixture="a" * 64)))
        self.assertEqual(run_cli("compare", self.valid, identity).returncode, 2)
        changed_records = [record(1, 0, 0, 0), record(5, 1, 0, 0, projection(43)),
                           record(6, 2, 0, 0), record(11, 3, 0, 0)]
        changed = self._write("changed.tape", tape(changed_records))
        result = run_cli("compare", self.valid, changed)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["record_sequence"], report["field_id"]), (1, 1030))
        report_schema = json.loads(
            (ROOT / "parity/schema/divergence-report.schema.json").read_text()
        )
        jsonschema.Draft202012Validator(report_schema).validate(report)
        self.assertEqual(
            result.stdout.strip(),
            json.dumps(report, sort_keys=True, separators=(",", ":")),
        )
        repeated = run_cli("compare", self.valid, changed)
        self.assertEqual(repeated.returncode, 1, repeated.stderr)
        self.assertEqual(repeated.stdout, result.stdout)
        optional_records = [record(1, 0, 0, 0), record(7, 1, 0, 0, b"ignored", flags=0),
                            record(5, 2, 0, 0, projection()), record(6, 3, 0, 0),
                            record(11, 4, 0, 0)]
        optional = self._write("diagnostic.tape", tape(optional_records))
        self.assertEqual(run_cli("compare", self.valid, optional).returncode, 0)
        signed_a = projection(overrides={1001: -1})
        signed_b = projection(overrides={1001: -2})
        signed_oracle = self._write("signed-a.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, signed_a), record(11, 2, 0, 0)]))
        signed_target = self._write("signed-b.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, signed_b), record(11, 2, 0, 0)]))
        signed_report = json.loads(run_cli("compare", signed_oracle, signed_target).stdout)
        self.assertEqual(signed_report["oracle_value_decimal"], "-1")
        self.assertEqual(signed_report["oracle_value_hex"], "0xffffffff")
        self.assertTrue(signed_report["value_signed"])

        def two_fields(first: int, second: int) -> bytes:
            return projection(overrides={1030: first, 1031: second})
        early_a = self._write("early-a.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, two_fields(1, 2)), record(11, 2, 0, 0)]))
        early_b = self._write("early-b.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, two_fields(3, 4)), record(11, 2, 0, 0)]))
        self.assertEqual(json.loads(run_cli("compare", early_a, early_b).stdout)["field_id"], 1030)

    def test_P004_command_payload_lifecycle(self) -> None:
        intent = struct.pack("<HHIIIII", 1, 0, 22, 0, 0, 0, 0)
        outcome = struct.pack("<HBBIqIIII", 1, 1, 0, 22, 0, 0, 0, 0, 0)
        command_tape = tape([
            record(1, 0, 0, 0), record(2, 1, 0, 0, intent),
            record(3, 2, 0, 0, outcome), record(4, 3, 0, 0, outcome),
            record(5, 4, 1, 1, projection()), record(11, 5, 1, 1),
        ], maximum_step=1, maximum_tick=1)
        self.assertEqual(run_cli("validate", self._write("commands.tape", command_tape)).returncode, 0)
        rejected = bytearray(outcome); rejected[2] = 0
        rejected_tape = tape([
            record(1, 0, 0, 0), record(2, 1, 0, 0, intent),
            record(3, 2, 0, 0, bytes(rejected)),
            record(5, 3, 1, 1, projection()), record(11, 4, 1, 1),
        ], maximum_step=1, maximum_tick=1)
        self.assertEqual(run_cli("validate", self._write("rejected.tape", rejected_tape)).returncode, 0)
        bad_exec = tape([
            record(1, 0, 0, 0), record(2, 1, 0, 0, intent),
            record(3, 2, 0, 0, bytes(rejected)), record(4, 3, 0, 0, outcome),
            record(5, 4, 1, 1, projection()), record(11, 5, 1, 1),
        ], maximum_step=1, maximum_tick=1)
        self.assert_c_status(bad_exec, "structure")

    def test_minimizer_contract(self) -> None:
        oracle = self._write("oracle-long.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, projection(42)),
            record(6, 2, 0, 0),
            record(5, 3, 1, 1, projection(43)), record(11, 4, 1, 1)
        ], maximum_step=1, maximum_tick=1))
        target = self._write("target.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, projection(42)),
            record(6, 2, 0, 0),
            record(5, 3, 1, 1, projection(99)), record(11, 4, 1, 1)
        ], maximum_step=1, maximum_tick=1))
        output = self.root / "minimum.tape"
        original = json.loads(run_cli("compare", oracle, target).stdout)
        result = run_cli("minimize", oracle, target, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        minimum = decode_file(output)
        self.assertEqual([r.record_type for r in minimum.records], [1, 5, 6, 5, 11])
        minimized = run_cli("compare", oracle, output)
        self.assertEqual(minimized.returncode, 1)
        minimized_report = json.loads(minimized.stdout)
        for key in ("kind", "field_id", "record_sequence", "record_type"):
            self.assertEqual(minimized_report[key], original[key])
        previous = self._write("previous-closed.tape", tape([
            record(1, 0, 0, 0), record(5, 1, 0, 0, projection(42)),
            record(6, 2, 0, 0), record(11, 3, 0, 0)]))
        previous_report = json.loads(run_cli("compare", oracle, previous).stdout)
        self.assertNotEqual(
            (previous_report["kind"], previous_report["field_id"],
             previous_report["record_sequence"], previous_report["record_type"]),
            (original["kind"], original["field_id"],
             original["record_sequence"], original["record_type"]),
        )
        self.assertEqual(run_cli("minimize", self.valid, self.valid, self.root / "equal").returncode, 64)
        existing = self.root / "exists"; existing.write_text("keep")
        self.assertEqual(run_cli("minimize", self.valid, target, existing).returncode, 4)
        self.assertEqual(existing.read_text(), "keep")

    def test_cli_and_finalize_contract(self) -> None:
        self.assertEqual(run_cli().returncode, 64)
        self.assertEqual(run_cli("unknown").returncode, 64)
        self.assertEqual(run_cli("--help").returncode, 0)
        self.assertIn("fault-inject", run_cli("--help").stdout)
        self.assertEqual(run_cli("validate", self.root / "missing").returncode, 4)
        inspect = run_cli("inspect", self.valid)
        self.assertEqual(inspect.returncode, 0)
        self.assertIn("records=4", inspect.stdout)
        digest = run_cli("hash", self.valid)
        self.assertEqual(digest.stdout.strip(), hashlib.sha256(self.valid.read_bytes()[:-64]).hexdigest())
        self.assertEqual(run_cli("schema-check", self.valid).returncode, 0)
        self.assertEqual(run_cli("dump", self.valid, "--from-tick", 2,
                                 "--to-tick", 1, "--fields", "all").returncode, 64)
        self.assertEqual(run_cli("dump", self.valid, "--from-tick", 0,
                                 "--to-tick", 0, "--fields", 1030).returncode, 0)
        unknown_filter = run_cli("dump", self.valid, "--from-tick", 0,
                                 "--to-tick", 0, "--fields", 4_000_000_000)
        self.assertEqual(unknown_filter.returncode, 64)
        self.assertIn("usage", unknown_filter.stderr)
        faulted = self.root / "faulted.tape"
        self.assertEqual(run_cli("fault-inject", self.valid, faulted,
                                 "field:1030:1").returncode, 0)
        self.assertEqual(run_cli("compare", self.valid, faulted).returncode, 1)
        raw = bytearray(self.valid.read_bytes()[:-64])
        struct.pack_into("<I", raw, 20, 1)
        partial = self._write("journal.partial", bytes(raw))
        finalized = self.root / "finalized.tape"
        self.assertEqual(run_cli("finalize", partial, finalized).returncode, 0)
        self.assertEqual(finalized.read_bytes(), self.valid.read_bytes())

    def test_named_checkpoint_registry_is_exact(self) -> None:
        for checkpoint_id in range(1, 9):
            with self.subTest(checkpoint_id=checkpoint_id):
                checkpoint = struct.pack("<HHI", 1, checkpoint_id, 0)
                encoded = tape([
                    record(1, 0, 0, 0),
                    record(5, 1, 0, 0, projection()),
                    record(6, 2, 0, 0, checkpoint),
                    record(11, 3, 0, 0),
                ])
                path = self._write(f"checkpoint-{checkpoint_id}.tape", encoded)
                self.assertEqual(run_cli("validate", path).returncode, 0)
        for checkpoint_id in (0, 9):
            with self.subTest(invalid_checkpoint_id=checkpoint_id):
                checkpoint = struct.pack("<HHI", 1, checkpoint_id, 0)
                encoded = tape([
                    record(1, 0, 0, 0),
                    record(5, 1, 0, 0, projection()),
                    record(6, 2, 0, 0, checkpoint),
                    record(11, 3, 0, 0),
                ])
                self.assert_c_status(encoded, "schema")


def main() -> int:
    global TAPE_CLI
    parser = argparse.ArgumentParser()
    parser.add_argument("--tape", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    TAPE_CLI = args.tape.resolve()
    suite = (unittest.defaultTestLoader.loadTestsFromNames(remaining, module=sys.modules[__name__])
             if remaining else
             unittest.defaultTestLoader.loadTestsFromTestCase(TapeContractTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
