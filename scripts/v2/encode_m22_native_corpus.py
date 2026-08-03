#!/usr/bin/env python3
"""Encode the validated M22 JSON corpus into the bounded native trainer format."""

from __future__ import annotations

import argparse
import hashlib
import math
import pathlib
import struct
import sys
from dataclasses import dataclass

import validate_m22_native_corpus


MAGIC = b"OTRLM22C"
VERSION = 1
FEATURES = 32
PROGRAMS = 17
MAX_BYTES = 1 << 20
CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
CORPUS = pathlib.Path("config/v2/m22-native-corpus.json")
PROGRAM_INDEX = {item: index for index, item in enumerate(validate_m22_native_corpus.builder.PROGRAMS)}
OPPONENT_FEATURE = {"not-applicable": 0.0, "AAAHogEx": 1.0 / 3.0, "KrakenAI2": 2.0 / 3.0, "NoOpAI": 1.0}


class M22CorpusEncodingError(ValueError):
    """The frozen JSON corpus cannot be represented by the native trainer format."""


@dataclass(frozen=True)
class DecodedEntry:
    split: str
    program: int
    sampler_seed: int
    entry_id: str
    public_features: tuple[float, ...]
    program_mask: tuple[bool, ...]
    rewards: tuple[float, ...]


@dataclass(frozen=True)
class DecodedCorpus:
    learning_contract_sha256: str
    corpus_sha256: str
    entries: tuple[DecodedEntry, ...]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22CorpusEncodingError(message)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def context_feature(cargo: str, variant: str) -> float:
    digest = hashlib.sha256(cargo.encode("utf-8") + b"\0" + variant.encode("utf-8")).digest()
    return f32(int.from_bytes(digest[:4], "big") / 0xFFFFFFFF)


def public_features(entry: dict[str, object]) -> list[float]:
    state = entry["public_state"]
    require(isinstance(state, dict), "corpus public state is not an object")
    mode = int(state["mode_index"])
    climate = int(state["climate_index"])
    width, height = int(state["map_width"]), int(state["map_height"])
    capabilities = state["capabilities"]
    require(0 <= mode < 7 and 0 <= climate < 4, "public mode/climate index is out of range")
    require(0 < width <= 1024 and 0 < height <= 1024, "public map dimensions exceed M22")
    require(isinstance(capabilities, list) and len(capabilities) == 16 and set(capabilities) <= {0, 1},
            "public capabilities are not 16 binary fields")
    result = [0.0] * FEATURES
    result[mode] = 1.0
    result[7 + climate] = 1.0
    result[11] = f32(width / 4096.0)
    result[12] = f32(height / 4096.0)
    result[13] = f32((width * height) / 1048576.0)
    result[14:30] = [float(value) for value in capabilities]
    opponent = str(state["opponent"])
    require(opponent in OPPONENT_FEATURE, f"unknown public opponent: {opponent}")
    result[30] = f32(OPPONENT_FEATURE[opponent])
    result[31] = context_feature(str(state["cargo"]), str(state["variant"]))
    require(all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in result),
            "encoded public feature is nonfinite or out of range")
    return result


def encode(root: pathlib.Path) -> bytes:
    root = root.resolve()
    validate_m22_native_corpus.validate(root)
    corpus = validate_m22_native_corpus.load(root / CORPUS)
    contract_sha = sha256(root / CONTRACT)
    corpus_sha = sha256(root / CORPUS)
    output = bytearray(MAGIC)
    output += struct.pack("<I", VERSION)
    output += contract_sha.encode("ascii")
    output += corpus_sha.encode("ascii")
    output += struct.pack("<I", len(corpus["entries"]))
    for entry in corpus["entries"]:
        split = {"training": 0, "development": 1}.get(entry["split"])
        require(split is not None, "native trainer corpus contains a forbidden split")
        program = PROGRAM_INDEX.get(entry["program"])
        require(program is not None and program > 0, "native trainer corpus program is unknown or WAIT")
        entry_id = entry["entry_id"].encode("ascii")
        require(0 < len(entry_id) <= 128, "native trainer entry ID length is invalid")
        mask = [program_id in entry["legal_programs"] for program_id in PROGRAM_INDEX]
        rewards = [float(entry["rewards"].get(program_id, 0.0)) for program_id in PROGRAM_INDEX]
        require(mask[0] and mask[program] and sum(mask) == 2, "native trainer legal mask drifted")
        require(rewards[0] == 0.0 and rewards[program] > 0.0 and
                all(math.isfinite(value) for value in rewards), "native trainer rewards drifted")
        output += struct.pack("<BBHIH", split, program, 0, int(entry["sampler_seed"]), len(entry_id))
        output += entry_id
        output += struct.pack(f"<{FEATURES}f", *public_features(entry))
        output += bytes(mask)
        output += struct.pack(f"<{PROGRAMS}d", *rewards)
    require(len(output) <= MAX_BYTES, "native trainer corpus exceeds its byte budget")
    return bytes(output)


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, count: int) -> bytes:
        require(0 <= count <= len(self.data) - self.offset, "native trainer corpus is truncated")
        result = self.data[self.offset:self.offset + count]
        self.offset += count
        return result

    def unpack(self, layout: str) -> tuple[object, ...]:
        size = struct.calcsize(layout)
        return struct.unpack(layout, self.take(size))


def decode(data: bytes) -> DecodedCorpus:
    require(len(data) <= MAX_BYTES, "native trainer corpus exceeds its byte budget")
    reader = Reader(data)
    require(reader.take(len(MAGIC)) == MAGIC, "native trainer corpus magic mismatch")
    require(reader.unpack("<I")[0] == VERSION, "native trainer corpus version mismatch")
    contract_sha = reader.take(64).decode("ascii")
    corpus_sha = reader.take(64).decode("ascii")
    require(all(len(value) == 64 and not set(value) - set("0123456789abcdef")
                for value in (contract_sha, corpus_sha)), "native trainer corpus identity is malformed")
    count = int(reader.unpack("<I")[0])
    require(count == 32, "native trainer corpus entry count drifted")
    entries: list[DecodedEntry] = []
    for _index in range(count):
        split, program, reserved, sampler_seed, name_length = reader.unpack("<BBHIH")
        require(split in (0, 1) and 1 <= program < PROGRAMS and reserved == 0 and
                0 < sampler_seed <= 0x7FFFFFFF and 0 < name_length <= 128,
                "native trainer entry header is invalid")
        entry_id = reader.take(int(name_length)).decode("ascii")
        features = tuple(float(value) for value in reader.unpack(f"<{FEATURES}f"))
        masks = tuple(bool(value) for value in reader.take(PROGRAMS))
        rewards = tuple(float(value) for value in reader.unpack(f"<{PROGRAMS}d"))
        require(all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in features),
                "decoded public feature is invalid")
        require(masks[0] and masks[program] and sum(masks) == 2, "decoded program mask drifted")
        require(rewards[0] == 0.0 and rewards[program] > 0.0 and all(math.isfinite(value) for value in rewards),
                "decoded rewards drifted")
        entries.append(DecodedEntry("training" if split == 0 else "development", int(program),
                                    int(sampler_seed), entry_id, features, masks, rewards))
    require(reader.offset == len(data), "native trainer corpus has trailing bytes")
    require(len({item.entry_id for item in entries}) == 32, "native trainer corpus IDs are not unique")
    for split in ("training", "development"):
        require([item.program for item in entries if item.split == split] == list(range(1, PROGRAMS)),
                f"native trainer {split} program order drifted")
    return DecodedCorpus(contract_sha, corpus_sha, tuple(entries))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        require(not output.exists() and not output.is_symlink(), f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        data = encode(args.root)
        decoded = decode(data)
        output.write_bytes(data)
        print(f"V2_M22_CORPUS_BINARY=PASS entries={len(decoded.entries)} bytes={len(data)} "
              f"sha256={hashlib.sha256(data).hexdigest()} output={output}")
        return 0
    except (M22CorpusEncodingError, OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_CORPUS_BINARY=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
