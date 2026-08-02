#!/usr/bin/env python3
"""Bounded little-endian client for the native M07 PPO trainer service."""

from __future__ import annotations

import dataclasses
import pathlib
import struct
import subprocess
from typing import BinaryIO, Sequence


REQUEST_MAGIC = b"OTRLPS01"
RESPONSE_MAGIC = b"OTRLPR01"
ACT = 1
UPDATE = 2
CHECKPOINT = 3
CLOSE = 4
MAXIMUM_FRAME_BYTES = 64 * 1024 * 1024
STRUCTURED_FEATURES = 256
ACTION_COUNT = 41


class M07TrainerClientError(RuntimeError):
    """The native trainer service failed or violated its protocol."""


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
    observation: Sequence[float]
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
            raise M07TrainerClientError("native trainer response was truncated")
        data.extend(chunk)
    return bytes(data)


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if len(encoded) > 65_535:
        raise M07TrainerClientError("trainer protocol string exceeds bound")
    return struct.pack("<I", len(encoded)) + encoded


def _decode_string(payload: bytes, offset: int = 0) -> tuple[str, int]:
    if offset + 4 > len(payload):
        raise M07TrainerClientError("trainer protocol string is truncated")
    length = struct.unpack_from("<I", payload, offset)[0]
    offset += 4
    if length > 65_535 or offset + length > len(payload):
        raise M07TrainerClientError("trainer protocol string length is invalid")
    try:
        return payload[offset : offset + length].decode("utf-8"), offset + length
    except UnicodeDecodeError as exc:
        raise M07TrainerClientError("trainer protocol string is not UTF-8") from exc


class TrainerClient:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise M07TrainerClientError("trainer process lacks required pipes")
        self.process = process
        self.input = process.stdin
        self.output = process.stdout
        self.errors = process.stderr

    @classmethod
    def start(
        cls,
        executable: pathlib.Path,
        *,
        run_seed: int | None = None,
        rollout_length: int = 128,
        environment_count: int = 1,
        minibatch_size: int = 32,
        optimization_epochs: int = 4,
        resume: pathlib.Path | None = None,
        diagnostic_root: pathlib.Path,
    ) -> "TrainerClient":
        if not executable.is_absolute() or not executable.is_file():
            raise M07TrainerClientError("trainer executable must be an existing absolute file")
        if not diagnostic_root.is_absolute():
            raise M07TrainerClientError("diagnostic root must be absolute")
        command = [str(executable), "--service", "--diagnostic-root", str(diagnostic_root)]
        if resume is not None:
            if run_seed is not None or not resume.is_absolute():
                raise M07TrainerClientError("resume must be absolute and cannot override the checkpoint seed")
            command.extend(("--resume", str(resume)))
        else:
            if run_seed is None or run_seed < 0:
                raise M07TrainerClientError("new trainer service requires a nonnegative run seed")
            command.extend(
                (
                    "--run-seed",
                    str(run_seed),
                    "--rollout-length",
                    str(rollout_length),
                    "--environment-count",
                    str(environment_count),
                    "--minibatch-size",
                    str(minibatch_size),
                    "--optimization-epochs",
                    str(optimization_epochs),
                )
            )
        return cls(
            subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        )

    def _request(self, message_type: int, payload: bytes) -> bytes:
        if len(payload) > MAXIMUM_FRAME_BYTES:
            raise M07TrainerClientError("trainer request exceeds frame bound")
        self.input.write(struct.pack("<8sIQ", REQUEST_MAGIC, message_type, len(payload)) + payload)
        self.input.flush()
        header = _read_exact(self.output, 24)
        magic, response_type, status, length = struct.unpack("<8sIIQ", header)
        if magic != RESPONSE_MAGIC or response_type != message_type or length > MAXIMUM_FRAME_BYTES:
            raise M07TrainerClientError("trainer response header is invalid")
        response = _read_exact(self.output, length)
        if status != 0:
            message, offset = _decode_string(response)
            if offset != len(response):
                raise M07TrainerClientError("trainer error response has trailing bytes")
            raise M07TrainerClientError(message)
        return response

    def act(
        self,
        observations: Sequence[Sequence[float]],
        masks: Sequence[Sequence[int]],
        *,
        deterministic: bool = False,
    ) -> list[ActionResult]:
        if not observations or len(observations) != len(masks) or len(observations) > 64:
            raise M07TrainerClientError("ACT batch must contain one to 64 aligned rows")
        payload = bytearray(struct.pack("<IB", len(observations), int(deterministic)))
        for row in observations:
            if len(row) != STRUCTURED_FEATURES:
                raise M07TrainerClientError("ACT observation does not have 256 features")
            payload.extend(struct.pack(f"<{STRUCTURED_FEATURES}f", *row))
        for row in masks:
            if len(row) != ACTION_COUNT or any(value not in (0, 1, False, True) for value in row):
                raise M07TrainerClientError("ACT mask is not 41 booleans")
            payload.extend(bytes(row))
        response = self._request(ACT, bytes(payload))
        if len(response) < 4:
            raise M07TrainerClientError("ACT response is truncated")
        count = struct.unpack_from("<I", response)[0]
        if count != len(observations) or len(response) != 4 + count * 24:
            raise M07TrainerClientError("ACT response shape is invalid")
        return [ActionResult(*struct.unpack_from("<qdd", response, 4 + index * 24)) for index in range(count)]

    def update(self, transitions: Sequence[Transition]) -> UpdateResult:
        if not transitions:
            raise M07TrainerClientError("UPDATE requires transitions")
        payload = bytearray(struct.pack("<I", len(transitions)))
        for transition in transitions:
            if len(transition.observation) != STRUCTURED_FEATURES:
                raise M07TrainerClientError("UPDATE observation does not have 256 features")
            payload.extend(struct.pack(f"<{STRUCTURED_FEATURES}f", *transition.observation))
        for transition in transitions:
            if len(transition.legal_mask) != ACTION_COUNT:
                raise M07TrainerClientError("UPDATE mask does not have 41 actions")
            payload.extend(bytes(transition.legal_mask))
        for transition in transitions:
            payload.extend(
                struct.pack(
                    "<qddddBB",
                    transition.action,
                    transition.old_log_probability,
                    transition.old_value,
                    transition.reward,
                    transition.next_value,
                    int(transition.bootstrap),
                    int(transition.continuation),
                )
            )
        response = self._request(UPDATE, bytes(payload))
        if len(response) != 80:
            raise M07TrainerClientError("UPDATE response shape is invalid")
        values = struct.unpack("<8dQQ", response)
        return UpdateResult(*values)

    def checkpoint(
        self,
        root: pathlib.Path,
        *,
        run_name: str,
        repository_commit: str,
        source_build_identity: str,
        parent_checkpoint: str,
        development_evaluation_json: str,
    ) -> tuple[str, pathlib.Path]:
        if not root.is_absolute():
            raise M07TrainerClientError("checkpoint root must be absolute")
        response = self._request(
            CHECKPOINT,
            b"".join(
                _string(value)
                for value in (
                    str(root),
                    run_name,
                    repository_commit,
                    source_build_identity,
                    parent_checkpoint,
                    development_evaluation_json,
                )
            ),
        )
        identity, offset = _decode_string(response)
        path, offset = _decode_string(response, offset)
        if offset != len(response) or len(identity) != 64:
            raise M07TrainerClientError("CHECKPOINT response is invalid")
        return identity, pathlib.Path(path)

    def close(self, timeout: float = 30.0) -> None:
        self._request(CLOSE, b"")
        self.input.close()
        self.output.close()
        code = self.process.wait(timeout=timeout)
        errors = self.errors.read()
        self.errors.close()
        if code != 0 or errors:
            raise M07TrainerClientError(
                f"trainer service failed rc={code} stderr={errors.decode(errors='replace')!r}"
            )

    def abort(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        if not self.input.closed:
            self.input.close()
        if not self.output.closed:
            self.output.close()
        if not self.errors.closed:
            self.errors.close()
        self.process.wait(timeout=30.0)
