#!/usr/bin/env python3
"""Static and application tests for the M23 visible-playback foundation patch."""

from __future__ import annotations

import pathlib
import re
import subprocess
import unittest


class M23VisibleSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.relative_patch = pathlib.Path(
            "integration/openttd/patches/15.3/m23/"
            "0002-Add-M23-visible-normal-game-controller-foundation.patch"
        )
        cls.patch_path = cls.root / cls.relative_patch
        cls.patch = cls.patch_path.read_text(encoding="utf-8")

    def test_patch_has_deterministic_identity_and_bounded_scope(self) -> None:
        self.assertTrue(self.patch.startswith(
            "From bbfcd4ca3133a60f2e1b293bad68918a3c4c26c5 Mon Sep 17 00:00:00 2001\n"
        ))
        self.assertIn("Date: Sat, 1 Jan 2000 00:00:00 +0000", self.patch)
        touched = re.findall(r"^diff --git a/(\S+) b/\1$", self.patch, flags=re.MULTILINE)
        self.assertEqual(touched, [
            "src/CMakeLists.txt",
            "src/openttd.cpp",
            "src/rl_v2_neural_agent.cpp",
            "src/rl_v2_neural_agent.h",
            "src/rl_v2_neural_agent_gui.cpp",
            "src/rl_v2_program_executor.cpp",
            "src/rl_v2_program_executor.h",
        ])

    def test_patch_applies_after_source_integrated_equivalence_foundation(self) -> None:
        source = pathlib.Path(
            "/home/thecl/.codex/artifacts/openttd-rl/v2-m23-visible-runtime-baseline-a"
        )
        if not source.is_dir():
            self.skipTest("retained M23 source-integrated baseline is not present")
        completed = subprocess.run(
            ["git", "-C", str(source), "apply", "--check", "--whitespace=error-all",
             str(self.patch_path.resolve())],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_equivalence_entrypoint_remains_available_beside_playback(self) -> None:
        for token in (
            'config.at("operation") == "equivalence"',
            'config.at("operation") == "playback"',
            "PrepareRlV2NeuralAgentConfig(rl_v2_neural_agent_config)",
            "RlV2NeuralAgentGameLoop();",
        ):
            self.assertIn(token, self.patch)

    def test_playback_is_prevalidated_then_activated_in_a_normal_game(self) -> None:
        for token in (
            "ParsePlaybackConfig(config)", "M23DeploymentPackage", "ConfigureNormalWorld",
            "SM_NEWGAME", "Company::IsValidID(CompanyID::Begin())", "DoStartupNewCompany(true, slot)",
            "generated normal-game map dimensions differ from campaign",
            "generated normal-game climate differs from campaign",
        ):
            self.assertIn(token, self.patch)

    def test_controller_runs_recurrent_masked_inference_at_policy_boundaries(self) -> None:
        for token in (
            "std::vector<float> PublicFeatures() const", "std::vector<uint8_t> ProgramMask()",
            "output.next_hidden.size() == 256", "next_hidden", "interval_ticks", "legal_programs_",
            "GetRlV2ProgramIndex", "ExecuteBoundary(this->last_program_, true)",
        ):
            self.assertIn(token, self.patch)

    def test_native_controls_inspection_and_safe_fault_state_are_present(self) -> None:
        for token in (
            '"Start"', '"Stop"', '"Step boundary"', '"Reload package"',
            '"Pause game"', "ToggleRlV2NeuralAgentPause", "ControllerState::Faulted",
            "ExecuteBoundary(0, false)", 'fmt::format("State:',
            'fmt::format("Last error:', 'fmt::format("Executor:',
        ):
            self.assertIn(token, self.patch)

    def test_outputs_are_bounded_atomic_and_use_normal_save_and_screenshot_paths(self) -> None:
        for token in (
            "maximum_records", "bounded canonical controller log", 'report_path.string() + ".tmp"', "WriteReport",
            "SaveOrLoad", "SLO_SAVE", "MakeScreenshot(SC_VIEWPORT",
            '"policy-boundary"', '"complete"',
        ):
            self.assertIn(token, self.patch)

    def test_executor_dispatch_is_explicitly_a_nonaccepting_discovery_foundation(self) -> None:
        for program in (
            "WAIT", "ROAD_PASSENGER", "ROAD_CARGO", "RAIL_PASSENGER", "RAIL_FREIGHT",
            "SHIP_NATURAL", "SHIP_CONSTRUCTED", "AIR_SERVICE", "AIR_HELICOPTER",
            "MULTIMODAL_DISCOVERY", "MODE_ROUTER", "COMPETITION_INSPECT",
            "CALENDAR_INSPECT", "AUTHORITY_ECONOMY", "EVENT_RECOVERY",
            "GAMESCRIPT_INSPECT", "CONTENT_INSPECT",
        ):
            self.assertIn(program, self.patch)
        self.assertIn('this->state_.last_command = "NO_OP_DISCOVERY"', self.patch)
        self.assertIn("uint64_t command_count = 0", self.patch)
        for forbidden in (
            "ResetM16", "RunM16CargoQualification", "RunM17RailQualification",
            "RunM18ShipQualification", "RunM19AirQualification", "RunM20CompetitionQualification",
        ):
            self.assertNotIn(forbidden, self.patch)


if __name__ == "__main__":
    unittest.main()
