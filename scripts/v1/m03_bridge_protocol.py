#!/usr/bin/env python3
"""M03 checksummed bridge framing and local worker-process client."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import select
import struct
import subprocess
import time
from typing import Any


MAGIC = b"ORL1"
PROTOCOL_MAJOR = 1
PROTOCOL_MINOR = 0
HEADER = struct.Struct("<4sHHHHIIIQQQQ")
HEADER_BYTES = 56
MAXIMUM_PAYLOAD_BYTES = 1_048_576
FLAG_RESPONSE = 1
FLAG_ERROR = 2

RESET = 1
SNAPSHOT = 2
LEGAL_ACTIONS = 3
STEP = 4
PAUSE = 5
RESUME = 6
CLOSE = 7


class M03BridgeProtocolError(ValueError):
    """The local frame stream or worker response violated the M03 contract."""


class M03BridgeTimeout(TimeoutError):
    """The worker did not complete a bounded control operation in time."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M03BridgeProtocolError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _response_is_compact_sorted(value: Any, payload: bytes) -> bool:
    """Accept cross-language shortest float spellings while retaining canonical structure."""
    def normalize_numbers(encoded: bytes) -> bytes:
        output = bytearray()
        index = 0
        in_string = False
        escaped = False
        while index < len(encoded):
            byte = encoded[index]
            if in_string:
                output.append(byte)
                if escaped:
                    escaped = False
                elif byte == ord("\\"):
                    escaped = True
                elif byte == ord('"'):
                    in_string = False
                index += 1
            elif byte == ord('"'):
                in_string = True
                output.append(byte)
                index += 1
            elif byte == ord("-") or ord("0") <= byte <= ord("9"):
                output.append(ord("#"))
                index += 1
                while index < len(encoded) and encoded[index] in b"0123456789+-.eE":
                    index += 1
            else:
                output.append(byte)
                index += 1
        return bytes(output)

    return isinstance(value, dict) and normalize_numbers(payload) == normalize_numbers(canonical_bytes(value))


def crc32c(value: bytes | bytearray) -> int:
    crc = 0xFFFFFFFF
    for byte in value:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return (~crc) & 0xFFFFFFFF


@dataclasses.dataclass(frozen=True)
class Frame:
    message_type: int
    flags: int
    payload_length: int
    checksum: int
    session_id: int
    episode_id: int
    request_id: int
    transition_ordinal: int
    payload: dict[str, Any]
    payload_bytes: bytes


def encode_frame(
    *,
    message_type: int,
    flags: int,
    session_id: int,
    episode_id: int,
    request_id: int,
    transition_ordinal: int,
    payload: dict[str, Any],
    checksum_override: int | None = None,
) -> bytes:
    payload_bytes = canonical_bytes(payload)
    if len(payload_bytes) > MAXIMUM_PAYLOAD_BYTES:
        raise M03BridgeProtocolError("payload exceeds the M03 frame bound")
    header = bytearray(
        HEADER.pack(
            MAGIC,
            PROTOCOL_MAJOR,
            PROTOCOL_MINOR,
            message_type,
            flags,
            len(payload_bytes),
            0,
            0,
            session_id,
            episode_id,
            request_id,
            transition_ordinal,
        )
    )
    checksum = crc32c(header + payload_bytes)
    struct.pack_into("<I", header, 16, checksum if checksum_override is None else checksum_override)
    return bytes(header) + payload_bytes


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        try:
            count = os.write(descriptor, value[offset:])
        except InterruptedError:
            continue
        if count <= 0:
            raise M03BridgeProtocolError("control write made no progress")
        offset += count


def _read_exact(descriptor: int, size: int, deadline: float) -> bytes:
    value = bytearray()
    while len(value) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise M03BridgeTimeout(f"control read timed out with {size - len(value)} bytes pending")
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            raise M03BridgeTimeout(f"control read timed out with {size - len(value)} bytes pending")
        try:
            block = os.read(descriptor, size - len(value))
        except InterruptedError:
            continue
        if not block:
            raise M03BridgeProtocolError(
                f"control response truncated with {size - len(value)} bytes pending"
            )
        value.extend(block)
    return bytes(value)


def decode_frame(descriptor: int, timeout: float) -> Frame:
    deadline = time.monotonic() + timeout
    header_bytes = _read_exact(descriptor, HEADER_BYTES, deadline)
    (
        magic,
        major,
        minor,
        message_type,
        flags,
        payload_length,
        checksum,
        reserved,
        session_id,
        episode_id,
        request_id,
        transition_ordinal,
    ) = HEADER.unpack(header_bytes)
    if magic != MAGIC:
        raise M03BridgeProtocolError(f"response magic mismatch: {magic!r}")
    if (major, minor) != (PROTOCOL_MAJOR, PROTOCOL_MINOR):
        raise M03BridgeProtocolError(f"response protocol mismatch: {major}.{minor}")
    if flags not in (FLAG_RESPONSE, FLAG_RESPONSE | FLAG_ERROR):
        raise M03BridgeProtocolError(f"response flags are invalid: {flags}")
    if reserved != 0:
        raise M03BridgeProtocolError("response reserved header field is nonzero")
    if payload_length > MAXIMUM_PAYLOAD_BYTES:
        raise M03BridgeProtocolError("response payload exceeds the M03 frame bound")
    payload_bytes = _read_exact(descriptor, payload_length, deadline)
    checksum_header = bytearray(header_bytes)
    struct.pack_into("<I", checksum_header, 16, 0)
    observed_checksum = crc32c(checksum_header + payload_bytes)
    if observed_checksum != checksum:
        raise M03BridgeProtocolError(
            f"response CRC32C mismatch: expected={checksum} actual={observed_checksum}"
        )
    try:
        payload = json.loads(
            payload_bytes.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M03BridgeProtocolError(f"nonstandard JSON constant: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M03BridgeProtocolError(f"response payload is invalid JSON: {exc}") from exc
    if not _response_is_compact_sorted(payload, payload_bytes):
        raise M03BridgeProtocolError("response payload is not a canonical compact JSON object")
    return Frame(
        message_type=message_type,
        flags=flags,
        payload_length=payload_length,
        checksum=checksum,
        session_id=session_id,
        episode_id=episode_id,
        request_id=request_id,
        transition_ordinal=transition_ordinal,
        payload=payload,
        payload_bytes=payload_bytes,
    )


class Client:
    """Synchronous exactly-ordered controller for one inherited-pipe worker."""

    def __init__(self, request_descriptor: int, response_descriptor: int, timeout: float) -> None:
        self.request_descriptor = request_descriptor
        self.response_descriptor = response_descriptor
        self.timeout = timeout

    def request(
        self,
        *,
        message_type: int,
        session_id: int,
        episode_id: int,
        request_id: int,
        transition_ordinal: int,
        payload: dict[str, Any],
        checksum_override: int | None = None,
    ) -> Frame:
        encoded = encode_frame(
            message_type=message_type,
            flags=0,
            session_id=session_id,
            episode_id=episode_id,
            request_id=request_id,
            transition_ordinal=transition_ordinal,
            payload=payload,
            checksum_override=checksum_override,
        )
        _write_all(self.request_descriptor, encoded)
        response = decode_frame(self.response_descriptor, self.timeout)
        if response.message_type != message_type:
            raise M03BridgeProtocolError(
                f"response message type mismatch: expected={message_type} actual={response.message_type}"
            )
        if response.request_id != request_id:
            raise M03BridgeProtocolError(
                f"response request ID mismatch: expected={request_id} actual={response.request_id}"
            )
        return response

    def close_descriptors(self) -> None:
        for descriptor in (self.request_descriptor, self.response_descriptor):
            try:
                os.close(descriptor)
            except OSError:
                pass


@dataclasses.dataclass
class WorkerProcess:
    process: subprocess.Popen[bytes]
    client: Client
    command: list[str]

    @classmethod
    def start(
        cls,
        *,
        executable: pathlib.Path,
        instance: pathlib.Path,
        run_root: pathlib.Path,
        timeout: float,
    ) -> "WorkerProcess":
        run_root.mkdir(parents=True, exist_ok=False)
        worker_read, controller_write = os.pipe()
        controller_read, worker_write = os.pipe()
        command = [
            str(executable),
            "-X",
            "-v",
            "null:ticks=1",
            "-s",
            "null",
            "-m",
            "null",
            "-b",
            "null",
            "-I",
            "OpenGFX",
            "-Q",
            "-x",
            "-c",
            str(run_root / "openttd.cfg"),
            "-B",
            f"{worker_read}:{worker_write}",
            "-Z",
            str(instance),
        ]
        try:
            process = subprocess.Popen(
                command,
                cwd=executable.parent,
                pass_fds=(worker_read, worker_write),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "LANG": "C",
                    "LC_ALL": "C",
                    "TZ": "UTC",
                    "SOURCE_DATE_EPOCH": "1742688000",
                },
            )
        except Exception:
            for descriptor in (
                worker_read,
                controller_write,
                controller_read,
                worker_write,
            ):
                os.close(descriptor)
            raise
        os.close(worker_read)
        os.close(worker_write)
        return cls(
            process=process,
            client=Client(controller_write, controller_read, timeout),
            command=command,
        )

    def finish(self, timeout: float) -> tuple[int, bytes, bytes]:
        self.client.close_descriptors()
        try:
            stdout, stderr = self.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self.process.kill()
            stdout, stderr = self.process.communicate()
            raise M03BridgeTimeout(f"worker exit timed out after {timeout} seconds") from exc
        return self.process.returncode, stdout, stderr

    def terminate_for_timeout_evidence(self) -> tuple[int, bytes, bytes]:
        self.client.close_descriptors()
        self.process.kill()
        stdout, stderr = self.process.communicate()
        return self.process.returncode, stdout, stderr
