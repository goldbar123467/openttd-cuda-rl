#!/usr/bin/env python3
"""Decode, independently regenerate, validate, and render M23 native golden records."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import struct
import sys
from dataclasses import dataclass
from typing import Any


MAGIC = b"M23GLD01"
VERSION = 1
ARCHITECTURES = ["monolithic-generalist-v1", "specialist-router-v1"]
CLASSES = ["public-final-projection", "recurrent-sequence-and-reset", "finite-boundary-and-mask-adversarial"]
SEED_DOMAIN = "openttd-rl-v2-m23-golden-v1"
FEATURES = 32
PROGRAMS = 17
HIDDEN = 256
CASES_PER_ARCHITECTURE = 24
MAXIMUM_BYTES = 64 * 1024 * 1024


class GoldenError(ValueError):
    """The M23 native golden file is invalid or no longer matches the frozen generator."""


@dataclass(frozen=True)
class GoldenDefinition:
    case_id: str
    architecture: int
    case_class: int
    sequence: int
    step: int
    mask_pattern: int
    hidden_mode: int
    seed: int
    batch: int
    public_features: list[float]
    program_mask: list[int]
    initial_hidden: list[float]
    recurrent_reset: list[int]


@dataclass(frozen=True)
class GoldenRecord:
    definition: GoldenDefinition
    hidden_input: list[float]
    program_logits: list[float]
    program_value: list[float]
    next_hidden: list[float]
    greedy_program: list[int]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GoldenError(message)


def float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def derived_seed(ordinal: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{SEED_DOMAIN}:{ordinal}".encode("ascii")).digest()[:4], "big") & 0x7FFFFFFF


def next_random(state: int) -> tuple[int, int]:
    mask = (1 << 64) - 1
    state ^= state >> 12
    state ^= (state << 25) & mask
    state ^= state >> 27
    state &= mask
    return state, (state * 2685821657736338717) & mask


def unit_random(state: int) -> tuple[int, float]:
    state, value = next_random(state)
    return state, float32(float(value >> 40) / float32(16777215.0))


def active_program(mode: int, selector: int) -> int:
    programs = [
        [1, 2, 1, 2, 1],
        [3, 4, 3, 4, 3],
        [5, 6, 5, 6, 5],
        [7, 8, 7, 8, 7],
        [9, 10, 9, 10, 9],
        [11, 11, 11, 11, 11],
        [12, 13, 14, 15, 16],
    ]
    return programs[mode][selector % 5]


def generate_definition(architecture: int, local: int) -> GoldenDefinition:
    require(architecture in (0, 1) and 0 <= local < CASES_PER_ARCHITECTURE, "golden generator index invalid")
    seed = derived_seed(architecture * CASES_PER_ARCHITECTURE + local)
    case_class = 0 if local < 8 else 1 if local < 16 else 2
    sequence = 255
    step = 0
    if case_class == 0:
        batch, mask_pattern, hidden_mode = 1, 2, 0
    elif case_class == 1:
        sequence = 0 if local < 12 else 1
        step = (local - 8) % 4
        batch = 8 if sequence == 0 else 32
        mask_pattern = 2 + step % 2
        hidden_mode = 0 if step == 0 else 1
    else:
        adversarial = local - 16
        batch = [1, 8, 32, 1, 8, 32, 8, 32][adversarial]
        mask_pattern = [0, 1, 3, 2, 1, 0, 3, 2][adversarial]
        hidden_mode = 2 if adversarial % 2 == 0 else 0
    class_name = ["public", "recurrent", "adversarial"][case_class]
    case_id = f"{ARCHITECTURES[architecture]}-{class_name}-{local:02d}"
    public = [0.0] * (batch * FEATURES)
    mask = [0] * (batch * PROGRAMS)
    hidden = [0.0] * (batch * HIDDEN)
    reset = [0] * batch
    if case_class != 1 or step == 0:
        reset = [1] * batch
    elif step == 2:
        reset = [1 if row % 2 == 0 else 0 for row in range(batch)]
    sizes = [(64, 64), (128, 128), (512, 128), (1024, 1024)]
    for row in range(batch):
        mode = (local + row) % 7
        climate = (local * 3 + row) % 4
        program = active_program(mode, local + row)
        width, height = sizes[(local + row) % 4]
        offset = row * FEATURES
        public[offset + mode] = 1.0
        public[offset + 7 + climate] = 1.0
        public[offset + 11] = float32(float(width) / float32(4096.0))
        public[offset + 12] = float32(float(height) / float32(4096.0))
        public[offset + 13] = float32(float(width * height) / float32(1048576.0))
        public[offset + 13 + program] = 1.0
        public[offset + 30] = float32(float((local + row) % 4) / float32(3.0))
        random_state = ((seed << 32) | (row + 0x9E3779B9)) & ((1 << 64) - 1)
        random_state, public[offset + 31] = unit_random(random_state)
        if case_class == 2:
            if local == 16:
                public[offset + 31] = 0.0
            if local == 17:
                public[offset + 31] = 1.0
            if local == 18:
                public[offset + 11] = public[offset + 12] = public[offset + 13] = 1.0
        mask_offset = row * PROGRAMS
        if mask_pattern == 0:
            mask[mask_offset] = 1
        elif mask_pattern == 1:
            mask[mask_offset:mask_offset + PROGRAMS] = [1] * PROGRAMS
        elif mask_pattern == 2:
            mask[mask_offset] = mask[mask_offset + program] = 1
        elif mask_pattern == 3:
            mask[mask_offset] = mask[mask_offset + program] = 1
            mask[mask_offset + 1 + ((program + 4) % 16)] = 1
            mask[mask_offset + 1 + ((program + 9) % 16)] = 1
        if hidden_mode == 2:
            for column in range(HIDDEN):
                random_state, unit = unit_random(random_state)
                hidden[row * HIDDEN + column] = float32(float32(unit * float32(1.5)) - float32(0.75))
    return GoldenDefinition(case_id, architecture, case_class, sequence, step, mask_pattern, hidden_mode,
                            seed, batch, public, mask, hidden, reset)


class Reader:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self.offset = 0

    def take(self, count: int) -> bytes:
        require(0 <= count <= len(self.value) - self.offset, "golden file is truncated")
        result = self.value[self.offset:self.offset + count]
        self.offset += count
        return result

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def floating(self) -> float:
        value = struct.unpack("<f", self.take(4))[0]
        require(value == value and value not in (float("inf"), float("-inf")), "golden file has nonfinite float")
        return value

    def string(self) -> str:
        length = self.u16()
        require(1 <= length <= 96, "golden case ID length invalid")
        try:
            return self.take(length).decode("ascii")
        except UnicodeDecodeError as exc:
            raise GoldenError("golden case ID is not ASCII") from exc

    def exact_end(self) -> None:
        require(self.offset == len(self.value), "golden file has trailing bytes")


def decode(path: pathlib.Path) -> list[GoldenRecord]:
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), "golden input must be an absolute regular file")
    value = path.read_bytes()
    require(len(value) <= MAXIMUM_BYTES, "golden input exceeds byte bound")
    reader = Reader(value)
    require(reader.take(8) == MAGIC and reader.u32() == VERSION, "golden magic or version mismatch")
    count = reader.u32()
    require(count == 2 * CASES_PER_ARCHITECTURE, "golden case count mismatch")
    result: list[GoldenRecord] = []
    carried: list[list[list[float] | None]] = [[None, None], [None, None]]
    for index in range(count):
        architecture, case_class, sequence, step = reader.u8(), reader.u8(), reader.u8(), reader.u8()
        mask_pattern, hidden_mode = reader.u8(), reader.u8()
        require(reader.u16() == 0, "golden reserved field nonzero")
        seed, batch, case_id = reader.u32(), reader.u32(), reader.string()
        read_floats = lambda size: [reader.floating() for _ in range(size)]
        read_bytes = lambda size: [reader.u8() for _ in range(size)]
        definition = GoldenDefinition(
            case_id, architecture, case_class, sequence, step, mask_pattern, hidden_mode, seed, batch,
            read_floats(batch * FEATURES), read_bytes(batch * PROGRAMS), read_floats(batch * HIDDEN), read_bytes(batch),
        )
        record = GoldenRecord(
            definition,
            read_floats(batch * HIDDEN),
            read_floats(batch * PROGRAMS),
            read_floats(batch),
            read_floats(batch * HIDDEN),
            [reader.i64() for _ in range(batch)],
        )
        expected = generate_definition(index // CASES_PER_ARCHITECTURE, index % CASES_PER_ARCHITECTURE)
        require(definition == expected, f"golden case definition drifted: {case_id}")
        require(all(value in (0, 1) for value in definition.program_mask + definition.recurrent_reset),
                f"golden boolean byte invalid: {case_id}")
        for row, action in enumerate(record.greedy_program):
            require(0 <= action < PROGRAMS and definition.program_mask[row * PROGRAMS + action] == 1,
                    f"golden action illegal: {case_id}")
        expected_hidden = definition.initial_hidden
        if hidden_mode == 1:
            require(sequence < 2 and carried[architecture][sequence] is not None,
                    f"golden carried hidden has no predecessor: {case_id}")
            expected_hidden = carried[architecture][sequence] or []
        require(record.hidden_input == expected_hidden, f"golden hidden input drifted: {case_id}")
        if case_class == 1:
            carried[architecture][sequence] = record.next_hidden
        result.append(record)
    reader.exact_end()
    return result


def record_json(record: GoldenRecord) -> dict[str, Any]:
    item = record.definition
    return {
        "architecture_id": ARCHITECTURES[item.architecture],
        "batch": item.batch,
        "case_class": CLASSES[item.case_class],
        "case_id": item.case_id,
        "greedy_program": record.greedy_program,
        "hidden_input": record.hidden_input,
        "hidden_mode": ["zero", "carry", "seeded"][item.hidden_mode],
        "mask_pattern": ["wait-only", "all-legal", "one-active-plus-wait", "deterministic-sparse"][item.mask_pattern],
        "next_hidden": record.next_hidden,
        "program_logits": record.program_logits,
        "program_mask": [bool(value) for value in item.program_mask],
        "program_value": record.program_value,
        "public_features": item.public_features,
        "recurrent_reset": [bool(value) for value in item.recurrent_reset],
        "seed": item.seed,
        "sequence": None if item.sequence == 255 else item.sequence,
        "step": item.step,
    }


def write_jsonl(path: pathlib.Path, records: list[GoldenRecord], architecture: str) -> None:
    require(path.is_absolute() and not path.exists() and path.parent.is_dir() and not path.is_symlink(),
            "golden JSONL output must be a new absolute file below an existing directory")
    selected = records if architecture == "all" else [
        item for item in records if ARCHITECTURES[item.definition.architecture] == architecture
    ]
    require(len(selected) == (48 if architecture == "all" else 24), "golden JSONL architecture selection drifted")
    value = "".join(json.dumps(record_json(item), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
                    for item in selected).encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--architecture", choices=["all", *ARCHITECTURES], default="all")
    arguments = parser.parse_args()
    try:
        records = decode(arguments.input)
        if arguments.output is not None:
            write_jsonl(arguments.output, records, arguments.architecture)
        print(f"V2_M23_GOLDEN=PASS cases={len(records)} architecture={arguments.architecture} "
              f"sha256={hashlib.sha256(arguments.input.read_bytes()).hexdigest()}")
        return 0
    except (GoldenError, OSError, ValueError) as exc:
        print(f"V2_M23_GOLDEN=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
