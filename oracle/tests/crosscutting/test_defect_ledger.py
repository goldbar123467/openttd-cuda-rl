#!/usr/bin/env python3
"""Independent contract tests for the append-only P0 defect ledger."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPOSITORY_ROOT / "tools" / "validate_manifest.py"
SCHEMA_PATH = REPOSITORY_ROOT / "oracle/manifests/schema/defect-divergence-ledger.schema.json"
LEDGER_PATH = REPOSITORY_ROOT / "evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json"

spec = importlib.util.spec_from_file_location("p0_validate_manifest", VALIDATOR_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load validator from {VALIDATOR_PATH}")
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


class DefectLedgerContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = validator.load_strict_json(LEDGER_PATH)

    def validate_copy(self, value: object) -> None:
        with tempfile.TemporaryDirectory(prefix="p0-ledger-test-") as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            validator.validate(SCHEMA_PATH, path)

    @staticmethod
    def sample_entry() -> dict[str, object]:
        zero_sha = "0" * 64
        return {
            "id": "DEF-P0-0001",
            "kind": "DEFECT",
            "discovery_date_diagnostic": "2026-07-30",
            "discovering_test_id": "TEST-LEDGER-001",
            "source_identity": {
                "outer_commit": "0" * 40,
                "submodule_commit": "29f808ef0022064e6d9a83c8476d1e0f4686af86",
            },
            "build_identity": {
                "profile": "focused-development",
                "executable": {"sha256": zero_sha, "size_bytes": 1},
            },
            "fixture_identity": {"sha256": zero_sha, "size_bytes": 1},
            "command_input_identity": {"sha256": zero_sha, "size_bytes": 1},
            "earliest_boundary": {
                "record_sequence": 0,
                "tick": 0,
                "boundary_kind": "tooling",
            },
            "location": {"subsystem": "ledger-contract-test"},
            "expected_value": "expected",
            "observed_value": "observed",
            "minimized_reproducer": {
                "relative_path": "evidence/p0/regressions/def-p0-0001.bin",
                "sha256": zero_sha,
                "size_bytes": 1,
                "rerun_argv": ["./oracle/runner/p0_gate.sh", "--profile", "local-release"],
            },
            "impact": "test fixture",
            "root_cause": "undetermined",
            "owner": "P0 harness",
            "fix_revision": None,
            "regression_test": None,
            "closure_evidence": [],
            "status": "OPEN",
        }

    def test_empty_canonical_ledger_validates(self) -> None:
        validator.validate(SCHEMA_PATH, LEDGER_PATH)

    def test_open_counts_are_recomputed(self) -> None:
        value = copy.deepcopy(self.ledger)
        value["entries"] = [self.sample_entry()]
        with self.assertRaisesRegex(ValueError, "open counts disagree"):
            self.validate_copy(value)
        value["open_counts"] = {
            "defects": 1,
            "divergences": 0,
            "total_nonclosed": 1,
        }
        self.validate_copy(value)

    def test_duplicate_ids_fail(self) -> None:
        value = copy.deepcopy(self.ledger)
        entry = self.sample_entry()
        value["entries"] = [entry, copy.deepcopy(entry)]
        value["open_counts"] = {
            "defects": 2,
            "divergences": 0,
            "total_nonclosed": 2,
        }
        with self.assertRaisesRegex(ValueError, "IDs must be unique"):
            self.validate_copy(value)

    def test_kind_and_id_prefix_must_agree(self) -> None:
        value = copy.deepcopy(self.ledger)
        entry = self.sample_entry()
        entry["kind"] = "DIVERGENCE"
        value["entries"] = [entry]
        value["open_counts"] = {
            "defects": 0,
            "divergences": 1,
            "total_nonclosed": 1,
        }
        with self.assertRaises(ValueError):
            self.validate_copy(value)

    def test_closed_entry_requires_fix_test_and_evidence(self) -> None:
        value = copy.deepcopy(self.ledger)
        entry = self.sample_entry()
        entry["status"] = "CLOSED"
        value["entries"] = [entry]
        with self.assertRaises(ValueError):
            self.validate_copy(value)


if __name__ == "__main__":
    unittest.main()
