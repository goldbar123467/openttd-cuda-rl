#!/usr/bin/env python3
"""Bounded typed client for the native M08 multimodal PPO service."""

from __future__ import annotations

import dataclasses
import pathlib
import struct
import subprocess
from typing import BinaryIO, Sequence


REQUEST_MAGIC = b"OTRLMS01"
RESPONSE_MAGIC = b"OTRLMR01"
ACT = 1
UPDATE = 2
EXPORT = 3
CLOSE = 4
MAXIMUM_FRAME_BYTES = 64 * 1024 * 1024
STRUCTURED_FEATURES = 256
SPATIAL_FEATURES = 32 * 32 * 32
ACTION_COUNT = 41


class M08TrainerClientError(RuntimeError):
    """The native multimodal trainer failed or violated its protocol."""


@dataclasses.dataclass(frozen=True)
class ActionResult:
    action: int
    log_probability: float
    value: float


@dataclasses.dataclass(frozen=True)
class UpdateResult:
    policy_loss: float
    value_loss: float
    entropy: float
    approximate_kl: float
    clip_fraction: float
    gradient_norm: float
    explained_variance: float
    learning_rate: float
    update: int
    samples: int


@dataclasses.dataclass(frozen=True)
class Transition:
    structured: Sequence[float]
    spatial: Sequence[float]
    legal_mask: Sequence[int]
    action: int
    old_log_probability: float
    old_value: float
    reward: float
    next_value: float
    bootstrap: bool
    continuation: bool


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise M08TrainerClientError("native M08 trainer response was truncated")
        data.extend(chunk)
    return bytes(data)


def _decode_string(payload: bytes) -> str:
    if len(payload) < 4:
        raise M08TrainerClientError("native M08 trainer error response was truncated")
    length = struct.unpack_from("<I", payload)[0]
    if length > 65_535 or len(payload) != 4 + length:
        raise M08TrainerClientError("native M08 trainer error response has invalid length")
    return payload[4:].decode("utf-8", errors="replace")


class TrainerClient:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise M08TrainerClientError("trainer process lacks required pipes")
        self.process = process
        self.input = process.stdin
        self.output = process.stdout
        self.errors = process.stderr

    @classmethod
    def start(
        cls,
        executable: pathlib.Path,
        *,
        architecture: str,
        device: str,
        run_seed: int,
        rollout_length: int,
        environment_count: int,
        minibatch_size: int,
        optimization_epochs: int,
        diagnostic_root: pathlib.Path,
    ) -> "TrainerClient":
        if not executable.is_absolute() or not executable.is_file():
            raise M08TrainerClientError("trainer executable must be an existing absolute file")
        if architecture not in {"structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"}:
            raise M08TrainerClientError("unknown M08 architecture")
        if device not in {"cpu", "cuda:0"} or not diagnostic_root.is_absolute() or run_seed < 0:
            raise M08TrainerClientError("invalid M08 trainer launch configuration")
        command = [
            str(executable),
            "--run-seed", str(run_seed),
            "--rollout-length", str(rollout_length),
            "--environment-count", str(environment_count),
            "--minibatch-size", str(minibatch_size),
            "--optimization-epochs", str(optimization_epochs),
            "--diagnostic-root", str(diagnostic_root),
            "--architecture", architecture,
            "--device", device,
        ]
        return cls(subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))

    def _request(self, message_type: int, payload: bytes) -> bytes:
        if len(payload) > MAXIMUM_FRAME_BYTES:
            raise M08TrainerClientError("M08 trainer request exceeds frame bound")
        self.input.write(struct.pack("<8sIQ", REQUEST_MAGIC, message_type, len(payload)) + payload)
        self.input.flush()
        header = _read_exact(self.output, 24)
        magic, response_type, status, length = struct.unpack("<8sIIQ", header)
        if magic != RESPONSE_MAGIC or response_type != message_type or length > MAXIMUM_FRAME_BYTES:
            raise M08TrainerClientError("M08 trainer response header is invalid")
        response = _read_exact(self.output, length)
        if status != 0:
            raise M08TrainerClientError(_decode_string(response))
        return response

    @staticmethod
    def _validate_batches(
        structured: Sequence[Sequence[float]],
        spatial: Sequence[Sequence[float]],
        masks: Sequence[Sequence[int]],
        *,
        maximum: int,
    ) -> None:
        if not structured or len(structured) != len(spatial) or len(structured) != len(masks) or len(structured) > maximum:
            raise M08TrainerClientError(f"batch must contain one to {maximum} aligned rows")
        if any(len(row) != STRUCTURED_FEATURES for row in structured):
            raise M08TrainerClientError("structured row does not contain 256 values")
        if any(len(row) != SPATIAL_FEATURES for row in spatial):
            raise M08TrainerClientError("spatial row does not contain 32768 values")
        if any(len(row) != ACTION_COUNT or any(value not in (0, 1, False, True) for value in row) for row in masks):
            raise M08TrainerClientError("legal-mask row is not 41 booleans")

    def act(
        self,
        structured: Sequence[Sequence[float]],
        spatial: Sequence[Sequence[float]],
        masks: Sequence[Sequence[int]],
        *,
        deterministic: bool = False,
    ) -> list[ActionResult]:
        self._validate_batches(structured, spatial, masks, maximum=64)
        payload = bytearray(struct.pack("<IB", len(structured), int(deterministic)))
        for row in structured:
            payload.extend(struct.pack(f"<{STRUCTURED_FEATURES}f", *row))
        for row in spatial:
            payload.extend(struct.pack(f"<{SPATIAL_FEATURES}f", *row))
        for row in masks:
            payload.extend(bytes(row))
        response = self._request(ACT, bytes(payload))
        if len(response) < 4:
            raise M08TrainerClientError("ACT response is truncated")
        count = struct.unpack_from("<I", response)[0]
        if count != len(structured) or len(response) != 4 + count * 24:
            raise M08TrainerClientError("ACT response shape is invalid")
        return [ActionResult(*struct.unpack_from("<qdd", response, 4 + index * 24)) for index in range(count)]

    def update(self, transitions: Sequence[Transition]) -> UpdateResult:
        if not transitions:
            raise M08TrainerClientError("UPDATE requires transitions")
        self._validate_batches(
            [transition.structured for transition in transitions],
            [transition.spatial for transition in transitions],
            [transition.legal_mask for transition in transitions],
            maximum=512,
        )
        payload = bytearray(struct.pack("<I", len(transitions)))
        for transition in transitions:
            payload.extend(struct.pack(f"<{STRUCTURED_FEATURES}f", *transition.structured))
        for transition in transitions:
            payload.extend(struct.pack(f"<{SPATIAL_FEATURES}f", *transition.spatial))
        for transition in transitions:
            payload.extend(bytes(transition.legal_mask))
        for transition in transitions:
            payload.extend(struct.pack(
                "<qddddBB",
                transition.action,
                transition.old_log_probability,
                transition.old_value,
                transition.reward,
                transition.next_value,
                int(transition.bootstrap),
                int(transition.continuation),
            ))
        response = self._request(UPDATE, bytes(payload))
        if len(response) != 80:
            raise M08TrainerClientError("UPDATE response shape is invalid")
        return UpdateResult(*struct.unpack("<8dQQ", response))

    @staticmethod
    def _pack_string(value: str) -> bytes:
        encoded = value.encode("utf-8")
        if len(encoded) > 65_535:
            raise M08TrainerClientError("trainer string exceeds bound")
        return struct.pack("<I", len(encoded)) + encoded

    @staticmethod
    def _unpack_string(payload: bytes, offset: int) -> tuple[str, int]:
        if len(payload) - offset < 4:
            raise M08TrainerClientError("EXPORT response string is truncated")
        length = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        if length > 65_535 or len(payload) - offset < length:
            raise M08TrainerClientError("EXPORT response string length is invalid")
        return payload[offset:offset + length].decode("utf-8"), offset + length

    def export_evaluation_model(
        self,
        package_root: pathlib.Path,
        *,
        repository_commit: str,
        training_mean_reward: float,
    ) -> tuple[str, pathlib.Path]:
        if not package_root.is_absolute() or len(repository_commit) != 40:
            raise M08TrainerClientError("invalid evaluation-model export configuration")
        payload = (
            self._pack_string(str(package_root))
            + self._pack_string(repository_commit)
            + struct.pack("<d", training_mean_reward)
        )
        response = self._request(EXPORT, payload)
        package_id, offset = self._unpack_string(response, 0)
        package_path, offset = self._unpack_string(response, offset)
        if offset != len(response) or len(package_id) != 64:
            raise M08TrainerClientError("EXPORT response shape is invalid")
        return package_id, pathlib.Path(package_path)

    def close(self, timeout: float = 30.0) -> None:
        self._request(CLOSE, b"")
        self.input.close()
        self.output.close()
        code = self.process.wait(timeout=timeout)
        errors = self.errors.read()
        self.errors.close()
        if code != 0 or errors:
            raise M08TrainerClientError(f"trainer failed rc={code} stderr={errors.decode(errors='replace')!r}")

    def abort(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        for stream in (self.input, self.output, self.errors):
            if not stream.closed:
                stream.close()
        self.process.wait(timeout=30.0)
