import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from power_table import T95, detectable_multiplier, project, t_power, variance_components
from studies.estimate_cost_v2 import request_span, workload
from studies.evidence_v2 import Inputs
from studies.protocol_v2 import load_protocol


class PlanningTests(unittest.TestCase):
    def test_noncentral_t_zero_effect_has_registered_five_percent_size(self):
        for n in (3, 5):
            # Known two-sided t critical values give 5% null rejection. A
            # finer independent quadrature grid also checks the power solve.
            self.assertAlmostEqual(t_power(0, n), .05, places=8)
            delta = detectable_multiplier(n)
            self.assertAlmostEqual(t_power(delta, n, steps=8192), .8, places=8)
            self.assertAlmostEqual(t_power(-delta, n), .8, places=8)

    def test_seed_only_variance_cannot_be_reduced_by_more_maps(self):
        rows = [{"training_seed": s, "map_seed": m, "action_seed": a, "difference": s}
                for s in (-1, 0, 1) for m in (10, 20) for a in (2, 3, 4)]
        result = project(rows, {3: 1, 5: 1})
        self.assertEqual(result["nonnegative_planning_components"], {"training_seed": 1., "map_within_seed": 0., "action_within_map": 0.})
        self.assertAlmostEqual(result["observed_conditional_t_half_width_95"], T95[3] / math.sqrt(3))
        self.assertEqual(result["planning_table"][0]["projected_standard_error"], result["planning_table"][1]["projected_standard_error"])
        for bad in (rows[:-1], rows + [rows[0]], rows[:6]):
            with self.assertRaises(ValueError): variance_components(bad)

    def test_map_and_action_noise_are_estimated_separately_without_hiding_negative_seed_estimate(self):
        rows = [{"training_seed": s, "map_seed": m, "action_seed": a, "difference": m + a}
                for s in (1, 2, 3) for m in (-2, 2) for a in (-1, 0, 1)]
        result = variance_components(rows)
        self.assertEqual(result["raw_variance_components"]["action_within_map"], 1.)
        self.assertAlmostEqual(result["raw_variance_components"]["map_within_seed"], 23/3)
        self.assertEqual(result["raw_variance_components"]["training_seed"], -4.)
        self.assertEqual(result["negative_component_estimates"], ["training_seed"])

    def test_registered_workload_does_not_count_action_seeds_as_models(self):
        self.assertEqual(workload(load_protocol()), {"training_runs": 12, "training_decisions": 98304,
            "candidate_games": 384, "control_games_with_verified_reuse": 128,
            "control_games_without_reuse": 256, "conditional_heldout_games": 160})

    def test_request_span_includes_interrequest_inference_but_not_unmeasured_archival(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "requests.jsonl"
            events = [{"kind": "request", "request": {"operation": "OBSERVE", "id": 1}, "monotonic_ns": 1_000_000_000},
                      {"kind": "response", "response": {"id": 1}, "elapsed_ns": 2_000_000},
                      {"kind": "request", "request": {"operation": "CLOSE", "id": 2}, "monotonic_ns": 5_000_000_000},
                      {"kind": "response", "response": {"id": 2}, "elapsed_ns": 30_000_000}]
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
            inputs = Inputs()
            self.assertAlmostEqual(request_span(path, inputs), 4.03)
            inputs.unchanged()
            path.write_text("\n".join(json.dumps(e) for e in events[:-1]) + "\n")
            with self.assertRaises(ValueError): request_span(path, Inputs())


if __name__ == "__main__":
    unittest.main()
