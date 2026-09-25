"""Timing is separate evidence and must not change canonical episode behavior."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import stage_timing
import evaluate_live
import test_evaluate_live as fixtures


class StageTimingTests(unittest.TestCase):
    def test_disabled_spans_do_not_read_clock_or_create_file(self):
        with patch.object(stage_timing.time, "perf_counter_ns", side_effect=AssertionError("clock read")):
            with stage_timing.StageTimings() as timing:
                with timing.measure("disabled", step=1):
                    pass
        self.assertEqual(timing.sequence, 0)

    def test_nanosecond_units_order_and_failure_are_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "timing.jsonl"
            error = RuntimeError("injected")
            with patch.object(stage_timing.time, "perf_counter_ns", side_effect=[100, 400, 500, 1000]):
                with stage_timing.StageTimings(path) as timing:
                    with timing.measure("first", step=1):
                        pass
                    with self.assertRaises(RuntimeError) as caught:
                        with timing.measure("second", step=2):
                            raise error
            self.assertIs(caught.exception, error)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([r["elapsed_ns"] for r in rows], [300, 500])
            self.assertEqual([r["sequence"] for r in rows], [1, 2])
            self.assertEqual([r["status"] for r in rows], ["completed", "failed"])
            self.assertEqual([r["context"] for r in rows], [{"step": 1}, {"step": 2}])
            with self.assertRaises(FileExistsError):
                with stage_timing.StageTimings(path):
                    pass

    def test_episode_timing_preserves_random_actions_economics_and_default_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = []
            for enabled in (False, True):
                template, environment = fixtures.EpisodeTests().fixture(root)
                environment.mask = {"legal": [1, 1] + [0] * 39}
                environment.controller.mask.return_value = environment.mask
                output = root / ("timed" if enabled else "plain")
                with patch.object(evaluate_live.m07, "start_environment", return_value=environment):
                    result = evaluate_live.episode(engine=root / "engine", template=template, output=output,
                        reward={}, policy="random", seed=7, evaluator=None, package=None, stage_timing=enabled)
                del result["elapsed_seconds"]
                results.append(result)
            self.assertEqual(results[0], results[1])
            self.assertEqual((root / "plain/actions.jsonl").read_bytes(), (root / "timed/actions.jsonl").read_bytes())
            self.assertFalse((root / "plain/timing.jsonl").exists())
            records = [json.loads(l) for l in (root / "timed/timing.jsonl").read_text().splitlines()]
            self.assertEqual([r["context"]["step"] for r in records if r["stage"] == "game_step"], [1, 2])
            self.assertTrue(all(r["elapsed_ns"] >= 0 and r["status"] == "completed" for r in records))
            self.assertEqual(sum(r["stage"] == "legal_actions_request" for r in records), 1)

    def test_failed_step_retains_timing_and_original_episode_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, environment = fixtures.EpisodeTests().fixture(root)
            error = RuntimeError("native step failed")
            environment.controller.step.side_effect = error
            with patch.object(evaluate_live.m07, "start_environment", return_value=environment):
                with self.assertRaises(RuntimeError) as caught:
                    evaluate_live.episode(engine=root / "engine", template=template, output=root / "run",
                        reward={}, policy="wait", seed=1, evaluator=None, package=None, stage_timing=True)
            self.assertIs(caught.exception, error)
            record = json.loads((root / "run/episode.json").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["completed_actions"], 0)
            rows = [json.loads(l) for l in (root / "run/timing.jsonl").read_text().splitlines()]
            self.assertEqual(rows[-1]["stage"], "game_step")
            self.assertEqual(rows[-1]["status"], "failed")
            environment.controller.abort.assert_called_once()


class TimingEvidenceTests(unittest.TestCase):
    def rows(self):
        startup = ['environment_start', 'initial_snapshot', 'initial_write', 'package_before',
                   'policy_start', 'environment_close', 'policy_close', 'package_after']
        steps = ['legal_mask', 'policy_inputs', 'policy_request', 'trace_inputs', 'game_step',
                 'observe', 'trace_assemble', 'trace_serialize', 'trace_write', 'trace_flush']
        entries = [(name, {}) for name in startup]
        for step in range(1, 513):
            entries += [(name, {'step': step}) for name in steps]
            if step < 512:
                entries.append(('legal_actions_request', {'step': step}))
        return [{'schema': 'development-stage-wall-timing-v1', 'sequence': i,
                 'clock': 'perf_counter_ns', 'status': 'completed', 'stage': name,
                 'context': context, 'start_ns': i*10, 'elapsed_ns': 5}
                for i, (name, context) in enumerate(entries, 1)]

    def test_profile_rejects_missing_stage_and_overlapping_durations(self):
        import profile_evaluation
        from studies.evidence_v2 import Inputs
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'timing.jsonl'
            rows = self.rows()
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            result = profile_evaluation.timing_summary(path, Inputs())
            self.assertEqual(result['game_step']['calls'], 512)
            self.assertEqual(result['game_step']['total_seconds'], 2560/1e9)
            for failure in ['missing-step', 'missing-close', 'overlap', 'failed']:
                with self.subTest(failure=failure):
                    rows = self.rows()
                    if failure == 'missing-step':
                        rows = [r for r in rows if not (r['stage']=='game_step' and r['context']['step']==512)]
                    elif failure == 'missing-close':
                        rows = [r for r in rows if r['stage']!='policy_close']
                    elif failure == 'overlap':
                        rows[1]['start_ns'] = rows[0]['start_ns']
                    else:
                        rows[-1]['status'] = 'failed'
                    for i, row in enumerate(rows, 1):
                        row['sequence'] = i
                    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                    with self.assertRaises(ValueError):
                        profile_evaluation.timing_summary(path, Inputs())


if __name__ == "__main__":
    unittest.main()
