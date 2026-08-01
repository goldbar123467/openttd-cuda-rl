#!/usr/bin/env python3
"""Contract, mutation, parser, and source tests for M02 map feasibility."""

from __future__ import annotations

import hashlib
import json
import lzma
import pathlib
import re
import tempfile
import unittest
from unittest import mock

import compare_m02_map_feasibility
import prepare_openttd_source
import run_m02_map_feasibility


class V1M02MapFeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.plan_path = cls.root / "config/v1/m02-map-feasibility-plan.json"
        cls.plan_schema_path = (
            cls.root / "docs/project/schema/v1-m02-map-feasibility-plan.schema.json"
        )
        cls.report_schema_path = (
            cls.root / "docs/project/schema/v1-m02-map-feasibility-report.schema.json"
        )
        cls.patch_path = (
            cls.root
            / "integration/openttd/patches/15.3/m02/0002-rl-environment-32x32-feasibility.patch"
        )
        cls.plan, cls.plan_sha256 = run_m02_map_feasibility.load_plan(
            cls.plan_path,
            cls.plan_schema_path,
        )

    def test_plan_and_report_schemas_are_valid_and_fail_closed(self) -> None:
        run_m02_map_feasibility.validate_plan_files(self.root, self.plan)
        report_schema = run_m02_map_feasibility.load_strict_json(self.report_schema_path)
        with self.assertRaisesRegex(
            run_m02_map_feasibility.M02FeasibilityError,
            "schema validation failed",
        ):
            run_m02_map_feasibility.validate_schema(
                {"schema_version": "wrong"},
                report_schema,
                "mutated report",
            )
        self.assertEqual(
            self.plan_sha256,
            "344bae1f25a394700667e38d2cee1e4409ee322218165cb01ce9884327b3da79",
        )

    def test_accepted_m01_source_identity_is_unchanged(self) -> None:
        profile = self.root / "config/v1/openttd-source-profile.json"
        series = self.root / "integration/openttd/patches/15.3/series"
        patch = self.root / "integration/openttd/patches/15.3/0001-gcc13-language-map-emplace.patch"
        self.assertEqual(
            hashlib.sha256(profile.read_bytes()).hexdigest(),
            "563339037626a8bb5a54e2f6a71e69500ccee44c11dfff2ce96bc4a96ef6c6cf",
        )
        self.assertEqual(
            hashlib.sha256(series.read_bytes()).hexdigest(),
            "f982ca6f630c74e240af16d6cb628660a41997cea6ff0c4940839d2ba80b21e2",
        )
        self.assertEqual(
            hashlib.sha256(patch.read_bytes()).hexdigest(),
            "0d056466b1abf5df755790f691c99c1db32d3e5f8498fae273abf7d4e4f2ac33",
        )

    def test_m02_delta_inventory_is_exact_and_ordered_after_m01(self) -> None:
        series, patches, records = run_m02_map_feasibility.validate_delta_series(
            self.root,
            self.plan["source"],
        )
        self.assertEqual(series.name, "series")
        self.assertEqual([path.name for path in patches], [self.patch_path.name])
        self.assertEqual(records, self.plan["source"]["patches"])
        self.assertEqual(records[0]["order"], 2)
        self.assertEqual(
            records[0]["sha256"],
            "8c4c9f8511c4eea96d5ef1d2ca23a68a673c75692972243d8ddb11d91b28207f",
        )

    def test_m02_delta_applies_exactly_and_produces_the_pinned_tree(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw)
            source = temporary / "source"
            base_manifest = temporary / "base.json"
            base = prepare_openttd_source.prepare(
                root=self.root,
                profile_path=self.root / self.plan["source"]["base_profile_path"],
                profile_schema_path=self.root / "docs/project/schema/v1-source-profile.schema.json",
                manifest_schema_path=self.root
                / "docs/project/schema/v1-prepared-source-manifest.schema.json",
                object_repository_override=self.root / "openttd-upstream",
                output=source,
                manifest_path=base_manifest,
            )
            self.assertEqual(
                base["preparation_identity_sha256"],
                self.plan["source"]["base_preparation_identity_sha256"],
            )
            series, patches, records = run_m02_map_feasibility.validate_delta_series(
                self.root,
                self.plan["source"],
            )
            prepare_openttd_source.apply_patches(
                source,
                patches,
                run_m02_map_feasibility.SOURCE_TREE,
            )
            result_tree = prepare_openttd_source.git(source, "write-tree")
            self.assertEqual(result_tree, self.plan["source"]["result_tree"])
            self.assertEqual(
                run_m02_map_feasibility.composed_source_identity(
                    base["preparation_identity_sha256"],
                    hashlib.sha256(series.read_bytes()).hexdigest(),
                    records,
                    result_tree,
                ),
                self.plan["source"]["composed_identity_sha256"],
            )

    def test_patch_scope_is_map_feasibility_only(self) -> None:
        text = self.patch_path.read_text(encoding="utf-8")
        paths = {
            match.group(1)
            for match in re.finditer(r"^diff --git a/([^ ]+) b/", text, re.MULTILINE)
        }
        self.assertEqual(
            paths,
            {
                "cmake/Options.cmake",
                "src/landscape.cpp",
                "src/main_gui.cpp",
                "src/map_func.h",
                "src/map_type.h",
                "src/newgrf/newgrf_actd.cpp",
                "src/openttd.cpp",
                "src/script/api/script_date.hpp",
                "src/saveload/map_sl.cpp",
                "src/tests/tilearea.cpp",
                "src/tgp.cpp",
                "src/tree_cmd.cpp",
            },
        )
        for forbidden in ("PPO", "LibTorch", "ONNX", "rl_bridge", "bus scenario"):
            self.assertNotIn(forbidden, text)

    def test_option_and_runtime_hooks_are_flag_gated(self) -> None:
        text = self.patch_path.read_text(encoding="utf-8")
        self.assertIn(
            'option(OPTION_RL_ENVIRONMENT "Enable the experimental 32x32 RL environment map profile" OFF)',
            text,
        )
        hook = 'IConsoleCmdExec("exec scripts/rl_environment_editor_start.scr 0");'
        self.assertIn("#ifdef WITH_RL_ENVIRONMENT\n+\t" + hook, text)
        self.assertIn("#endif\n }", text)
        self.assertIn(
            "+#ifdef WITH_RL_ENVIRONMENT\n"
            "+\t/* ResetNewGRFData repopulates the engine pool; release it at process shutdown. */\n"
            "+\tPoolBase::Clean(PT_ALL);\n"
            "+#endif",
            text,
        )
        self.assertIn("+\tenum Date : int32_t {", text)

    def test_new_lfsr_feedbacks_have_maximal_period(self) -> None:
        for bits, feedback in ((10, 0x204), (11, 0x402)):
            state = 1
            seen: set[int] = set()
            while state not in seen:
                seen.add(state)
                state = (state >> 1) ^ (feedback if state & 1 else 0)
            self.assertEqual(state, 1)
            self.assertEqual(len(seen), (1 << bits) - 1)

    def test_save_parser_extracts_dimensions_empty_types_and_map_oracle(self) -> None:
        width = height = 32
        maps = bytes.fromhex(
            "4d4150530310060564696d5f78060564696d5f790009"
        ) + width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x00"
        tile_data = bytes([0x00] * 900 + [0x70] * 124)
        chunks = []
        for tag, data in (
            (b"MAPT", tile_data),
            (b"MAPH", b""),
            (b"MAPO", b""),
            (b"MAP2", b""),
            (b"M3LO", b""),
            (b"M3HI", b""),
            (b"MAP5", b""),
            (b"MAPE", b""),
            (b"MAP7", b""),
            (b"MAP8", b""),
        ):
            chunks.append(tag + len(data).to_bytes(4, "big") + data)
        container = b"OTTX\x00\x00\x00\x00" + lzma.compress(maps + b"".join(chunks))
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "fixture.sav"
            path.write_bytes(container)
            summary, map_bytes = run_m02_map_feasibility.parse_save(path)
        self.assertEqual((summary["width"], summary["height"]), (32, 32))
        self.assertEqual(summary["tile_type_counts"], {"clear": 900, "void": 124})
        self.assertEqual(summary["map_sha256"], hashlib.sha256(map_bytes).hexdigest())
        run_m02_map_feasibility.validate_empty_save(summary, 32, "fixture")
        canonical = run_m02_map_feasibility.canonical_save_summary(summary)
        self.assertNotIn("save_sha256", canonical)
        self.assertNotIn("payload_sha256", canonical)

    def test_save_parser_rejects_non_ottd_and_nonempty_editor_maps(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "bad.sav"
            path.write_bytes(b"not a save")
            with self.assertRaisesRegex(
                run_m02_map_feasibility.M02FeasibilityError,
                "not an OTTX container",
            ):
                run_m02_map_feasibility.parse_save(path)
        with self.assertRaisesRegex(
            run_m02_map_feasibility.M02FeasibilityError,
            "not a true empty editor map",
        ):
            run_m02_map_feasibility.validate_empty_save(
                {
                    "width": 32,
                    "height": 32,
                    "tile_type_counts": {"house": 1, "void": 1023},
                },
                32,
                "mutation",
            )

    def test_runtime_save_discovery_excludes_source_and_build_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            expected = [
                root / "reference-runtime-generated64/save/reference.sav",
                root / "profiles/rl-on-assert/runtime-empty32-1/save/empty.sav",
            ]
            excluded = [
                root / "source/regression/stationlist/test.sav",
                root / "profiles/rl-on-assert/build/regression/test.sav",
            ]
            for path in expected + excluded:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            self.assertEqual(
                run_m02_map_feasibility.discover_runtime_save_paths(root),
                sorted(expected),
            )

    def test_canonical_workspace_and_rpath_contract_are_run_independent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            first = root / "run-a"
            second = root / "run-b"
            self.assertEqual(
                run_m02_map_feasibility.canonical_workspace_root(first),
                run_m02_map_feasibility.canonical_workspace_root(second),
            )
            self.assertEqual(
                run_m02_map_feasibility.CMAKE_REPRODUCIBILITY_OPTIONS,
                ("-DCMAKE_SKIP_RPATH=ON",),
            )

    def test_failed_canonical_workspace_is_preserved_inside_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            artifact_root = root / "run"
            artifact_root.mkdir()
            options = mock.Mock(
                root=self.root,
                artifact_root=artifact_root,
                cache_root=root / "missing-cache",
                reference_root=root / "missing-reference",
            )
            with self.assertRaisesRegex(
                run_m02_map_feasibility.M02FeasibilityError,
                "offline build-input cache does not exist",
            ):
                run_m02_map_feasibility.run_feasibility(options)
            self.assertFalse(
                run_m02_map_feasibility.canonical_workspace_root(artifact_root).exists()
            )
            self.assertTrue((artifact_root / "failed-canonical-workspace").is_dir())

    def test_unit_summary_and_diagnostic_guards_fail_explicitly(self) -> None:
        self.assertEqual(
            run_m02_map_feasibility.parse_unit_summary(
                "All tests passed (2193 assertions in 96 test cases)"
            ),
            (96, 2193),
        )
        with self.assertRaisesRegex(
            run_m02_map_feasibility.M02FeasibilityError,
            "cannot parse complete",
        ):
            run_m02_map_feasibility.parse_unit_summary("some tests passed")
        with self.assertRaisesRegex(
            run_m02_map_feasibility.M02FeasibilityError,
            "forbidden diagnostic",
        ):
            run_m02_map_feasibility.check_forbidden_diagnostics(
                "runtime error: shift exponent -1",
                "runtime error:",
                "mutation",
            )

    def test_comparison_rejects_canonical_output_drift(self) -> None:
        profile = {
            "id": "profile",
            "binary_sha256": "a" * 64,
            "test_binary_sha256": "b" * 64,
        }
        report = {"result": "PASS", "report_identity_sha256": "c" * 64, "profiles": [profile]}
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            for relative in compare_m02_map_feasibility.CANONICAL_FILES:
                (first / relative).write_text("same\n", encoding="utf-8")
                (second / relative).write_text("same\n", encoding="utf-8")
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(
                compare_m02_map_feasibility,
                "validate_report",
                side_effect=[report, report],
            ):
                result = compare_m02_map_feasibility.compare(first, second, schema)
            self.assertEqual(result["result"], "PASS")
            (second / "commands.json").write_text("different\n", encoding="utf-8")
            with mock.patch.object(
                compare_m02_map_feasibility,
                "validate_report",
                side_effect=[report, report],
            ):
                with self.assertRaisesRegex(
                    compare_m02_map_feasibility.M02ComparisonError,
                    "canonical output differs",
                ):
                    compare_m02_map_feasibility.compare(first, second, schema)


if __name__ == "__main__":
    unittest.main()
