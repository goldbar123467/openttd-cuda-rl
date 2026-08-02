#!/usr/bin/env python3
"""Bounded, content-addressed, corruption-detecting M06 trajectory bundles."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pathlib
import shutil
import struct
import uuid
from typing import Any

from m06_reward_reference import float64_bits, record_sha256
from validate_m06_reward_contract import canonical_bytes


TRAJECTORY_SCHEMA_VERSION = "openttd-rl-v1-m06-trajectory-1"
REWARD_COMPATIBILITY_SHA256 = "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e"
OBSERVATION_COMPATIBILITY_SHA256 = "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb"
ACTION_COMPATIBILITY_SHA256 = "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536"
BRIDGE_COMPATIBILITY_SHA256 = "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6"
OBSERVATION_BYTES = 132_096
MAX_TRANSITIONS = 128
MAX_OBSERVATION_BYTES = 17_040_384
MAX_METADATA_BYTES = 8_388_608
MAX_TOTAL_BYTES = 25_428_992


class M06TrajectoryError(ValueError):
    """A trajectory is malformed, over bounds, incomplete, or corrupt."""


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M06TrajectoryError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _finite_number(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise M06TrajectoryError(f"{name} must be a finite JSON number")
    return float(value)


def _uint(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > (1 << 64) - 1:
        raise M06TrajectoryError(f"{name} must fit uint64")
    return value


def _exact_keys(value: Any, expected: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise M06TrajectoryError(f"{name} fields differ: expected={sorted(expected)} actual={actual}")


def _load_canonical(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M06TrajectoryError(f"{path}: UTF-8 BOM is forbidden")
    if not raw.endswith(b"\n"):
        raise M06TrajectoryError(f"{path}: canonical JSON must end in one newline")
    try:
        value = json.loads(
            raw[:-1],
            object_pairs_hook=_strict_object_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(M06TrajectoryError(f"invalid JSON constant {token}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M06TrajectoryError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_bytes(value) + b"\n" != raw:
        raise M06TrajectoryError(f"{path}: JSON is not canonical")
    return value


def encode_observation(observation: dict[str, Any]) -> bytes:
    """Encode the exact M04 structured-then-spatial canonical float32 blob."""
    _exact_keys(
        observation,
        {"compatibility_sha256", "schema_version", "spatial", "structured"},
        "observation",
    )
    if observation["compatibility_sha256"] != OBSERVATION_COMPATIBILITY_SHA256:
        raise M06TrajectoryError("M04 observation compatibility identity mismatch")
    expected = (("structured", [256], 256), ("spatial", [32, 32, 32], 32_768))
    output = bytearray()
    for name, shape, count in expected:
        tensor = observation[name]
        _exact_keys(tensor, {"data", "dtype", "logical_order", "shape"}, f"observation.{name}")
        if tensor["dtype"] != "float32" or tensor["shape"] != shape or not isinstance(tensor["data"], list) or len(tensor["data"]) != count:
            raise M06TrajectoryError(f"observation.{name} tensor metadata or length drifted")
        values = [_finite_number(value, f"observation.{name}[{index}]") for index, value in enumerate(tensor["data"])]
        try:
            output.extend(struct.pack(f"<{count}f", *values))
        except (OverflowError, struct.error) as exc:
            raise M06TrajectoryError(f"observation.{name} cannot be encoded as float32: {exc}") from exc
    if len(output) != OBSERVATION_BYTES:
        raise M06TrajectoryError("M04 observation byte length drifted")
    return bytes(output)


def observation_sha256(observation: dict[str, Any]) -> tuple[str, bytes]:
    blob = encode_observation(observation)
    return hashlib.sha256(blob).hexdigest(), blob


def _validate_float_guard(container: dict[str, Any], field: str, bits_field: str, name: str) -> None:
    value = _finite_number(container.get(field), f"{name}.{field}")
    if container.get(bits_field) != float64_bits(value):
        raise M06TrajectoryError(f"{name}.{bits_field} does not guard the finite float64 value")


def validate_record(record: dict[str, Any]) -> None:
    _exact_keys(
        record,
        {
            "action",
            "action_mask",
            "boundary",
            "identities",
            "ids",
            "integrity_sha256",
            "next_observation_sha256",
            "next_value",
            "observation_sha256",
            "reward",
            "scenario",
            "schema_version",
            "termination",
        },
        "trajectory record",
    )
    if record["schema_version"] != TRAJECTORY_SCHEMA_VERSION or record["integrity_sha256"] != record_sha256(record):
        raise M06TrajectoryError("trajectory record schema or integrity mismatch")
    identities = record["identities"]
    _exact_keys(identities, {"action", "bridge", "model_checkpoint", "observation", "reward"}, "identities")
    expected_identities = {
        "action": ACTION_COMPATIBILITY_SHA256,
        "bridge": BRIDGE_COMPATIBILITY_SHA256,
        "observation": OBSERVATION_COMPATIBILITY_SHA256,
        "reward": REWARD_COMPATIBILITY_SHA256,
    }
    for name, expected in expected_identities.items():
        if identities[name] != expected:
            raise M06TrajectoryError(f"{name} compatibility identity mismatch")
    if identities["model_checkpoint"] is not None and (not isinstance(identities["model_checkpoint"], str) or len(identities["model_checkpoint"]) != 64):
        raise M06TrajectoryError("model checkpoint identity must be null or SHA-256")
    ids = record["ids"]
    _exact_keys(ids, {"environment_id", "episode_id", "request_id", "run_id", "transition_ordinal", "worker_id"}, "ids")
    if not isinstance(ids["run_id"], str) or not ids["run_id"]:
        raise M06TrajectoryError("run_id must be a nonempty string")
    for name in {"environment_id", "episode_id", "request_id", "transition_ordinal", "worker_id"}:
        _uint(ids[name], f"ids.{name}")
    scenario = record["scenario"]
    _exact_keys(scenario, {"seed_ledger_sha256", "template_id", "template_sha256"}, "scenario")
    for name in ("seed_ledger_sha256", "template_sha256"):
        if not isinstance(scenario[name], str) or len(scenario[name]) != 64:
            raise M06TrajectoryError(f"scenario.{name} must be SHA-256")
    boundary = record["boundary"]
    _exact_keys(boundary, {"advanced_ticks", "post_tick", "post_token", "pre_tick", "pre_token"}, "boundary")
    pre_tick = _uint(boundary["pre_tick"], "boundary.pre_tick")
    post_tick = _uint(boundary["post_tick"], "boundary.post_tick")
    advanced = _uint(boundary["advanced_ticks"], "boundary.advanced_ticks")
    if advanced > 128 or post_tick - pre_tick != advanced:
        raise M06TrajectoryError("boundary tick delta does not equal advanced_ticks in 0..128")
    for name in ("pre_token", "post_token"):
        if not isinstance(boundary[name], str) or not boundary[name]:
            raise M06TrajectoryError(f"boundary.{name} must be nonempty")
    for name in ("observation_sha256", "next_observation_sha256"):
        if not isinstance(record[name], str) or len(record[name]) != 64:
            raise M06TrajectoryError(f"{name} must be SHA-256")
    mask = record["action_mask"]
    _exact_keys(mask, {"dtype", "legal", "mask_token"}, "action_mask")
    if mask["dtype"] != "uint8" or not isinstance(mask["legal"], list) or len(mask["legal"]) != 41 or any(value not in (0, 1) or isinstance(value, bool) for value in mask["legal"]):
        raise M06TrajectoryError("action mask is not the exact 41-byte uint8 mask")
    if not isinstance(mask["mask_token"], str) or not mask["mask_token"]:
        raise M06TrajectoryError("action mask token is empty")
    action = record["action"]
    _exact_keys(action, {"index", "log_probability", "log_probability_float64_bits", "outcome", "parameters", "selection_mode", "value", "value_float64_bits"}, "action")
    index = _uint(action["index"], "action.index")
    if index >= 41 or mask["legal"][index] != 1:
        raise M06TrajectoryError("recorded action is outside or masked by the recorded mask")
    if action["selection_mode"] not in {"SAMPLED", "GREEDY", "SCRIPTED", "RANDOM_LEGAL"}:
        raise M06TrajectoryError("unknown action selection mode")
    if not isinstance(action["parameters"], dict) or not isinstance(action["outcome"], dict):
        raise M06TrajectoryError("action parameters/outcome must be objects")
    _validate_float_guard(action, "log_probability", "log_probability_float64_bits", "action")
    _validate_float_guard(action, "value", "value_float64_bits", "action")
    reward = record["reward"]
    if not isinstance(reward, dict) or reward.get("compatibility_sha256") != REWARD_COMPATIBILITY_SHA256:
        raise M06TrajectoryError("reward object compatibility identity mismatch")
    _validate_float_guard(reward, "scalar", "scalar_float64_bits", "reward")
    components = reward.get("components")
    if not isinstance(components, list) or [item.get("component_id") for item in components] != [f"RC-{index:03d}" for index in range(1, 9)]:
        raise M06TrajectoryError("reward component inventory drifted")
    for index, component in enumerate(components):
        _validate_float_guard(component, "weighted", "weighted_float64_bits", f"reward.components[{index}]")
    termination = record["termination"]
    _exact_keys(termination, {"bootstrap", "kind", "reason", "schema_version", "terminal", "trainable", "truncated"}, "termination")
    for name in ("bootstrap", "terminal", "trainable", "truncated"):
        if not isinstance(termination[name], bool):
            raise M06TrajectoryError(f"termination.{name} must be boolean")
    next_value = record["next_value"]
    if termination["bootstrap"]:
        _exact_keys(next_value, {"float64_bits", "value"}, "next_value")
        _validate_float_guard(next_value, "value", "float64_bits", "next_value")
    elif next_value is not None:
        raise M06TrajectoryError("non-bootstrap transition must have null next_value")


def seal_record(record: dict[str, Any]) -> dict[str, Any]:
    if "integrity_sha256" in record:
        raise M06TrajectoryError("unsealed record must not already contain integrity_sha256")
    sealed = copy.deepcopy(record)
    sealed["integrity_sha256"] = record_sha256(sealed)
    validate_record(sealed)
    return sealed


class TrajectoryBundle:
    """In-memory bounded builder that writes one atomic immutable bundle directory."""

    def __init__(self, provenance: dict[str, Any]) -> None:
        if not isinstance(provenance, dict) or not provenance:
            raise M06TrajectoryError("bundle provenance must be a nonempty object")
        canonical_bytes(provenance)
        self.provenance = copy.deepcopy(provenance)
        self.records: list[dict[str, Any]] = []
        self.blobs: dict[str, bytes] = {}

    @classmethod
    def resume(cls, source: pathlib.Path) -> "TrajectoryBundle":
        """Resume a validated immutable bundle into a new builder/output generation."""
        manifest = load_bundle(source)
        builder = cls(manifest["provenance"])
        builder.records = copy.deepcopy(manifest["records"])
        for digest, metadata in manifest["observation_blobs"].items():
            builder.blobs[digest] = (source.resolve() / metadata["path"]).read_bytes()
        return builder

    def add(self, record: dict[str, Any], observation: dict[str, Any], next_observation: dict[str, Any]) -> dict[str, Any]:
        if len(self.records) >= MAX_TRANSITIONS:
            raise M06TrajectoryError("trajectory exceeds the 128-transition segment bound")
        observation_id, observation_blob = observation_sha256(observation)
        next_id, next_blob = observation_sha256(next_observation)
        candidate = copy.deepcopy(record)
        candidate["observation_sha256"] = observation_id
        candidate["next_observation_sha256"] = next_id
        sealed = seal_record(candidate)
        key = (
            sealed["ids"]["worker_id"],
            sealed["ids"]["episode_id"],
            sealed["ids"]["transition_ordinal"],
        )
        if self.records:
            prior = self.records[-1]
            prior_key = (prior["ids"]["worker_id"], prior["ids"]["episode_id"], prior["ids"]["transition_ordinal"])
            if key <= prior_key:
                raise M06TrajectoryError("records are not in deterministic worker/episode/transition order")
            if key[:2] == prior_key[:2] and sealed["observation_sha256"] != prior["next_observation_sha256"]:
                raise M06TrajectoryError("adjacent transition observation boundary is discontinuous")
        self.records.append(sealed)
        self.blobs.setdefault(observation_id, observation_blob)
        self.blobs.setdefault(next_id, next_blob)
        if len(self.blobs) * OBSERVATION_BYTES > MAX_OBSERVATION_BYTES:
            raise M06TrajectoryError("trajectory exceeds the observation-byte bound")
        return copy.deepcopy(sealed)

    def manifest(self) -> dict[str, Any]:
        blobs = {
            digest: {
                "byte_length": len(blob),
                "dtype": "little-endian-float32",
                "path": f"blobs/{digest}.bin",
            }
            for digest, blob in sorted(self.blobs.items())
        }
        manifest = {
            "bundle_sha256": "",
            "observation_blobs": blobs,
            "provenance": copy.deepcopy(self.provenance),
            "record_count": len(self.records),
            "records": copy.deepcopy(self.records),
            "reward_compatibility_sha256": REWARD_COMPATIBILITY_SHA256,
            "schema_version": TRAJECTORY_SCHEMA_VERSION,
            "status": "COMPLETE",
        }
        digest_input = copy.deepcopy(manifest)
        digest_input.pop("bundle_sha256")
        manifest["bundle_sha256"] = hashlib.sha256(canonical_bytes(digest_input)).hexdigest()
        metadata_bytes = len(canonical_bytes(manifest)) + 1
        observation_bytes = sum(len(blob) for blob in self.blobs.values())
        if metadata_bytes > MAX_METADATA_BYTES or metadata_bytes + observation_bytes > MAX_TOTAL_BYTES:
            raise M06TrajectoryError("trajectory exceeds metadata or total byte bound")
        return manifest

    def write(self, destination: pathlib.Path) -> dict[str, Any]:
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite trajectory bundle {destination}")
        temporary = destination.parent / f".{destination.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
        temporary.mkdir(mode=0o700)
        try:
            blobs_dir = temporary / "blobs"
            blobs_dir.mkdir()
            for digest, blob in sorted(self.blobs.items()):
                _write_new_fsync(blobs_dir / f"{digest}.bin", blob)
            _fsync_directory(blobs_dir)
            manifest = self.manifest()
            _write_new_fsync(temporary / "manifest.json", canonical_bytes(manifest) + b"\n")
            _fsync_directory(temporary)
            if destination.exists():
                raise FileExistsError(f"refusing to overwrite trajectory bundle {destination}")
            os.rename(temporary, destination)
            _fsync_directory(destination.parent)
            return manifest
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise


def _write_new_fsync(path: pathlib.Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("trajectory write made no progress")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def load_bundle(path: pathlib.Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_dir() or path.is_symlink():
        raise M06TrajectoryError("trajectory bundle must be a real directory")
    manifest = _load_canonical(path / "manifest.json")
    _exact_keys(
        manifest,
        {"bundle_sha256", "observation_blobs", "provenance", "record_count", "records", "reward_compatibility_sha256", "schema_version", "status"},
        "bundle manifest",
    )
    if manifest["schema_version"] != TRAJECTORY_SCHEMA_VERSION or manifest["reward_compatibility_sha256"] != REWARD_COMPATIBILITY_SHA256 or manifest["status"] != "COMPLETE":
        raise M06TrajectoryError("bundle schema, reward identity, or completion status mismatch")
    digest_input = copy.deepcopy(manifest)
    claimed = digest_input.pop("bundle_sha256")
    if claimed != hashlib.sha256(canonical_bytes(digest_input)).hexdigest():
        raise M06TrajectoryError("bundle integrity mismatch")
    records = manifest["records"]
    if not isinstance(records, list) or len(records) != manifest["record_count"] or len(records) > MAX_TRANSITIONS:
        raise M06TrajectoryError("bundle record count violates its manifest or bound")
    prior_key: tuple[int, int, int] | None = None
    referenced: set[str] = set()
    for record in records:
        validate_record(record)
        key = (record["ids"]["worker_id"], record["ids"]["episode_id"], record["ids"]["transition_ordinal"])
        if prior_key is not None and key <= prior_key:
            raise M06TrajectoryError("bundle record order is not deterministic")
        prior_key = key
        referenced.update((record["observation_sha256"], record["next_observation_sha256"]))
    blobs = manifest["observation_blobs"]
    if not isinstance(blobs, dict) or referenced != set(blobs):
        raise M06TrajectoryError("bundle observation references and blob inventory differ")
    observation_bytes = 0
    for digest, metadata in blobs.items():
        if len(digest) != 64 or metadata != {"byte_length": OBSERVATION_BYTES, "dtype": "little-endian-float32", "path": f"blobs/{digest}.bin"}:
            raise M06TrajectoryError("observation blob metadata drifted")
        blob_path = path / metadata["path"]
        if not blob_path.is_file() or blob_path.is_symlink():
            raise M06TrajectoryError("observation blob is missing or not a real file")
        blob = blob_path.read_bytes()
        if len(blob) != OBSERVATION_BYTES or hashlib.sha256(blob).hexdigest() != digest:
            raise M06TrajectoryError("observation blob length or SHA-256 mismatch")
        observation_bytes += len(blob)
    metadata_bytes = len(canonical_bytes(manifest)) + 1
    if observation_bytes > MAX_OBSERVATION_BYTES or metadata_bytes > MAX_METADATA_BYTES or observation_bytes + metadata_bytes > MAX_TOTAL_BYTES:
        raise M06TrajectoryError("loaded bundle violates rollout byte bounds")
    return manifest


__all__ = [
    "M06TrajectoryError",
    "TrajectoryBundle",
    "encode_observation",
    "load_bundle",
    "observation_sha256",
    "seal_record",
    "validate_record",
]
