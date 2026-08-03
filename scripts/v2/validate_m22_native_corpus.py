#!/usr/bin/env python3
"""Validate the frozen M22 native-qualified training/development corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

import build_m22_native_corpus as builder


CORPUS = pathlib.Path("config/v2/m22-native-corpus.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-native-corpus.schema.json")
CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")


class M22CorpusValidationError(ValueError):
    """The M22 corpus is malformed, stale, or not reproducible."""


@dataclass(frozen=True)
class M22CorpusSummary:
    entries: int
    training: int
    development: int
    programs: int
    native_gates: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22CorpusValidationError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M22CorpusValidationError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def validate(
    root: pathlib.Path,
    corpus_path: pathlib.Path | None = None,
    contract_path: pathlib.Path | None = None,
) -> M22CorpusSummary:
    root = root.resolve()
    corpus_path = corpus_path or root / CORPUS
    contract_path = contract_path or root / CONTRACT
    corpus = load(corpus_path)
    schema = load(root / SCHEMA)
    contract = load(contract_path)

    try:
        jsonschema.Draft202012Validator(schema).validate(corpus)
    except jsonschema.ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22CorpusValidationError(f"M22 corpus schema failed at {location}: {exc.message}") from exc

    require(corpus["schema_sha256"] == sha256(root / SCHEMA), "corpus schema SHA-256 mismatch")
    require(corpus_path.read_bytes() == canonical(corpus), "corpus JSON is not canonical")
    require(contract["identities"]["m22_native_corpus_sha256"] == sha256(corpus_path),
            "learning contract corpus identity drifted")
    environment = contract["environment_boundary"]
    require(environment["native_corpus"] == CORPUS.as_posix(), "learning contract corpus path drifted")
    require(environment["native_corpus_entries"] == 32, "learning contract corpus count drifted")
    require(environment["native_corpus_builder"] == "scripts/v2/build_m22_native_corpus.py",
            "learning contract corpus builder drifted")

    expected = builder.build(root)
    require(corpus == expected, "corpus does not exactly rebuild from accepted G15-G21 native evidence")
    summary = corpus["summary"]
    require(summary == {
        "entries": 32,
        "training": 16,
        "development": 16,
        "programs": 17,
        "native_gates": 7,
        "final_entries": 0,
        "all_native_success": True,
    }, "corpus summary drifted")
    require(all(item["native"]["success"] for item in corpus["entries"]),
            "corpus contains an unsuccessful native source")
    require(not any(item["split"] == "final" for item in corpus["entries"]),
            "corpus contains forbidden final data")
    return M22CorpusSummary(
        entries=summary["entries"],
        training=summary["training"],
        development=summary["development"],
        programs=summary["programs"],
        native_gates=summary["native_gates"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--corpus", type=pathlib.Path)
    parser.add_argument("--contract", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.corpus, args.contract)
        print(f"V2_M22_NATIVE_CORPUS=PASS entries={result.entries} training={result.training} "
              f"development={result.development} programs={result.programs} native_gates={result.native_gates}")
        return 0
    except (M22CorpusValidationError, builder.M22CorpusError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_NATIVE_CORPUS=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
