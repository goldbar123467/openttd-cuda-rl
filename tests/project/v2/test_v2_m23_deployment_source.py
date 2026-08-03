#!/usr/bin/env python3
"""Source and mutation tests for the M23 exporter, adapter, goldens, and ORT boundary."""

from __future__ import annotations

import copy
import math
import pathlib
import struct
import tempfile
import unittest

import m23_golden as golden
import validate_m23_release_contract as contract_validator


class M23DeploymentSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = contract_validator.load(cls.root / contract_validator.CONTRACT)
        cls.exporter = (cls.root / "scripts/v2/export_m23_models.py").read_text(encoding="utf-8")
        cls.adapter = (cls.root / "training/v2/src/m23_deployment.cpp").read_text(encoding="utf-8")
        cls.golden_cpp = (cls.root / "training/v2/src/m23_golden.cpp").read_text(encoding="utf-8")
        cls.onnx_cpp = (cls.root / "training/v2/src/m23_onnx.cpp").read_text(encoding="utf-8")
        cls.cmake = (cls.root / "training/v2/m23/CMakeLists.txt").read_text(encoding="utf-8")

    @staticmethod
    def encode_fixture(records: list[golden.GoldenRecord]) -> bytes:
        value = bytearray(golden.MAGIC)
        value.extend(struct.pack("<II", golden.VERSION, len(records)))
        for record in records:
            item = record.definition
            value.extend(struct.pack("<BBBBBBHII", item.architecture, item.case_class, item.sequence, item.step,
                                     item.mask_pattern, item.hidden_mode, 0, item.seed, item.batch))
            encoded_id = item.case_id.encode("ascii")
            value.extend(struct.pack("<H", len(encoded_id)))
            value.extend(encoded_id)
            value.extend(struct.pack(f"<{len(item.public_features)}f", *item.public_features))
            value.extend(bytes(item.program_mask))
            value.extend(struct.pack(f"<{len(item.initial_hidden)}f", *item.initial_hidden))
            value.extend(bytes(item.recurrent_reset))
            value.extend(struct.pack(f"<{len(record.hidden_input)}f", *record.hidden_input))
            value.extend(struct.pack(f"<{len(record.program_logits)}f", *record.program_logits))
            value.extend(struct.pack(f"<{len(record.program_value)}f", *record.program_value))
            value.extend(struct.pack(f"<{len(record.next_hidden)}f", *record.next_hidden))
            value.extend(struct.pack(f"<{len(record.greedy_program)}q", *record.greedy_program))
        return bytes(value)

    @classmethod
    def fixture_records(cls) -> list[golden.GoldenRecord]:
        result: list[golden.GoldenRecord] = []
        carried: list[list[list[float] | None]] = [[None, None], [None, None]]
        for architecture in range(2):
            for local in range(24):
                item = golden.generate_definition(architecture, local)
                hidden = item.initial_hidden
                if item.hidden_mode == 1:
                    hidden = carried[architecture][item.sequence] or []
                logits = [-1.0] * (item.batch * golden.PROGRAMS)
                actions = []
                for row in range(item.batch):
                    action = next(index for index, legal in enumerate(
                        item.program_mask[row * golden.PROGRAMS:(row + 1) * golden.PROGRAMS]
                    ) if legal)
                    logits[row * golden.PROGRAMS + action] = 1.0
                    actions.append(action)
                next_hidden = [0.0] * (item.batch * golden.HIDDEN)
                record = golden.GoldenRecord(item, list(hidden), logits, [0.0] * item.batch, next_hidden, actions)
                if item.case_class == 1:
                    carried[architecture][item.sequence] = next_hidden
                result.append(record)
        return result

    def decode_value(self, value: bytes) -> list[golden.GoldenRecord]:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "golden.bin"
            path.write_bytes(value)
            return golden.decode(path.resolve())

    def test_generator_has_exact_frozen_case_inventory(self) -> None:
        definitions = [golden.generate_definition(architecture, local) for architecture in range(2) for local in range(24)]
        self.assertEqual(len(definitions), 48)
        self.assertEqual(len({item.case_id for item in definitions}), 48)
        self.assertEqual(len({item.seed for item in definitions}), 48)
        self.assertEqual([sum(item.case_class == kind for item in definitions) for kind in range(3)], [16, 16, 16])
        self.assertEqual({item.batch for item in definitions}, {1, 8, 32})
        self.assertEqual({item.mask_pattern for item in definitions}, {0, 1, 2, 3})
        self.assertEqual({item.hidden_mode for item in definitions}, {0, 1, 2})
        self.assertEqual(definitions[0].seed, 1794838386)
        self.assertEqual(definitions[-1].seed, 482128934)

    def test_generator_matches_contract_domain_and_counts(self) -> None:
        specification = self.contract["equivalence"]
        self.assertEqual(specification["generation"]["domain"], golden.SEED_DOMAIN)
        self.assertEqual(specification["generation"]["seed_count"], 48)
        self.assertEqual(specification["cases_per_architecture"], golden.CASES_PER_ARCHITECTURE)
        self.assertEqual(specification["coverage"]["batch_sizes"], [1, 8, 32])

    def test_recurrent_sequences_have_exact_reset_and_carry_shape(self) -> None:
        for architecture in range(2):
            rows = [golden.generate_definition(architecture, local) for local in range(8, 16)]
            self.assertEqual([(item.sequence, item.step, item.batch) for item in rows],
                             [(0, 0, 8), (0, 1, 8), (0, 2, 8), (0, 3, 8),
                              (1, 0, 32), (1, 1, 32), (1, 2, 32), (1, 3, 32)])
            for item in rows:
                if item.step == 0:
                    self.assertTrue(all(item.recurrent_reset))
                elif item.step == 2:
                    self.assertEqual(item.recurrent_reset, [1 if row % 2 == 0 else 0 for row in range(item.batch)])
                else:
                    self.assertFalse(any(item.recurrent_reset))

    def test_python_binary_round_trip_fixture_passes(self) -> None:
        records = self.fixture_records()
        observed = self.decode_value(self.encode_fixture(records))
        self.assertEqual(observed, records)

    def test_binary_magic_truncation_and_trailing_bytes_fail(self) -> None:
        value = self.encode_fixture(self.fixture_records())
        mutated = bytearray(value); mutated[0] ^= 1
        with self.assertRaisesRegex(golden.GoldenError, "magic"):
            self.decode_value(bytes(mutated))
        with self.assertRaisesRegex(golden.GoldenError, "truncated"):
            self.decode_value(value[:-1])
        with self.assertRaisesRegex(golden.GoldenError, "trailing"):
            self.decode_value(value + b"x")

    def test_binary_seed_definition_mutation_fails(self) -> None:
        value = bytearray(self.encode_fixture(self.fixture_records()))
        # Header 16, six u8 plus reserved u16; seed begins at byte 24.
        value[24] ^= 1
        with self.assertRaisesRegex(golden.GoldenError, "definition drifted"):
            self.decode_value(bytes(value))

    def test_binary_nonfinite_output_fails(self) -> None:
        records = self.fixture_records()
        record = records[0]
        records[0] = golden.GoldenRecord(record.definition, record.hidden_input, [math.inf, *record.program_logits[1:]],
                                         record.program_value, record.next_hidden, record.greedy_program)
        with self.assertRaisesRegex(golden.GoldenError, "nonfinite"):
            self.decode_value(self.encode_fixture(records))

    def test_binary_illegal_action_fails(self) -> None:
        records = self.fixture_records()
        record = records[0]
        records[0] = golden.GoldenRecord(record.definition, record.hidden_input, record.program_logits,
                                         record.program_value, record.next_hidden, [16])
        with self.assertRaisesRegex(golden.GoldenError, "action illegal"):
            self.decode_value(self.encode_fixture(records))

    def test_binary_carried_hidden_mutation_fails(self) -> None:
        records = self.fixture_records()
        index = 9
        record = records[index]
        bad_hidden = list(record.hidden_input); bad_hidden[0] = 1.0
        records[index] = golden.GoldenRecord(record.definition, bad_hidden, record.program_logits,
                                             record.program_value, record.next_hidden, record.greedy_program)
        with self.assertRaisesRegex(golden.GoldenError, "hidden input drifted"):
            self.decode_value(self.encode_fixture(records))

    def test_exporter_loads_every_checkpoint_tensor_strictly(self) -> None:
        self.assertIn("torch.jit.load", self.exporter)
        self.assertIn("model.load_state_dict(state, strict=True)", self.exporter)
        self.assertIn("not result.missing_keys and not result.unexpected_keys", self.exporter)
        self.assertIn('"state_tensors": len(state)', self.exporter)

    def test_exporter_repeats_and_compares_canonical_onnx_bytes(self) -> None:
        self.assertIn("first = export_bytes(model, inputs)", self.exporter)
        self.assertIn("second = export_bytes(model, inputs)", self.exporter)
        self.assertIn("first == second", self.exporter)
        self.assertIn("SerializeToString(deterministic=True)", self.exporter)
        self.assertIn("opset_version=18", self.exporter)
        self.assertIn("dynamo=False", self.exporter)

    def test_exporter_signature_and_recurrent_reset_are_frozen(self) -> None:
        for name in ("public_features", "program_mask", "hidden_state", "recurrent_reset",
                     "program_logits", "program_value", "next_hidden"):
            self.assertIn(f'"{name}"', self.exporter)
        self.assertIn("torch.logical_not(recurrent_reset)", self.exporter)
        self.assertIn("self.memory(fused, reset_hidden)", self.exporter)

    def test_native_adapter_preserves_full_m22_projection(self) -> None:
        for token in ("kStructuredFeatures", "kGlobalSpatialSide", "kCompanyCapacity", "kGraphEdgeCapacity",
                      "kCandidateCapacity", "kM22DomainTokenCapacity", "kM22ProgramFeatures"):
            self.assertIn(token, self.adapter)
        self.assertIn("validate_m23_deployment_batch(batch)", self.adapter)
        self.assertIn("batch_size > kM23MaximumBatch", self.adapter)
        self.assertIn("!batch.program_mask.any(1).all()", self.adapter)

    def test_cpp_and_python_generators_share_domain_and_counts(self) -> None:
        self.assertIn(golden.SEED_DOMAIN, self.golden_cpp)
        self.assertIn("kCasesPerArchitecture = 24", self.golden_cpp)
        self.assertIn("records.size() == 2U * kCasesPerArchitecture", self.golden_cpp)
        self.assertIn("M23 golden file has trailing bytes", self.golden_cpp)

    def test_onnx_adapter_validates_exact_graph_signature(self) -> None:
        for name in ("public_features", "program_mask", "hidden_state", "recurrent_reset",
                     "program_logits", "program_value", "next_hidden"):
            self.assertIn(f'"{name}"', self.onnx_cpp)
        self.assertIn("ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL", self.onnx_cpp)
        self.assertIn("{-1, 32}", self.onnx_cpp)
        self.assertIn("{-1, 256}", self.onnx_cpp)
        self.assertIn("program mask contains an all-illegal row", self.onnx_cpp)

    def test_deployment_only_cmake_returns_before_libtorch_discovery(self) -> None:
        return_position = self.cmake.index("if(V2_M23_DEPLOYMENT_ONLY)")
        torch_position = self.cmake.index("find_package(Torch 2.13.0 EXACT CONFIG REQUIRED)")
        self.assertLess(return_position, torch_position)
        onnx_target = self.cmake[self.cmake.index("add_library(openttd_rl_v2_m23_onnx"):return_position]
        self.assertNotIn("Torch", onnx_target)
        self.assertIn("V2_ONNXRUNTIME_LIBRARY", onnx_target)

    def test_native_golden_and_onnx_evaluator_are_separate_targets(self) -> None:
        self.assertIn("add_executable(m23_native_golden", self.cmake)
        self.assertIn("add_executable(m23_onnx_evaluator", self.cmake)
        self.assertIn("openttd_rl_v2_m23_native", self.cmake)
        self.assertIn("openttd_rl_v2_m23_onnx", self.cmake)


if __name__ == "__main__":
    unittest.main()
