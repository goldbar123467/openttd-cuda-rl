import json
import pathlib
import unittest

import jsonschema


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "docs/project/schema/v2-m22-evaluator-report.schema.json"
HEADER = ROOT / "training/v2/include/openttd_rl/v2/m22_evaluation.h"
SOURCE = ROOT / "training/v2/src/m22_evaluation.cpp"
MAIN = ROOT / "training/v2/src/m22_evaluator_main.cpp"
CMAKE = ROOT / "training/v2/m22/CMakeLists.txt"


class M22EvaluatorTests(unittest.TestCase):
    def test_evaluator_schema_is_closed_and_forbids_final_labels(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("seed", schema["properties"]["public_state"]["properties"])
        self.assertNotIn("required_program", schema["properties"]["public_state"]["properties"])

    def test_optimizer_free_link_boundary_is_structural(self) -> None:
        header = HEADER.read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8")
        cmake = CMAKE.read_text(encoding="utf-8")
        evaluation_block = cmake.split("add_library(\n  openttd_rl_v2_m22_evaluation", 1)[1].split(")", 1)[0]
        self.assertNotIn("M22Trainer", header)
        self.assertNotIn("torch::optim", source)
        self.assertNotIn("m22_trainer.cpp", evaluation_block)
        self.assertNotIn("m22_checkpoint.cpp", evaluation_block)
        self.assertNotIn("m22_ppo.cpp", evaluation_block)
        self.assertNotIn("m22_campaign.cpp", evaluation_block)
        self.assertNotIn('sha256_file(checkpoint_path / "optimizer.pt")', source)
        self.assertNotIn('load_from((checkpoint_path / "optimizer.pt")', source)

    def test_evaluator_cli_has_no_final_seed_or_required_program_channel(self) -> None:
        source = MAIN.read_text(encoding="utf-8")
        expected_block = source.split("constexpr std::array<std::string_view, 13> expected", 1)[1].split("};", 1)[0]
        self.assertNotIn('"--seed"', expected_block)
        self.assertNotIn('"--required-program"', expected_block)
        self.assertIn('"--checkpoint"', expected_block)
        self.assertIn('"--native-probe"', expected_block)
        self.assertIn('values.at("--policy-split") != "final"', source)

    def test_evaluator_public_capability_mapping_covers_every_program(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for program in range(1, 17):
            self.assertIn(f"return {program};", source)
        self.assertIn("program_mask.sum().item", source)
        self.assertIn("batch.recurrent_reset.item<bool>()", source)

    def test_schema_rejects_seed_and_required_program_mutations(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        report = {
            "schema_version": "openttd-rl-v2-m22-evaluator-report-1",
            "status": "PASS",
            "checkpoint": {"architecture": "monolithic-generalist-v1", "id": "0" * 64, "run_seed": 1},
            "execution": {"device": "cpu", "greedy_masked": True, "optimizer_constructed": False,
                          "optimizer_deserialized": False, "optimizer_path_opened": False, "recurrent_reset": True},
            "public_state": {"cargo": "PASS", "climate": "temperate", "map_height": 64, "map_width": 64,
                             "native_probe": "passenger-service", "opponent": "not-applicable", "source_gate": "G15",
                             "task": "service", "transport_mode": "road"},
            "policy": {"action": "road-passenger", "action_index": 1, "legal_active_index": 1,
                       "legal_active_program": "road-passenger", "logits": [0.0] * 17,
                       "next_hidden": [0.0] * 256, "value": 0.0},
            "tensor_input": {"program_mask": [True, True] + [False] * 15, "public_features": [0.0] * 32},
        }
        jsonschema.validate(report, schema)
        for forbidden in ("seed", "required_program"):
            mutated = json.loads(json.dumps(report))
            mutated["public_state"][forbidden] = 1 if forbidden == "seed" else "road-passenger"
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(mutated, schema)
