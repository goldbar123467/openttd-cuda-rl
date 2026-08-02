#!/usr/bin/env python3
"""Typed client for standalone and in-game-adapter M10 ONNX inference."""

from __future__ import annotations

import dataclasses
import pathlib
import struct
import subprocess
from typing import BinaryIO, Sequence


REQUEST_MAGIC = b"OTRLDS01"
RESPONSE_MAGIC = b"OTRLDR01"
INSPECT = 2
CLOSE = 4
MAXIMUM_FRAME_BYTES = 64 * 1024 * 1024
STRUCTURED_FEATURES = 256
SPATIAL_FEATURES = 32 * 32 * 32
ACTION_COUNT = 41


class M10DeploymentClientError(RuntimeError):
    """The M10 ONNX deployment service failed or violated its protocol."""


@dataclasses.dataclass(frozen=True)
class InspectionResult:
    action: int
    log_probability: float
    value: float
    logits: tuple[float, ...]
    probabilities: tuple[float, ...]


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise M10DeploymentClientError("deployment response was truncated")
        data.extend(chunk)
    return bytes(data)


def _decode_string(payload: bytes, offset: int = 0) -> tuple[str, int]:
    if len(payload) - offset < 4:
        raise M10DeploymentClientError("deployment string was truncated")
    length = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    if length > 65_535 or len(payload) - offset < length:
        raise M10DeploymentClientError("deployment string length is invalid")
    return payload[offset:offset + length].decode("utf-8", errors="replace"), offset + length


class DeploymentClient:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise M10DeploymentClientError("deployment process lacks required pipes")
        self.process = process
        self.input = process.stdin
        self.output = process.stdout
        self.errors = process.stderr

    @classmethod
    def start(cls, executable: pathlib.Path, *, package: pathlib.Path, sampling_seed: int, mode: str) -> "DeploymentClient":
        if not executable.is_absolute() or not executable.is_file() or not package.is_absolute() or not package.is_dir():
            raise M10DeploymentClientError("deployment executable/package must be existing absolute paths")
        if sampling_seed < 0 or mode not in ("standalone", "ingame"):
            raise M10DeploymentClientError("invalid deployment seed/mode")
        return cls(subprocess.Popen(
            [str(executable), "--package", str(package), "--sampling-seed", str(sampling_seed), "--mode", mode],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ))

    def _request(self, message_type: int, payload: bytes) -> bytes:
        self.input.write(struct.pack("<8sIQ", REQUEST_MAGIC, message_type, len(payload)) + payload)
        self.input.flush()
        header = _read_exact(self.output, 24)
        magic, response_type, status, length = struct.unpack("<8sIIQ", header)
        if magic != RESPONSE_MAGIC or response_type != message_type or length > MAXIMUM_FRAME_BYTES:
            raise M10DeploymentClientError("deployment response header is invalid")
        response = _read_exact(self.output, length)
        if status != 0:
            message, offset = _decode_string(response)
            if offset != len(response):
                raise M10DeploymentClientError("deployment error response has trailing bytes")
            raise M10DeploymentClientError(message)
        return response

    def inspect(
        self,
        structured: Sequence[Sequence[float]],
        spatial: Sequence[Sequence[float]],
        masks: Sequence[Sequence[int]],
        *,
        deterministic: bool,
    ) -> list[InspectionResult]:
        if not structured or len(structured) != len(spatial) or len(structured) != len(masks) or len(structured) > 64:
            raise M10DeploymentClientError("deployment batch must contain one to 64 aligned rows")
        if any(len(row) != STRUCTURED_FEATURES for row in structured) or any(len(row) != SPATIAL_FEATURES for row in spatial):
            raise M10DeploymentClientError("deployment observation row shape drifted")
        if any(len(row) != ACTION_COUNT or any(value not in (0, 1, False, True) for value in row) for row in masks):
            raise M10DeploymentClientError("deployment legal mask row drifted")
        payload = bytearray(struct.pack("<IB", len(structured), int(deterministic)))
        for row in structured:
            payload.extend(struct.pack(f"<{STRUCTURED_FEATURES}f", *row))
        for row in spatial:
            payload.extend(struct.pack(f"<{SPATIAL_FEATURES}f", *row))
        for row in masks:
            payload.extend(bytes(row))
        response = self._request(INSPECT, bytes(payload))
        if len(response) < 4:
            raise M10DeploymentClientError("deployment INSPECT response is truncated")
        count = struct.unpack_from("<I", response)[0]
        row_bytes = 24 + 2 * ACTION_COUNT * 8
        if count != len(structured) or len(response) != 4 + count * row_bytes:
            raise M10DeploymentClientError("deployment INSPECT response shape is invalid")
        result = []
        for index in range(count):
            offset = 4 + index * row_bytes
            action, log_probability, value = struct.unpack_from("<qdd", response, offset)
            offset += 24
            logits = struct.unpack_from(f"<{ACTION_COUNT}d", response, offset)
            offset += ACTION_COUNT * 8
            probabilities = struct.unpack_from(f"<{ACTION_COUNT}d", response, offset)
            result.append(InspectionResult(action, log_probability, value, logits, probabilities))
        return result

    def close(self, timeout: float = 30.0) -> tuple[str, str]:
        response = self._request(CLOSE, b"")
        package_id, offset = _decode_string(response)
        model_sha256, offset = _decode_string(response, offset)
        if offset != len(response) or len(package_id) != 64 or len(model_sha256) != 64:
            raise M10DeploymentClientError("deployment CLOSE response shape is invalid")
        self.input.close()
        self.output.close()
        code = self.process.wait(timeout=timeout)
        errors = self.errors.read()
        self.errors.close()
        if code != 0 or errors:
            raise M10DeploymentClientError(f"deployment failed rc={code} stderr={errors.decode(errors='replace')!r}")
        return package_id, model_sha256

    def abort(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        for stream in (self.input, self.output, self.errors):
            if not stream.closed:
                stream.close()
        self.process.wait(timeout=30.0)
