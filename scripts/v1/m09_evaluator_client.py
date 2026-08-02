#!/usr/bin/env python3
"""Bounded typed client for the optimizer-free native M09 evaluator."""

from __future__ import annotations

import dataclasses
import pathlib
import struct
import subprocess
from typing import BinaryIO, Sequence


REQUEST_MAGIC = b"OTRLES01"
RESPONSE_MAGIC = b"OTRLER01"
ACT = 1
CLOSE = 4
MAXIMUM_FRAME_BYTES = 64 * 1024 * 1024
STRUCTURED_FEATURES = 256
SPATIAL_FEATURES = 32 * 32 * 32
ACTION_COUNT = 41


class M09EvaluatorClientError(RuntimeError):
    """The native read-only evaluator failed or violated its protocol."""


@dataclasses.dataclass(frozen=True)
class ActionResult:
    action: int
    log_probability: float
    value: float


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise M09EvaluatorClientError("native M09 evaluator response was truncated")
        data.extend(chunk)
    return bytes(data)


def _decode_string(payload: bytes, offset: int = 0) -> tuple[str, int]:
    if len(payload) - offset < 4:
        raise M09EvaluatorClientError("native M09 evaluator string was truncated")
    length = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    if length > 65_535 or len(payload) - offset < length:
        raise M09EvaluatorClientError("native M09 evaluator string length is invalid")
    return payload[offset:offset + length].decode("utf-8", errors="replace"), offset + length


class EvaluatorClient:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise M09EvaluatorClientError("evaluator process lacks required pipes")
        self.process = process
        self.input = process.stdin
        self.output = process.stdout
        self.errors = process.stderr

    @classmethod
    def start(
        cls,
        executable: pathlib.Path,
        *,
        package: pathlib.Path,
        sampling_seed: int,
    ) -> "EvaluatorClient":
        if not executable.is_absolute() or not executable.is_file():
            raise M09EvaluatorClientError("evaluator executable must be an existing absolute file")
        if not package.is_absolute() or not package.is_dir() or sampling_seed < 0:
            raise M09EvaluatorClientError("invalid evaluator launch configuration")
        return cls(subprocess.Popen(
            [str(executable), "--package", str(package), "--sampling-seed", str(sampling_seed)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ))

    def _request(self, message_type: int, payload: bytes) -> bytes:
        if len(payload) > MAXIMUM_FRAME_BYTES:
            raise M09EvaluatorClientError("M09 evaluator request exceeds frame bound")
        self.input.write(struct.pack("<8sIQ", REQUEST_MAGIC, message_type, len(payload)) + payload)
        self.input.flush()
        header = _read_exact(self.output, 24)
        magic, response_type, status, length = struct.unpack("<8sIIQ", header)
        if magic != RESPONSE_MAGIC or response_type != message_type or length > MAXIMUM_FRAME_BYTES:
            raise M09EvaluatorClientError("M09 evaluator response header is invalid")
        response = _read_exact(self.output, length)
        if status != 0:
            message, offset = _decode_string(response)
            if offset != len(response):
                raise M09EvaluatorClientError("M09 evaluator error response has trailing bytes")
            raise M09EvaluatorClientError(message)
        return response

    def act(
        self,
        structured: Sequence[Sequence[float]],
        spatial: Sequence[Sequence[float]],
        masks: Sequence[Sequence[int]],
        *,
        deterministic: bool,
    ) -> list[ActionResult]:
        if not structured or len(structured) != len(spatial) or len(structured) != len(masks) or len(structured) > 64:
            raise M09EvaluatorClientError("batch must contain one to 64 aligned rows")
        if any(len(row) != STRUCTURED_FEATURES for row in structured):
            raise M09EvaluatorClientError("structured row does not contain 256 values")
        if any(len(row) != SPATIAL_FEATURES for row in spatial):
            raise M09EvaluatorClientError("spatial row does not contain 32768 values")
        if any(len(row) != ACTION_COUNT or any(value not in (0, 1, False, True) for value in row) for row in masks):
            raise M09EvaluatorClientError("legal-mask row is not 41 booleans")
        payload = bytearray(struct.pack("<IB", len(structured), int(deterministic)))
        for row in structured:
            payload.extend(struct.pack(f"<{STRUCTURED_FEATURES}f", *row))
        for row in spatial:
            payload.extend(struct.pack(f"<{SPATIAL_FEATURES}f", *row))
        for row in masks:
            payload.extend(bytes(row))
        response = self._request(ACT, bytes(payload))
        if len(response) < 4:
            raise M09EvaluatorClientError("ACT response is truncated")
        count = struct.unpack_from("<I", response)[0]
        if count != len(structured) or len(response) != 4 + count * 24:
            raise M09EvaluatorClientError("ACT response shape is invalid")
        return [ActionResult(*struct.unpack_from("<qdd", response, 4 + index * 24)) for index in range(count)]

    def close(self, timeout: float = 30.0) -> tuple[str, str]:
        response = self._request(CLOSE, b"")
        package_id, offset = _decode_string(response)
        state_sha256, offset = _decode_string(response, offset)
        if offset != len(response) or len(package_id) != 64 or len(state_sha256) != 64:
            raise M09EvaluatorClientError("CLOSE response shape is invalid")
        self.input.close()
        self.output.close()
        code = self.process.wait(timeout=timeout)
        errors = self.errors.read()
        self.errors.close()
        if code != 0 or errors:
            raise M09EvaluatorClientError(f"evaluator failed rc={code} stderr={errors.decode(errors='replace')!r}")
        return package_id, state_sha256

    def abort(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        for stream in (self.input, self.output, self.errors):
            if not stream.closed:
                stream.close()
        self.process.wait(timeout=30.0)
