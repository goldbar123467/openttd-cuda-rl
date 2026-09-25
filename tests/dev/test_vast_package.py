"""Failure/restart tests use temporary files and never open game splits."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/dev"))
from local import write_json
from studies.evidence_v2 import Inputs
from studies.execution_v2 import artifact, check_qualification, CORRECTNESS_CHECKS
from studies.protocol_v2 import load_protocol, PROTOCOL_SHA256
from studies import recovery_v2, unattended_v2 as runner
from studies.training_result_v2 import training_history

spec = importlib.util.spec_from_file_location("vast_entrypoint", ROOT / "deployment/vast/entrypoint.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


def registration():
    p = load_protocol()
    return {"training": {**p["fixed_training"], **{k: v for k, v in p["arms"][3].items() if k != "id"}},
            "source": {"commit": "a" * 40, "working_files_sha256": "b" * 64, "status": ""},
            "training_seeds": p["training_seeds"], "runtime": {"device": "cuda:0"},
            "binaries": {k: {"path": "/fixture/" + k, "sha256": "c" * 64} for k in ("engine", "trainer", "policy")}}


def training_record(reg):
    t, p = reg["training"], load_protocol()
    return {"kind": "native-v2-live-recurrent-ppo", "status": "interrupted", "source": reg["source"],
            "study_registration_sha256": "d" * 64, "run_seed": p["training_seeds"][0],
            "device": "cuda:0", "environments": 1, "requested_updates": 128, "rollout_steps": 64,
            "episode_horizon": 128, "training_map_seeds": p["training_maps"], "guidance": t["guide"],
            "trainer_sha256": "c" * 64, "engine_sha256": "c" * 64, "updates": [], "checkpoints": [],
            **{k: t[k] for k in ("financial_features", "reuse_bootstrap_tensors", "checkpoint_interval", "gamma",
                "gae_lambda", "entropy_coefficient", "optimization_epochs", "sequence_length", "choice_weighted", "asset_potential")}}


class PackageTests(unittest.TestCase):
    def test_revision_mount_and_space_refuse_unsafe_defaults(self):
        for value in (None, "main", "a" * 39, "A" * 40):
            with self.assertRaises(ValueError):
                entrypoint.checked_revision(value)
        self.assertEqual(entrypoint.checked_revision("a" * 40), "a" * 40)
        with tempfile.TemporaryDirectory() as directory:
            mountinfo = Path(directory) / "mountinfo"
            mountinfo.write_text("1 0 0:1 / / rw - overlay overlay rw\n2 1 0:2 / /data rw - ext4 disk rw\n")
            self.assertEqual(entrypoint.persistent_mount(Path("/data/study"), mountinfo), Path("/data"))
            with self.assertRaises(ValueError):
                entrypoint.persistent_mount(Path("/tmp/study"), mountinfo)
        with self.assertRaisesRegex(RuntimeError, "storage"):
            runner.storage(Path("/fixture"), 100, usage=lambda _: SimpleNamespace(free=99))
        self.assertEqual(runner.storage(Path("/fixture"), 100, usage=lambda _: SimpleNamespace(free=100)), 100)

    def test_exact_budget_and_inherited_resume_point(self):
        reg = registration()
        command = runner.training_command(Path("/reg"), reg, reg["training_seeds"][0], Path("/out"),
                                          checkpoint=Path("/checkpoint"), restored_update=40)
        self.assertEqual(command[command.index("--updates") + 1], "88")
        self.assertIn("--training-reset-probes", command)
        self.assertIn("--asset-potential", command)
        self.assertEqual(runner.resume_point({"checkpoints": [], "resume_from": "/old/checkpoint", "restored_update": 40}),
                         (Path("/old/checkpoint"), 40))
        self.assertEqual(runner.resume_point({"checkpoints": [{"status": "saved", "path": "/new/checkpoint", "update": 48}],
                                             "resume_from": "/old/checkpoint", "restored_update": 40}), (Path("/new/checkpoint"), 48))

    def test_fresh_restart_retains_history_and_cannot_replace_failed_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root, reg = Path(directory), registration()
            first = training_record(reg)
            (root / "first").mkdir()
            (root / "second").mkdir()
            write_json(root / "first/run.json", first)
            second = training_record(reg)
            second["interrupted_predecessor"] = artifact(root / "first/run.json")
            write_json(root / "second/run.json", second)
            training_history(artifact(root / "second/run.json"), reg, load_protocol(), Inputs(), "d" * 64)
            for changes in ({"status": "failed"}, {"checkpoints": [{"status": "saved"}]}, {"run_seed": 20260924}):
                write_json(root / "first/run.json", {**first, **changes})
                write_json(root / "second/run.json", {**second, "interrupted_predecessor": artifact(root / "first/run.json")})
                with self.assertRaisesRegex(ValueError, "Fresh restart"):
                    training_history(artifact(root / "second/run.json"), reg, load_protocol(), Inputs(), "d" * 64)

    def test_completed_or_failed_training_is_never_relaunched_despite_receipt_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root, reg = Path(directory), registration()
            write_json(root / "registration.json", reg)
            output = root / "seed/segment-001"
            output.mkdir(parents=True)
            (root / "seed/segment-002").mkdir()
            write_json(root / "seed/segment-002.json", {"status": "interrupted"})
            for status in ("completed", "early-stopped", "failed"):
                write_json(output / "run.json", {"status": status})
                write_json(root / "seed/segment-001.json", {"status": "finished"})
                (root / "seed/segment-001.log").write_text("retained")
                with patch.object(runner, "preflight", return_value=(reg, load_protocol(), Inputs())), \
                        patch.object(runner, "verify_training"), patch.object(recovery_v2, "launch") as launch:
                    self.assertEqual(runner.train_seed(root / "registration.json", root / "seed", reg["training_seeds"][0]), output)
                    launch.assert_not_called()

    def test_evaluation_resume_preserves_failed_and_completed_cases(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root, reg = Path(directory), registration()
            training = [{"status": "completed", "training_seed": s, "training_run": "/training/" + str(s)} for s in reg["training_seeds"]]
            invocations = []
            def launch(command, log):
                output = Path(command[command.index("--output") + 1])
                invocations.append(output)
                code = int(len(invocations) == 2)
                output.mkdir()
                write_json(output / "run.json", {"status": "failed" if code else "passed"})
                return code
            def reader(reference, case, reg, inputs):
                return {**case, "run": reference, "execution_status": "passed", "summary": {}, "guidance": reg["training"]["guide"]}
            first = recovery_v2.evaluate_jobs(reg, load_protocol(), training, root, Inputs(), launcher=launch, reader=reader)
            self.assertEqual(len(first), 160)
            self.assertEqual(sum(c["execution_status"] == "failed" for c in first), 1)
            with patch.object(recovery_v2, "launch", side_effect=AssertionError("must not relaunch")) as unused:
                second = recovery_v2.evaluate_jobs(reg, load_protocol(), training, root, Inputs(), launcher=unused, reader=reader)
            self.assertEqual(first, second)
            # A supervisor crash after a failed child must not grant another attempt.
            receipt = sorted((root / "logs").glob("*.json"))[0]
            saved = json.loads(receipt.read_text())
            saved["status"] = "interrupted"
            write_json(receipt, saved)
            write_json(Path(saved["output"]) / "run.json", {"status": "failed"})
            third = recovery_v2.evaluate_jobs(reg, load_protocol(), training, root, Inputs(), launcher=unused, reader=reader)
            self.assertEqual(sum(c["execution_status"] == "failed" for c in third), 2)

    def test_supervisor_finishes_all_arms_before_no_eligible_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root, reg = Path(directory), registration()
            calls = []
            def register(args):
                args.output.mkdir(parents=True)
                write_json(args.output / "registration.json", {"arm": args.arm})
                calls.append(("register", args.arm))
            def train(path, output, seed):
                calls.append(("train", json.loads(path.read_text())["arm"], seed))
                output.mkdir(parents=True)
                return output
            def evaluate(args, **kwargs):
                arm = json.loads(args.registration.read_text())["arm"]
                calls.append(("evaluate", arm))
                args.output.mkdir(parents=True)
                write_json(args.output / "result.json", {"decision": {"arm": arm, "eligible": False}, "cases": []})
                return args.output / "result.json"
            def freeze(results, output):
                self.assertEqual([r[1] for r in calls if r[0] == "evaluate"], ["A0", "A1", "A2", "A3"])
                self.assertEqual(len(results), 4)
                output.mkdir()
                write_json(output / "selection.json", {"status": "no-eligible-arm"})
            with patch.object(runner, "source_identity", return_value=reg["source"]), patch.object(runner, "runtime"), \
                    patch.object(runner, "storage", return_value=runner.MINIMUM_INITIAL_FREE_BYTES), \
                    patch.object(runner.vast_bootstrap, "build", return_value=reg["binaries"]), \
                    patch.object(runner.vast_bootstrap, "qualify", return_value=root / "qualification.json"), \
                    patch.object(runner, "register", side_effect=register), patch.object(runner, "preflight"), \
                    patch.object(runner, "train_seed", side_effect=train), patch.object(recovery_v2, "evaluate", side_effect=evaluate), \
                    patch.object(runner.heldout_v2, "freeze", side_effect=freeze), \
                    patch.object(runner.heldout_v2, "selected_evidence", return_value=(None, load_protocol())), \
                    patch.object(runner.heldout_v2, "execute") as heldout:
                runner.run(SimpleNamespace(root=root, revision=reg["source"]["commit"]))
                heldout.assert_not_called()
            self.assertEqual(len([c for c in calls if c[0] == "train"]), 12)
            self.assertEqual(json.loads((root / "study.json").read_text())["status"], "completed")
            self.assertIn("No arm qualified", (root / "REPORT.md").read_text())

    def test_interruption_before_restore_uses_validated_target_and_cannot_claim_experience(self):
        with tempfile.TemporaryDirectory() as directory:
            root, reg = Path(directory), registration()
            parent = training_record(reg)
            (root / "parent").mkdir()
            (root / "child").mkdir()
            checkpoint = root / "parent/checkpoints/update-000008"
            checkpoint.mkdir(parents=True)
            (checkpoint / "trainer.pt").write_bytes(b"fixture")
            manifest = {"update": 8, "trainer_sha256": artifact(checkpoint / "trainer.pt")["sha256"]}
            write_json(checkpoint / "checkpoint.json", manifest)
            parent.update(updates=[{"update": i, "transitions": i * 64} for i in range(1, 9)],
                          training_reset_probes=[], initial_training_reset_probe={"update": 0},
                          checkpoints=[{"status": "saved", "path": str(checkpoint), "update": 8,
                                        "manifest_sha256": artifact(checkpoint / "checkpoint.json")["sha256"]}])
            write_json(root / "parent/run.json", parent)
            child = training_record(reg)
            child.update(requested_updates=120, resume_from=str(checkpoint), resume_parent=artifact(root / "parent/run.json"),
                         resume_target={"update": 8, "transitions": 512})
            write_json(root / "child/run.json", child)
            with patch("checkpoint_v2.compatibility", return_value={}), patch("checkpoint_v2.read", return_value=manifest):
                _, updates = training_history(artifact(root / "child/run.json"), reg, load_protocol(), Inputs(), "d" * 64)
                self.assertEqual(len(updates), 8)
                self.assertEqual(runner.resume_point(child), (checkpoint, 8))
                child["updates"] = [{"update": 9, "transitions": 576}]
                write_json(root / "child/run.json", child)
                with self.assertRaisesRegex(ValueError, "Unrestored"):
                    training_history(artifact(root / "child/run.json"), reg, load_protocol(), Inputs(), "d" * 64)

    def test_bundle_rejects_missing_gate_failed_cuda_and_changed_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root, reg = Path(directory), registration()
            reg["code_sha256"] = {"fixture": "e" * 64}
            checks = {}
            for name in CORRECTNESS_CHECKS:
                write_json(root / (name + ".json"), {"status": "passed"})
                checks[name] = artifact(root / (name + ".json"))
            names = ("rl_choice_weighted_cpu", "rl_choice_weighted_cuda", "rl_dev_v2_policy_cpu", "rl_dev_v2_policy_cuda",
                     "rl_checkpoint_roundtrip_cpu", "rl_checkpoint_roundtrip_cuda", "rl_behavior_replay_cpu", "rl_behavior_replay_cuda")
            xml = root / "native.xml"
            xml.write_text("<testsuite>" + "".join(f'<testcase status="run" name="{name}" />' for name in names) + "</testsuite>")
            report = {"format": "openttd-rl-v2-minimum-correctness-1", "status": "passed", "protocol_sha256": PROTOCOL_SHA256,
                      **{k: reg[k] for k in ("source", "code_sha256", "binaries", "runtime")}, "checks": checks, "native_junit": artifact(xml)}
            path = root / "qualification.json"
            write_json(path, report)
            check_qualification(artifact(path), reg, Inputs())
            changed = copy.deepcopy(report)
            changed["checks"].pop("recovery")
            write_json(path, changed)
            with self.assertRaisesRegex(ValueError, "bundle"):
                check_qualification(artifact(path), reg, Inputs())
            xml.write_text(xml.read_text().replace('name="rl_choice_weighted_cuda" />', 'name="rl_choice_weighted_cuda"><skipped /></testcase>'))
            report["native_junit"] = artifact(xml)
            write_json(path, report)
            with self.assertRaisesRegex(ValueError, "native"):
                check_qualification(artifact(path), reg, Inputs())
            write_json(root / "recovery.json", {"status": "failed"})
            with self.assertRaisesRegex(ValueError, "changed"):
                check_qualification(artifact(path), reg, Inputs())


if __name__ == "__main__":
    unittest.main()
