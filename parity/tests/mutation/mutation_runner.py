#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile and execute deterministic, plausible PORT-004 source mutants."""

from __future__ import annotations

import argparse
import dataclasses
import shutil
import subprocess
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Mutant:
    name: str
    file: str
    old: str
    new: str
    test_id: str


MUTANTS = (
    Mutant("disabled-prefix-magic", "tape_reader.c", "bytes[i] != PREFIX_MAGIC[i]", "0", "P004-PFX-004"),
    Mutant("disabled-major-version", "tape_reader.c", "otrl_get_u16_le(bytes + 8U) != OTRL_FORMAT_MAJOR", "0", "P004-PFX-005"),
    Mutant("disabled-reserved-zero", "tape_reader.c", "otrl_get_u64_le(bytes + 56U) != 0U", "0", "P004-PFX-017"),
    Mutant("unchecked-add", "checked_arithmetic.c", "out == NULL || b > SIZE_MAX - a", "out == NULL && b > SIZE_MAX - a", "P004-ENC-011"),
    Mutant("unchecked-multiply", "checked_arithmetic.c", "out == NULL || (a != 0U && b > SIZE_MAX / a)", "out == NULL || (a != 0U && b > SIZE_MAX / a && 0)", "P004-ENC-012"),
    Mutant("disabled-sequence", "tape_reader.c", "record->sequence != sequence", "0", "P004-REC-010"),
    Mutant("disabled-padding-zero", "tape_reader.c", "bytes[pad] != 0U", "0", "P004-REC-010"),
    Mutant("disabled-trailer-count", "tape_reader.c", "otrl_get_u64_le(bytes + trailer_offset + 8U) != record_count", "0", "P004-TRL-004"),
    Mutant("disabled-sha", "tape_reader.c", "memcmp(digest, bytes + trailer_offset + 24U, 32U) != 0", "0", "P004-TRL-006"),
    Mutant("skip-first-field", "comparator.c", "if (memcmp(af.value, bf.value, af.bytes) != 0)", "if (0)", "P004-CMP-016"),
    Mutant("signed-as-unsigned", "comparator.c", "result->value_signed = af.type >= OTRL_VALUE_I8 && af.type <= OTRL_VALUE_I64;", "result->value_signed = 0U;", "P004-CMP-021"),
    Mutant("overwrite-first-divergence", "comparator.c", "return OTRL_E_DIVERGENCE;\n        }\n    }\n    return OTRL_OK;\n}\n\notrl_status otrl_compare", "continue;\n        }\n    }\n    return OTRL_OK;\n}\n\notrl_status otrl_compare", "P004-CMP-017"),
    Mutant("extra-minimum-boundary", "comparator.c", "required = low - 1U;", "required = low;", "P004-MIN-012"),
    Mutant("misplaced-minimum-digest", "comparator.c", "EVP_DigestFinal_ex(digest, trailer + 24U, &digest_bytes)", "EVP_DigestFinal_ex(digest, trailer + 23U, &digest_bytes)", "P004-MIN-010"),
    Mutant("duplicate-field-id", "tape_reader.c", "field_id <= previous", "field_id < previous", "P004-FLD-006"),
    Mutant("field-width-mismatch", "tape_reader.c", "meta->value_type != type", "0", "P004-FLD-009"),
    Mutant("ignore-fixture-identity", "comparator.c", '"fixture_sha256",', '"source_commit",', "P004-CMP-005"),
    Mutant("ignore-settings-identity", "comparator.c", '"settings_sha256",', '"source_commit",', "P004-CMP-006"),
    Mutant("command-state-before-validation", "tape_reader.c", "*intent_command = command;", "*intent_command = 0U;", "P004-REC-023"),
    Mutant("overwrite-output-promotion", "comparator.c", "link(temporary, path) != 0", "rename(temporary, path) != 0", "P004-MIN-007"),
)


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def test_method(mutant: Mutant) -> str:
    if mutant.name == "command-state-before-validation":
        return "TapeContractTests.test_P004_command_payload_lifecycle"
    test_id = mutant.test_id
    group = test_id.split("-", 2)[1]
    mapping = {
        "PFX": "test_file_prefix_contract",
        "ENC": "test_primitive_encoding_and_golden_vectors",
        "REC": "test_record_framing_contract",
        "TRL": "test_trailer_and_digest_contract",
        "CMP": "test_comparator_contract",
        "MIN": "test_minimizer_contract",
        "FLD": "test_projection_contract",
    }
    return f"TapeContractTests.{mapping[group]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    artifacts = args.artifact_root.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    for mutant in MUTANTS:
        work = artifacts / mutant.name
        source = work / "src"
        include = work / "include"
        fields_include = work / "fields-include"
        work.mkdir()
        shutil.copytree(root / "parity/src", source)
        shutil.copytree(root / "parity/include", include)
        shutil.copytree(root / "parity/include", fields_include)
        target = source / mutant.file
        text = target.read_text()
        count = text.count(mutant.old)
        expected_count = 2 if mutant.name == "signed-as-unsigned" else 1
        if count != expected_count:
            raise RuntimeError(
                f"{mutant.name}: expected {expected_count} mutation anchor(s), found {count}"
            )
        target.write_text(text.replace(mutant.old, mutant.new, expected_count))
        executable = work / "tape-mutant"
        sources = [str(path) for path in sorted(source.glob("*.c"))]
        command = [
            "/usr/bin/clang-16", "-std=c17", "-D_POSIX_C_SOURCE=200809L",
            "-D_XOPEN_SOURCE=700",
            "-O1", "-g", "-Wall", "-Wextra", "-Wpedantic", "-Wconversion",
            "-Wsign-conversion", "-Wshadow", f"-I{include}",
            f"-I{source}", f"-I{fields_include}", *sources,
            str(root / "parity/tools/tape_main.c"), "-lcrypto", "-o",
            str(executable),
        ]
        compiled = run(command, cwd=root)
        (work / "compile.log").write_text(compiled.stdout)
        if compiled.returncode != 0:
            raise RuntimeError(f"{mutant.name}: mutant did not compile")
        unit_executable = work / "unit-mutant"
        unit_command = command[:-4] + [
            str(root / "parity/tests/unit/tape_unit.c"), "-lcrypto", "-o",
            str(unit_executable),
        ]
        unit_compiled = run(unit_command, cwd=root)
        (work / "unit-compile.log").write_text(unit_compiled.stdout)
        if unit_compiled.returncode != 0:
            raise RuntimeError(f"{mutant.name}: unit mutant did not compile")
        unit_tested = run([str(unit_executable)], cwd=root)
        (work / "unit-test.log").write_text(unit_tested.stdout)
        if unit_tested.returncode != 0:
            results.append(f"{mutant.name} {mutant.test_id} KILLED")
            continue
        tested = run([
            str(args.python), str(root / "parity/tests/integration/test_port004.py"),
            "--tape", str(executable), test_method(mutant),
        ], cwd=root)
        (work / "test.log").write_text(tested.stdout)
        if tested.returncode == 0:
            raise RuntimeError(f"{mutant.name}: SURVIVED ({mutant.test_id})")
        results.append(f"{mutant.name} {mutant.test_id} KILLED")
    (artifacts / "mutation-results.txt").write_text("\n".join(results) + "\n")
    print(f"PORT004_MUTATION=PASS killed={len(results)} survived=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
