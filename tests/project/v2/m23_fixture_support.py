#!/usr/bin/env python3
"""Immutable cached golden data and isolated package/report fixtures for M23."""

from __future__ import annotations

import dataclasses
import functools
import os
import pathlib
import shutil
import struct
from collections.abc import Mapping, Sequence
from typing import Any

import m23_golden
import m23_ingame
import m23_package
import validate_m23_release_contract as contract_validator


_MODEL_KEYS = frozenset({"monolithic_sha256", "specialist_sha256"})
_SHA256 = frozenset("0123456789abcdef")


def _immutable_definition(
    definition: m23_golden.GoldenDefinition,
) -> m23_golden.GoldenDefinition:
    return dataclasses.replace(
        definition,
        public_features=tuple(definition.public_features),  # type: ignore[arg-type]
        program_mask=tuple(definition.program_mask),  # type: ignore[arg-type]
        initial_hidden=tuple(definition.initial_hidden),  # type: ignore[arg-type]
        recurrent_reset=tuple(definition.recurrent_reset),  # type: ignore[arg-type]
    )


@functools.cache
def make_golden_records(index: int) -> tuple[m23_golden.GoldenRecord, ...]:
    """Return the cached immutable 24-case golden fixture for one architecture."""

    if isinstance(index, bool) or index not in (0, 1):
        raise ValueError(f"M23 fixture architecture index is invalid: {index!r}")
    records: list[m23_golden.GoldenRecord] = []
    carried: list[tuple[float, ...] | None] = [None, None]
    for local in range(m23_golden.CASES_PER_ARCHITECTURE):
        definition = _immutable_definition(m23_golden.generate_definition(index, local))
        hidden = definition.initial_hidden
        if definition.hidden_mode == 1:
            prior = carried[definition.sequence]
            if prior is None:
                raise ValueError("M23 fixture carried hidden has no predecessor")
            hidden = prior  # type: ignore[assignment]
        logits = [-1.0] * (definition.batch * m23_golden.PROGRAMS)
        actions: list[int] = []
        for row in range(definition.batch):
            offset = row * m23_golden.PROGRAMS
            action = next(
                candidate
                for candidate, legal in enumerate(
                    definition.program_mask[offset:offset + m23_golden.PROGRAMS]
                )
                if legal
            )
            logits[offset + action] = 1.0
            actions.append(action)
        next_hidden = tuple(0.0 for _ in range(definition.batch * m23_golden.HIDDEN))
        record = m23_golden.GoldenRecord(
            definition,
            tuple(hidden),  # type: ignore[arg-type]
            tuple(logits),  # type: ignore[arg-type]
            tuple(0.0 for _ in range(definition.batch)),  # type: ignore[arg-type]
            next_hidden,  # type: ignore[arg-type]
            tuple(actions),  # type: ignore[arg-type]
        )
        if definition.case_class == 1:
            carried[definition.sequence] = next_hidden
        records.append(record)
    return tuple(records)


@functools.cache
def make_golden_binary() -> bytes:
    """Return the cached exact 48-case/580-row binary golden fixture."""

    records = (*make_golden_records(0), *make_golden_records(1))
    output = bytearray(m23_golden.MAGIC)
    output.extend(struct.pack("<II", m23_golden.VERSION, len(records)))
    for record in records:
        definition = record.definition
        output.extend(struct.pack(
            "<BBBBBBHII",
            definition.architecture,
            definition.case_class,
            definition.sequence,
            definition.step,
            definition.mask_pattern,
            definition.hidden_mode,
            0,
            definition.seed,
            definition.batch,
        ))
        case_id = definition.case_id.encode("ascii")
        output.extend(struct.pack("<H", len(case_id)))
        output.extend(case_id)
        output.extend(struct.pack(
            f"<{len(definition.public_features)}f", *definition.public_features,
        ))
        output.extend(bytes(definition.program_mask))
        output.extend(struct.pack(
            f"<{len(definition.initial_hidden)}f", *definition.initial_hidden,
        ))
        output.extend(bytes(definition.recurrent_reset))
        for values in (
            record.hidden_input,
            record.program_logits,
            record.program_value,
            record.next_hidden,
        ):
            output.extend(struct.pack(f"<{len(values)}f", *values))
        output.extend(struct.pack(
            f"<{len(record.greedy_program)}q", *record.greedy_program,
        ))
    return bytes(output)


def _plain_directory(path: pathlib.Path, label: str) -> pathlib.Path:
    candidate = pathlib.Path(path)
    if (
        not candidate.is_absolute()
        or not candidate.is_dir()
        or candidate.is_symlink()
        or candidate.resolve(strict=True) != candidate
    ):
        raise ValueError(f"{label} must be a canonical absolute nonsymlink directory")
    return candidate


def _validate_records(
    records: Sequence[m23_golden.GoldenRecord], architecture: str,
) -> tuple[m23_golden.GoldenRecord, ...]:
    if not isinstance(records, tuple) or len(records) != m23_golden.CASES_PER_ARCHITECTURE:
        raise ValueError("M23 package fixture records must be one immutable architecture")
    architecture_index = contract_validator.ARCHITECTURES.index(architecture)
    for record in records:
        sequences = (
            record.definition.public_features,
            record.definition.program_mask,
            record.definition.initial_hidden,
            record.definition.recurrent_reset,
            record.hidden_input,
            record.program_logits,
            record.program_value,
            record.next_hidden,
            record.greedy_program,
        )
        if record.definition.architecture != architecture_index or not all(
            isinstance(value, tuple) for value in sequences
        ):
            raise ValueError("M23 package fixture records are mutable or misbound")
    return records


def make_package(
    parent: pathlib.Path,
    root: pathlib.Path,
    contract: dict[str, Any],
    architecture: str,
    records: Sequence[m23_golden.GoldenRecord],
) -> pathlib.Path:
    """Build one new deterministic package base from immutable fixture records."""

    destination_parent = _plain_directory(parent, "M23 fixture package parent")
    repository_root = _plain_directory(root, "M23 fixture repository root")
    if architecture not in contract_validator.ARCHITECTURES:
        raise ValueError(f"M23 fixture architecture is invalid: {architecture!r}")
    immutable_records = _validate_records(records, architecture)
    checkpoints, deployments = m23_package.architecture_maps(contract)
    checkpoint = checkpoints[architecture]
    deployment = deployments[architecture]
    stage = destination_parent / f".{architecture}.stage"
    if stage.exists() or stage.is_symlink():
        raise FileExistsError(f"M23 fixture package stage already exists: {stage}")
    stage.mkdir(mode=0o700)
    try:
        m23_package.write_new(stage / "model.onnx", b"fixture-onnx")
        m23_golden.write_jsonl(
            (stage / "golden.jsonl").resolve(),
            immutable_records,  # type: ignore[arg-type]
            architecture,
        )
        model_sha256 = m23_package.sha256_file(stage / "model.onnx")
        evaluation = {
            "architecture_id": architecture,
            "case_count": 24,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "compared_runtimes": [
                "native-libtorch-cpu", "standalone-onnxruntime-cpu",
            ],
            "equivalence_report_sha256": "4" * 64,
            "failure_counts": {"action": 0, "float": 0, "total": 0},
            "golden_binary_sha256": "5" * 64,
            "maximum_error": {"hidden_absolute": 0.0},
            "model_sha256": model_sha256,
            "result_runtime": "onnxruntime-1.28.0-cpu",
            "results": [
                {
                    "action_exact": True,
                    "case_id": record.definition.case_id,
                    "passed": True,
                }
                for record in immutable_records
            ],
            "row_count": sum(record.definition.batch for record in immutable_records),
            "schema_version": "openttd-rl-v2-m23-package-evaluation-1",
            "status": "PASS",
            "tolerance": {"absolute": 0.00005, "relative": 0.00005},
        }
        m23_package.write_new(
            stage / "evaluation.json",
            m23_package.canonical_json(evaluation, newline=True),
        )
        m23_package.write_new(
            stage / "INSTALL.md",
            m23_package.install_text(contract["deployment_packages"]["format"]),
        )
        m23_package.write_new(
            stage / "MODEL_CARD.md",
            m23_package.model_card_text(
                architecture, deployment["role"], checkpoint["checkpoint_id"],
            ),
        )
        files = {
            name: m23_package.sha256_file(stage / name)
            for name in m23_package.PAYLOAD_FILES
        }
        package_graph = contract["deployment_packages"]["graph"]
        graph = {
            "inputs": package_graph["inputs"],
            "outputs": package_graph["outputs"],
            "training_nodes": False,
        }
        provenance = {
            "contract_sha256": m23_package.sha256_file(
                repository_root / contract_validator.CONTRACT
            ),
            "equivalence_report_sha256": "4" * 64,
            "export_report_sha256": "6" * 64,
            "golden_binary_sha256": "5" * 64,
            "model_sha256": model_sha256,
        }
        manifest = m23_package.package_manifest(
            contract, deployment, checkpoint, graph, files, provenance,
        )
        package_id = m23_package.sha256_bytes(m23_package.canonical_json(manifest))
        manifest["package_id"] = package_id
        m23_package.write_new(
            stage / "manifest.json", m23_package.canonical_json(manifest),
        )
        final = destination_parent / package_id
        if final.exists() or final.is_symlink():
            raise FileExistsError(f"M23 fixture package target already exists: {final}")
        stage.rename(final)
        return final
    except Exception:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise


def snapshot_tree(root: pathlib.Path) -> tuple[tuple[str, str], ...]:
    """Return sorted file SHA-256 pairs after rejecting every tree symlink."""

    source = _plain_directory(root, "M23 fixture snapshot root")
    result: list[tuple[str, str]] = []
    for current, directories, filenames in os.walk(source, followlinks=False):
        current_path = pathlib.Path(current)
        directories.sort()
        filenames.sort()
        for name in directories:
            entry = current_path / name
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError(f"M23 fixture snapshot contains invalid directory: {entry}")
        for name in filenames:
            entry = current_path / name
            if entry.is_symlink() or not entry.is_file():
                raise ValueError(f"M23 fixture snapshot contains invalid file: {entry}")
            result.append((entry.relative_to(source).as_posix(), m23_package.sha256_file(entry)))
    return tuple(sorted(result))


def clone_package(base: pathlib.Path, parent: pathlib.Path) -> pathlib.Path:
    """Copy a package base to a new unlinked target below an existing parent."""

    source = _plain_directory(base, "M23 fixture package base")
    destination_parent = _plain_directory(parent, "M23 fixture clone parent")
    if destination_parent == source or destination_parent.is_relative_to(source):
        raise ValueError("M23 fixture clone parent aliases the package base")
    target = destination_parent / source.name
    if target == source or target.exists() or target.is_symlink():
        raise FileExistsError(f"M23 fixture clone target must be new: {target}")
    before = snapshot_tree(source)
    shutil.copytree(source, target)
    try:
        if snapshot_tree(target) != before:
            raise ValueError("M23 fixture clone content drifted")
        for relative, _digest in before:
            source_stat = os.stat(source / relative, follow_symlinks=False)
            target_stat = os.stat(target / relative, follow_symlinks=False)
            if (source_stat.st_dev, source_stat.st_ino) == (
                target_stat.st_dev, target_stat.st_ino
            ):
                raise ValueError(f"M23 fixture clone shares an inode: {relative}")
        return target
    except Exception:
        shutil.rmtree(target)
        raise


def make_equivalence_report(
    records: Sequence[m23_golden.GoldenRecord],
    *,
    golden_sha256: str,
    runtime: str,
    model_shas: Mapping[str, str],
) -> dict[str, Any]:
    """Return a fresh semantic-equivalence report around immutable records."""

    if len(records) != 48 or sum(record.definition.batch for record in records) != 580:
        raise ValueError("M23 equivalence fixture must contain exact 48-case/580-row records")
    if len(golden_sha256) != 64 or not set(golden_sha256) <= _SHA256:
        raise ValueError("M23 equivalence fixture golden SHA-256 is invalid")
    copied_model_shas = dict(model_shas)
    if set(copied_model_shas) != _MODEL_KEYS or any(
        not isinstance(value, str)
        or len(value) != 64
        or not set(value) <= _SHA256
        for value in copied_model_shas.values()
    ):
        raise ValueError("M23 equivalence fixture model SHA-256 inventory is invalid")
    return {
        "cases": [
            {
                "action_exact": True,
                "batch": record.definition.batch,
                "case_id": record.definition.case_id,
                "hidden_absolute": 0.0,
                "hidden_input_absolute": 0.0,
                "hidden_relative": 0.0,
                "logits_absolute": 0.0,
                "logits_relative": 0.0,
                "passed": True,
                "value_absolute": 0.0,
                "value_relative": 0.0,
            }
            for record in records
        ],
        "failure_counts": {"action": 0, "float": 0, "total": 0},
        "golden": {"sha256": golden_sha256},
        "maximum_error": {key: 0.0 for key in m23_ingame.ERROR_KEYS},
        "models": copied_model_shas,
        "runtime": runtime,
        "schema_version": m23_ingame.REPORT_SCHEMA,
        "status": "PASS",
        "tolerance": {"absolute": 0.00005, "relative": 0.00005},
    }
