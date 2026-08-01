#!/usr/bin/env python3
"""Framing, source-delta, and oracle-helper tests for the M03 bridge."""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import struct
import tempfile
import unittest

import jsonschema

import m03_bridge_protocol
import prepare_openttd_source
import run_m02_map_feasibility
import run_m03_bridge
import validate_m02_scenario_contract


class V1M03BridgeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.series = cls.root / "integration/openttd/patches/15.3/m03/series"
        cls.patch = (
            cls.root
            / "integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch"
        )

    def test_crc32c_uses_castagnoli_reference_vector(self) -> None:
        self.assertEqual(m03_bridge_protocol.crc32c(b"123456789"), 0xE3069283)

    def test_response_frame_round_trips_exact_header_and_canonical_payload(self) -> None:
        encoded = m03_bridge_protocol.encode_frame(
            message_type=m03_bridge_protocol.STEP,
            flags=m03_bridge_protocol.FLAG_RESPONSE,
            session_id=41,
            episode_id=7,
            request_id=19,
            transition_ordinal=3,
            payload={"status": "OK", "value": 1},
        )
        self.assertEqual(len(encoded), 56 + len(b'{"status":"OK","value":1}'))
        read_descriptor, write_descriptor = os.pipe()
        try:
            os.write(write_descriptor, encoded)
            frame = m03_bridge_protocol.decode_frame(read_descriptor, 1.0)
        finally:
            os.close(read_descriptor)
            os.close(write_descriptor)
        self.assertEqual(frame.message_type, m03_bridge_protocol.STEP)
        self.assertEqual(frame.flags, m03_bridge_protocol.FLAG_RESPONSE)
        self.assertEqual((frame.session_id, frame.episode_id), (41, 7))
        self.assertEqual((frame.request_id, frame.transition_ordinal), (19, 3))
        self.assertEqual(frame.payload, {"status": "OK", "value": 1})

    def test_decoder_rejects_bad_checksum_duplicate_json_and_timeout(self) -> None:
        bad_checksum = m03_bridge_protocol.encode_frame(
            message_type=m03_bridge_protocol.SNAPSHOT,
            flags=m03_bridge_protocol.FLAG_RESPONSE,
            session_id=1,
            episode_id=1,
            request_id=1,
            transition_ordinal=0,
            payload={},
            checksum_override=1,
        )
        read_descriptor, write_descriptor = os.pipe()
        try:
            os.write(write_descriptor, bad_checksum)
            with self.assertRaisesRegex(
                m03_bridge_protocol.M03BridgeProtocolError,
                "CRC32C mismatch",
            ):
                m03_bridge_protocol.decode_frame(read_descriptor, 1.0)
        finally:
            os.close(read_descriptor)
            os.close(write_descriptor)

        duplicate = b'{"status":"OK","status":"ERROR"}'
        header = bytearray(
            m03_bridge_protocol.HEADER.pack(
                b"ORL1", 1, 0, 2, 1, len(duplicate), 0, 0, 1, 1, 1, 0
            )
        )
        struct.pack_into(
            "<I",
            header,
            16,
            m03_bridge_protocol.crc32c(header + duplicate),
        )
        read_descriptor, write_descriptor = os.pipe()
        try:
            os.write(write_descriptor, header + duplicate)
            with self.assertRaisesRegex(
                m03_bridge_protocol.M03BridgeProtocolError,
                "duplicate JSON key",
            ):
                m03_bridge_protocol.decode_frame(read_descriptor, 1.0)
        finally:
            os.close(read_descriptor)
            os.close(write_descriptor)

        read_descriptor, write_descriptor = os.pipe()
        try:
            with self.assertRaises(m03_bridge_protocol.M03BridgeTimeout):
                m03_bridge_protocol.decode_frame(read_descriptor, 0.01)
        finally:
            os.close(read_descriptor)
            os.close(write_descriptor)

    def test_m03_delta_inventory_and_identities_are_exact(self) -> None:
        self.assertEqual(self.series.read_text(encoding="utf-8"), self.patch.name + "\n")
        self.assertEqual(
            hashlib.sha256(self.series.read_bytes()).hexdigest(),
            run_m03_bridge.M03_SERIES_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(self.patch.read_bytes()).hexdigest(),
            run_m03_bridge.M03_PATCH_SHA256,
        )
        run_m03_bridge.validate_native_delta(self.root)

    def test_oracle_report_schema_and_isolation_guard_are_frozen(self) -> None:
        schema_path = (
            self.root
            / "docs/project/schema/v1-m03-bridge-oracle-report.schema.json"
        )
        self.assertEqual(
            hashlib.sha256(schema_path.read_bytes()).hexdigest(),
            run_m03_bridge.M03_REPORT_SCHEMA_SHA256,
        )
        schema = validate_m02_scenario_contract.load_strict_json(schema_path)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(
            schema["properties"]["isolation"]["properties"]["process_count"],
            {"const": 2},
        )
        self.assertIn("crash", schema["properties"]["failure_evidence"]["required"])
        self.assertEqual(
            schema["properties"]["scheduler"]["properties"]["rejected_action_ids"],
            {"const": [4_294_967_297]},
        )
        self.assertTrue(callable(run_m03_bridge.exercise_process_isolation))

    def test_m03_delta_applies_exactly_after_the_accepted_m02_tree(self) -> None:
        plan = run_m02_map_feasibility.load_strict_json(
            self.root / "config/v1/m02-map-feasibility-plan.json"
        )
        oracle = validate_m02_scenario_contract.load_strict_json(
            self.root / "config/v1/m02-reset-oracle.json"
        )
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw)
            source = temporary / "source"
            base = prepare_openttd_source.prepare(
                root=self.root,
                profile_path=self.root / plan["source"]["base_profile_path"],
                profile_schema_path=self.root / "docs/project/schema/v1-source-profile.schema.json",
                manifest_schema_path=self.root
                / "docs/project/schema/v1-prepared-source-manifest.schema.json",
                object_repository_override=self.root / "openttd-upstream",
                output=source,
                manifest_path=temporary / "base.json",
            )
            _, feasibility_patches, _ = run_m02_map_feasibility.validate_delta_series(
                self.root, plan["source"]
            )
            prepare_openttd_source.apply_patches(
                source,
                feasibility_patches,
                run_m02_map_feasibility.SOURCE_TREE,
            )
            self.assertEqual(
                prepare_openttd_source.git(source, "write-tree"),
                plan["source"]["result_tree"],
            )
            native_patch = self.root / oracle["native_delta"]["patches"][0]["path"]
            prepare_openttd_source.apply_patches(
                source,
                [native_patch],
                plan["source"]["result_tree"],
            )
            self.assertEqual(
                prepare_openttd_source.git(source, "write-tree"),
                oracle["native_delta"]["result_tree"],
            )
            prepare_openttd_source.apply_patches(
                source,
                [self.patch],
                oracle["native_delta"]["result_tree"],
            )
            result_tree = prepare_openttd_source.git(source, "write-tree")
            self.assertEqual(result_tree, run_m03_bridge.M03_RESULT_TREE)
            self.assertEqual(
                run_m02_map_feasibility.composed_source_identity(
                    run_m03_bridge.M02_BASE_COMPOSED_SOURCE_IDENTITY,
                    run_m03_bridge.M03_SERIES_SHA256,
                    [
                        {
                            "order": 4,
                            "path": self.patch.relative_to(self.root).as_posix(),
                            "sha256": run_m03_bridge.M03_PATCH_SHA256,
                        }
                    ],
                    result_tree,
                ),
                run_m03_bridge.M03_COMPOSED_SOURCE_IDENTITY,
            )
            self.assertEqual(
                base["preparation_identity_sha256"],
                plan["source"]["base_preparation_identity_sha256"],
            )

    def test_native_patch_is_bridge_only_and_keeps_learning_downstream(self) -> None:
        text = self.patch.read_text(encoding="utf-8")
        self.assertIn("RunRlEnvironmentBridge", text)
        self.assertIn("StateGameLoop();", text)
        self.assertIn("M02_SCRIPTED_BUS_SETUP", text)
        self.assertIn("inherited pipes", text)
        for forbidden in (
            "LibTorch",
            "ONNX Runtime",
            "CUDA",
            "policy observation",
            "neural agent",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIsNone(re.search(r"\bPPO\b", text))

    def test_control_snapshot_stripping_preserves_only_engine_evidence(self) -> None:
        snapshot = {
            "boundary_token": "token",
            "company": {"balance": 1},
            "episode_id": 2,
            "lifecycle": "AT_BOUNDARY",
            "session_id": 3,
            "tick": 128,
            "transition_ordinal": 1,
        }
        self.assertEqual(
            run_m03_bridge.strip_control_snapshot(snapshot),
            {"company": {"balance": 1}, "tick": 128},
        )


if __name__ == "__main__":
    unittest.main()
