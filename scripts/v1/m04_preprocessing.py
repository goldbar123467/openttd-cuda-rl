#!/usr/bin/env python3
"""Common no-reprocessing adapter for native M04 policy tensors."""

from __future__ import annotations

import dataclasses
import hashlib
import math
import pathlib
import struct
from typing import Any

import validate_m04_observation_contract


class M04PreprocessingError(ValueError):
    """A native tensor or its compatibility identity is invalid."""


@dataclasses.dataclass(frozen=True)
class PolicyTensorBytes:
    consumer: str
    structured: bytes
    spatial: bytes
    combined: bytes
    sha256: str


def _pack_float32(values: Any, expected: int, bounds: tuple[float, float], label: str) -> bytes:
    if not isinstance(values, list) or len(values) != expected:
        raise M04PreprocessingError(f"{label} must contain exactly {expected} values")
    output = bytearray()
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise M04PreprocessingError(f"{label}[{index}] is not numeric")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < bounds[0] or numeric > bounds[1]:
            raise M04PreprocessingError(f"{label}[{index}] is outside {bounds}")
        output.extend(struct.pack("<f", numeric))
    return bytes(output)


def load_policy_tensors(
    observation: dict[str, Any],
    *,
    consumer: str,
    contract: dict[str, Any],
) -> PolicyTensorBytes:
    if consumer not in contract["shared_preprocessing"]["consumers"]:
        raise M04PreprocessingError(f"unknown M04 tensor consumer {consumer!r}")
    if observation.get("compatibility_sha256") != contract["identity"]["compatibility_sha256"]:
        raise M04PreprocessingError("M04 observation compatibility identity mismatch")
    if observation.get("schema_version") != "openttd-rl-v1-m04-observation-1":
        raise M04PreprocessingError("M04 observation schema version mismatch")
    if consumer != "m04-bridge-oracle" and "source_projection" in observation:
        raise M04PreprocessingError("oracle source projection cannot enter a policy consumer")

    structured = observation.get("structured")
    spatial = observation.get("spatial")
    if not isinstance(structured, dict) or not isinstance(spatial, dict):
        raise M04PreprocessingError("M04 tensor objects are missing")
    if structured.get("dtype") != "float32" or structured.get("shape") != [256] or structured.get("logical_order") != "feature":
        raise M04PreprocessingError("structured tensor metadata mismatch")
    if spatial.get("dtype") != "float32" or spatial.get("shape") != [32, 32, 32] or spatial.get("logical_order") != "channel-y-x":
        raise M04PreprocessingError("spatial tensor metadata mismatch")

    structured_bytes = _pack_float32(structured.get("data"), 256, (-1.0, 1.0), "structured")
    spatial_bytes = _pack_float32(spatial.get("data"), 32 * 32 * 32, (0.0, 1.0), "spatial")
    combined = structured_bytes + spatial_bytes
    return PolicyTensorBytes(
        consumer=consumer,
        structured=structured_bytes,
        spatial=spatial_bytes,
        combined=combined,
        sha256=hashlib.sha256(combined).hexdigest(),
    )


def load_contract(root: pathlib.Path) -> dict[str, Any]:
    return validate_m04_observation_contract.validate(
        root / "config/v1/m04-observation-contract.json",
        root / "docs/project/schema/v1-m04-observation-contract.schema.json",
    )
