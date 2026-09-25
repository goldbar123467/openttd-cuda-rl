import copy
from pathlib import Path
import sys
import tempfile
import unittest
import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from studies.protocol_v2 import PROTOCOL_PATH, PROTOCOL_SHA256, development_matrix, load_protocol, require_development_matrix, require_episode_identity, validate_registration


class ProtocolTests(unittest.TestCase):
    def test_frozen_protocol_covers_disjoint_native_partitions(self):
        p = load_protocol()
        self.assertFalse(set(p["training_maps"]) & set(p["development"]["maps"]))
        self.assertFalse(set(p["held_out"]["maps"]) & set(p["development"]["maps"]))
        rows = development_matrix(p)
        self.assertEqual(len(rows), 32)
        self.assertEqual(sum(r["mode"] == "greedy" for r in rows), 8)
        require_development_matrix(rows[::-1], p)
        for wrong in (rows[:-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                require_development_matrix(wrong, p)
        wrong = copy.deepcopy(rows)
        wrong[0]["split"] = "training"
        with self.assertRaises(ValueError):
            require_development_matrix(wrong, p)

    def test_protocol_edits_do_not_silently_change_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "edited.json"
            path.write_text(PROTOCOL_PATH.read_text().replace('"greedy_sustained_maps_per_training_seed": 7',
                                                             '"greedy_sustained_maps_per_training_seed": 6'))
            with self.assertRaisesRegex(ValueError, "identity changed"):
                load_protocol(path)

    def test_registered_episode_checks_observed_reset_and_explicit_record(self):
        case = development_matrix(load_protocol())[0]
        record = {**case, "status": "passed", "engine_sha256": "a" * 64, "guidance": "one-bus-public-plan-v2",
                  "decisions": 512, "final_evaluation_accessed": False,
                  "final_observation": {"terminal": False, "truncated": True}}
        reset = {"split": case["split"], "map_seed": case["map_seed"]}
        def verify(r, s):
            require_episode_identity(r, s, case, engine_sha256="a" * 64, guidance="one-bus-public-plan-v2")
        verify(record, reset)
        for key, value in (("status", "running"), ("split", "training"), ("map_seed", None),
                           ("mode", "sampled"), ("sampling_seed", 123), ("guidance", "one-bus-public-plan-v1"),
                           ("decisions", 128), ("engine_sha256", "b" * 64), ("final_evaluation_accessed", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify({**record, key: value}, reset)
        with self.assertRaises(ValueError):
            verify(record, {**reset, "split": "training"})
        with self.assertRaises(ValueError):
            verify(record, {**reset, "map_seed": 0})

    def test_registration_binds_exact_arm_seeds_budget_and_driver(self):
        p = load_protocol()
        artifact = {"path": str(Path.cwd() / "fixture.bin"), "sha256": "a" * 64}
        registration = {
            "format": "openttd-rl-dev-study-registration-1", "study_id": "test-a1", "registered_utc": "2026-09-25T14:34:35Z",
            "protocol_sha256": PROTOCOL_SHA256, "arm": "A1", "training_seeds": p["training_seeds"],
            "training": {**p["fixed_training"], **{k: v for k, v in p["arms"][1].items() if k != "id"}},
            "runtime": {"device": "cuda:0", "python": "3.12", "torch": "2.9.1", "torch_cuda": "12.8",
                        "cuda_available": True, "gpu": "fixture GPU", "compute_capability": [7, 5]},
            "source": {"commit": "b" * 40, "status": "", "working_files_sha256": "c" * 64},
            "source_archive": str(Path.cwd() / "fixture-source"), "driver": "scripts/dev/studies/recovery_v2.py",
            "code_sha256": {"scripts/dev/studies/recovery_v2.py": "d" * 64},
            "binaries": {name: artifact for name in ("engine", "trainer", "policy")},
            "content": artifact,
            "qualification_reports": [artifact], "cost_estimate": artifact, "maximum_native_jobs": 2,
            "maximum_cuda_training_jobs": 1,
        }
        validate_registration(registration, p)
        for key, value in (("decisions", 1024), ("gamma", .995), ("entropy_coefficient", .01), ("asset_potential", 0)):
            altered = copy.deepcopy(registration)
            altered["training"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_registration(altered, p)
        for key, value in (("training_seeds", [20260923]), ("registered_utc", "yesterday"), ("maximum_cuda_training_jobs", 2), ("arm", "A5")):
            with self.subTest(key=key), self.assertRaises(jsonschema.ValidationError):
                validate_registration({**registration, key: value}, p)
        with self.assertRaises(ValueError):
            validate_registration({**registration, "driver": "scripts/dev/studies/another.py"}, p)
        with self.assertRaises(ValueError):
            validate_registration({**registration, "protocol_sha256": "e" * 64}, p)


if __name__ == "__main__":
    unittest.main()
