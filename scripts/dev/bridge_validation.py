"""Faster, byte-equivalent development implementations of M03 validation.

The original bitwise checksum and byte scanner remain the independent oracle.
This adapter changes neither the frame format nor which checks are performed.
"""
from __future__ import annotations

import re


def _crc_table() -> tuple[int, ...]:
    table = []
    for value in range(256):
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
        table.append(value)
    return tuple(table)


CRC_TABLE = _crc_table()
# Match a complete JSON string first so digits and escaped quotes inside strings
# stay unchanged. The numeric byte alphabet matches M03's scanner exactly.
TOKENS = re.compile(rb'"(?:[^"\\]|\\.)*"|[-0-9][0-9+\-.eE]*')
_original = None


def crc32c(value: bytes | bytearray) -> int:
    crc = 0xFFFFFFFF
    for byte in value:
        crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return (~crc) & 0xFFFFFFFF


def _normalize(encoded: bytes) -> bytes:
    return TOKENS.sub(lambda match: match[0] if match[0][0] == 34 else b"#", encoded)


def response_is_compact_sorted(value, payload: bytes) -> bool:
    import m03_bridge_protocol as protocol
    return isinstance(value, dict) and _normalize(payload) == _normalize(protocol.canonical_bytes(value))


def configure(mode: str) -> None:
    global _original
    if mode not in ("reference", "fast"):
        raise ValueError(f"Unknown bridge validation mode: {mode}")
    import m03_bridge_protocol as protocol
    if _original is None:
        _original = (protocol.crc32c, protocol._response_is_compact_sorted)
    protocol.crc32c, protocol._response_is_compact_sorted = (
        (crc32c, response_is_compact_sorted) if mode == "fast" else _original)
