#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PORT005 = Path(__file__).resolve().parent
DEV = ROOT / "scripts/dev"
sys.path.insert(0, str(PORT005))
sys.path.insert(0, str(DEV))

from invariants import InvariantError, validate_cargo, validate_ledger, validate_pool, validate_timer_rng
from build_sample_projection import build_sample_projection
from validate_field_schema import RegistryError, canonical_bytes, validate_projection, validate_registry


REGISTRY_PATH = ROOT / "parity/schema/fields-v1.json"
SCHEMA_PATH = ROOT / "parity/schema/field-schema.schema.json"
UPSTREAM = ROOT / "openttd-upstream"


def dump_temp(value: object) -> tempfile.NamedTemporaryFile:
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False)
    json.dump(value, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
    handle.close()
    return handle


class RegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = validate_registry(REGISTRY_PATH, SCHEMA_PATH, UPSTREAM)
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.by_id = {field["field_id"]: field for field in cls.registry["fields"]}
        cls.by_path = {field["path"]: field for field in cls.registry["fields"]}

    def assert_registry_rejected(self, mutant: dict) -> None:
        temporary = dump_temp(mutant)
        self.addCleanup(lambda: os.unlink(temporary.name))
        with self.assertRaises(RegistryError):
            validate_registry(Path(temporary.name), SCHEMA_PATH, UPSTREAM)

    def test_P005_REG_001_valid_complete_registry(self) -> None:
        self.assertGreaterEqual(len(self.registry["fields"]), 500)
        self.assertEqual(self.registry["fields"][0]["field_id"], 1)

    def test_registry_semantic_mutants_have_explicit_case_ids(self) -> None:
        mutations = []
        def mutation(label: str, action) -> None:
            value = copy.deepcopy(self.registry)
            action(value)
            mutations.append((label, value))

        mutation("REG-002-zero-id", lambda r: r["fields"][0].__setitem__("field_id", 0))
        mutation("REG-003-duplicate-id", lambda r: r["fields"][1].__setitem__("field_id", r["fields"][0]["field_id"]))
        mutation("REG-004-duplicate-path", lambda r: r["fields"][1].__setitem__("path", r["fields"][0]["path"]))
        mutation("REG-005-order", lambda r: r["fields"].__setitem__(slice(0, 2), list(reversed(r["fields"][:2]))))
        mutation("REG-006-class", lambda r: r["fields"][0].__setitem__("classification", "other"))
        mutation("REG-007-owner", lambda r: r["fields"][0].__setitem__("owner_type", ""))
        mutation("REG-008-lifecycle", lambda r: r["fields"][0].__setitem__("lifecycle_end", ""))
        mutation("REG-009-source-commit", lambda r: r["fields"][0].__setitem__("source_commit", ""))
        mutation("REG-010-source-pin", lambda r: r["fields"][0].__setitem__("source_commit", "0" * 40))
        mutation("REG-011-source-file", lambda r: r["fields"][0].__setitem__("source_file", ""))
        mutation("REG-012-source-absent", lambda r: r["fields"][0].__setitem__("source_file", "src/not-present.cc"))
        mutation("REG-013-symbol", lambda r: r["fields"][0].__setitem__("source_symbol", ""))
        mutation("REG-014-rationale", lambda r: r["fields"][0].__setitem__("future_influence_rationale", ""))
        mutation("REG-015-placeholder", lambda r: r["fields"][0].__setitem__("description", "TODO placeholder text"))
        mutation("REG-016-width", lambda r: r["fields"][0].__setitem__("width_bits", 24))
        mutation("REG-017-signedness", lambda r: r["fields"][0].__setitem__("signedness", None))
        dynamic_index = next(i for i, f in enumerate(self.registry["fields"]) if f["shape"] == "dynamic_array")
        mutation("REG-018-count-source", lambda r: r["fields"][dynamic_index].__setitem__("count_source_field", None))
        mutation("REG-019-capacity", lambda r: r["fields"][dynamic_index].__setitem__("maximum_capacity", 0))
        cache_index = next(i for i, f in enumerate(self.registry["fields"]) if f["cache_classification"] == "authoritative_cache")
        def make_derived(r):
            r["fields"][cache_index]["classification"] = "derived_rebuild"
            r["fields"][cache_index]["cache_classification"] = "derived_rebuild"
            r["fields"][cache_index]["cache_evidence_sha256"] = None
        mutation("REG-020-derived-proof", make_derived)
        unreachable_index = next(i for i, f in enumerate(self.registry["fields"]) if f["classification"] == "out_of_scope_unreachable")
        mutation("REG-021-unreachable-proof", lambda r: r["fields"][unreachable_index].__setitem__("fixture_reachability_status", "reached"))
        diagnostic_index = next(i for i, f in enumerate(self.registry["fields"]) if f["classification"] == "diagnostic")
        mutation("REG-022-diagnostic-consumed", lambda r: r["fields"][diagnostic_index].__setitem__("consumed_by_simulation", True))
        numeric_index = next(i for i, f in enumerate(self.registry["fields"]) if f["width_bits"] == 16 and int(f["sample_logical_value"][0] if isinstance(f["sample_logical_value"], list) else f["sample_logical_value"]) != 0)
        mutation("REG-023-byte-length", lambda r: r["fields"][numeric_index].__setitem__("sample_encoded_hex", "00"))
        def wrong_endian(r):
            sample = r["fields"][numeric_index]["sample_encoded_hex"]
            r["fields"][numeric_index]["sample_encoded_hex"] = bytes.fromhex(sample)[::-1].hex()
        mutation("REG-024-byte-order", wrong_endian)

        for label, mutant in mutations:
            with self.subTest(label=label):
                self.assert_registry_rejected(mutant)

    def test_P005_REG_025_regeneration_is_byte_identical(self) -> None:
        before = REGISTRY_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            subprocess.run([sys.executable, str(DEV / "generate_field_schema.py"), "--artifact-root", str(artifact_root)], cwd=ROOT, check=True)
            generated = artifact_root / "parity"
            self.assertEqual(before, (generated / "schema/fields-v1.json").read_bytes())
            self.assertEqual((ROOT / "parity/schema/fields-v1.sha256").read_bytes(), (generated / "schema/fields-v1.sha256").read_bytes())
            self.assertEqual((ROOT / "parity/schema/projection-plan-v1.json").read_bytes(), (generated / "schema/projection-plan-v1.json").read_bytes())
            self.assertEqual((ROOT / "parity/include/openttd_rl_parity/field_schema.h").read_bytes(), (generated / "include/openttd_rl_parity/field_schema.h").read_bytes())
            self.assertEqual((ROOT / "parity/src/field_schema.c").read_bytes(), (generated / "src/field_schema.c").read_bytes())
        digest_line = (REGISTRY_PATH.parent / "fields-v1.sha256").read_text(encoding="ascii").split()[0]
        self.assertEqual(digest_line, hashlib.sha256(before.rstrip(b"\n")).hexdigest())

    def test_projection_plan_is_generated_from_registry_authority(self) -> None:
        plan = json.loads((ROOT / "parity/schema/projection-plan-v1.json").read_text(encoding="utf-8"))
        expected = [field for field in self.registry["fields"] if field["classification"] == "authoritative_full"]
        self.assertEqual(plan["field_schema_sha256"], hashlib.sha256(canonical_bytes(self.registry)).hexdigest())
        self.assertEqual(plan["authoritative_field_count"], len(expected))
        self.assertEqual([row["field_id"] for row in plan["ordered_authoritative_fields"]], [field["field_id"] for field in expected])
        self.assertTrue(all(row["native_member_expression"] for row in plan["ordered_authoritative_fields"]))

    def test_source_files_symbols_and_diagnostic_lines(self) -> None:
        for field in self.registry["fields"]:
            with self.subTest(field=field["field_id"]):
                source = UPSTREAM / field["source_file"]
                self.assertTrue(source.is_file())
                lines = source.read_text(encoding="utf-8").splitlines()
                self.assertLessEqual(field["source_line_diagnostic"], len(lines))
                self.assertIn(field["source_symbol"], lines[field["source_line_diagnostic"] - 1])

    def test_source_policy_and_cache_anchors(self) -> None:
        text = REGISTRY_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/master/", text)
        for field in self.registry["fields"]:
            self.assertEqual(field["source_commit"], "29f808ef0022064e6d9a83c8476d1e0f4686af86")
            self.assertGreaterEqual(len(field["reached_call_path"]), 8)
            if field["cache_classification"] == "authoritative_cache":
                self.assertNotEqual(field["cache_invalidation_trigger"], "not_applicable")

    def test_P005_SRC_comment_or_nonfirst_locator_is_rejected(self) -> None:
        mutant = copy.deepcopy(self.registry)
        field = mutant["fields"][0]
        field["source_file"] = "src/core/kdtree.hpp"
        field["source_symbol"] = "Kdtree"
        field["source_line_diagnostic"] = 405  # Documentation comment, not code.
        self.assert_registry_rejected(mutant)

    def test_P005_generated_C17_registry_agrees(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "check.c"
            binary = Path(directory) / "check"
            source.write_text(
                '#include "openttd_rl_parity/field_schema.h"\n'
                '#include <string.h>\n'
                'int main(void) { const otrl_field_meta *m = otrl_field_lookup(UINT32_C(1000)); '
                'if (m == NULL || m->width_bits != 64U || strcmp(m->path, "time.tick_counter") != 0) return 1; '
                'if (m->source_anchor == NULL || m->cache_class == NULL) return 2; '
                'if (otrl_field_lookup(UINT32_C(0)) != NULL) return 3; '
                'if (otrl_field_registry_count() < 500U || otrl_field_authoritative_count() == 0U) return 4; '
                'if (otrl_field_registry_at(0U) == NULL || otrl_field_registry_at(0U)->field_id != UINT32_C(1)) return 5; '
                'if (otrl_field_registry_at(otrl_field_registry_count()) != NULL) return 6; '
                'return 0; }\n', encoding="utf-8")
            subprocess.run([
                "gcc", "-std=c17", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                "-I", str(ROOT / "parity/include"), str(source), str(ROOT / "parity/src/field_schema.c"), "-o", str(binary)
            ], check=True)
            subprocess.run([str(binary)], check=True)

    def make_projection(self) -> dict:
        return build_sample_projection(self.registry)

    def assert_projection_rejected(self, projection: dict, registry: dict | None = None) -> None:
        handle = dump_temp(projection)
        self.addCleanup(lambda: os.unlink(handle.name))
        with self.assertRaises(RegistryError):
            validate_projection(Path(handle.name), self.registry if registry is None else registry)

    def test_P005_AGR_001_complete_projection(self) -> None:
        projection = self.make_projection()
        handle = dump_temp(projection)
        self.addCleanup(lambda: os.unlink(handle.name))
        validate_projection(Path(handle.name), self.registry)

    def test_projection_structural_mutants_have_explicit_case_ids(self) -> None:
        base = self.make_projection()
        by_id = {record["field_id"]: record for record in base["fields"]}
        cases = []
        p = copy.deepcopy(base); p["fields"].append({"field_id": 4294967295, "value_type": 1, "element_count": 1, "encoded_hex": "00"}); cases.append(("unknown", p))
        for field_id in (1002, 1030, 3010, 4003, 9003):
            p = copy.deepcopy(base); p["fields"] = [r for r in p["fields"] if r["field_id"] != field_id]; cases.append((f"omit-{field_id}", p))
        p = copy.deepcopy(base); by = {r["field_id"]: r for r in p["fields"]}; by[3010]["element_count"] = 4095; by[3010]["encoded_hex"] = "00" * 4095; cases.append(("fixed-count", p))
        p = copy.deepcopy(base); p["fields"][0]["value_type"] = 12; cases.append(("wrong-type", p))
        p = copy.deepcopy(base); rec = next(r for r in p["fields"] if self.by_id[r["field_id"]]["width_bits"] == 32); rec["encoded_hex"] += "00000000"; cases.append(("host-size", p))
        p = copy.deepcopy(base); rec = next(r for r in p["fields"] if r["field_id"] == 1); rec["value_type"] = 9; cases.append(("raw-enum", p))
        p = copy.deepcopy(base); rec = next(r for r in p["fields"] if r["field_id"] == 4000); rec["encoded_hex"] = "01000000"; cases.append(("owner-count", p))
        p = copy.deepcopy(base); p["field_schema_sha256"] = "0" * 64; cases.append(("identity", p))
        for label, projection in cases:
            with self.subTest(label=label):
                self.assert_projection_rejected(projection)

    def test_P005_AGR_015_field_mutation_is_exactly_observable(self) -> None:
        left = self.make_projection()
        right = copy.deepcopy(left)
        right["fields"][0]["encoded_hex"] = "00"
        self.assertNotEqual(left["fields"], right["fields"])

    def test_nested_partitions_and_count_sources(self) -> None:
        required_offsets = {
            "company.road_unit_word_offsets": "company.road_unit_word_count_total",
            "industry.produced_slot_offsets": "industry.produced_slot_count",
            "industry.accepted_history_offsets": "industry.accepted_history_cell_count",
            "station.catchment_bit_offsets": "station.catchment_bit_count",
            "station.goods.packet_offsets": "station.goods.packet_ref_count",
            "station.goods.flow_owner_offsets": "station.goods.flow_owner_count",
            "station.goods.flow_share_offsets": "station.goods.flow_share_count",
            "vehicle.cargo_packet_offsets": "vehicle.cargo_packet_ref_count",
            "road_vehicle.path_offsets": "road_vehicle.path_element_count",
            "town.supplied_history_offsets": "town.supplied_history_cell_count",
            "town.accepted_history_offsets": "town.accepted_history_cell_count",
        }
        for path, target in required_offsets.items():
            with self.subTest(path=path):
                field = self.by_path[path]
                self.assertEqual(field["shape"], "dynamic_array")
                self.assertEqual(field["value_type"], "u32")
                self.assertEqual(field["offset_target_count_field"], target)
                self.assertEqual(self.by_path[field["count_source_field"]]["shape"], "scalar")
        self.assertEqual(self.by_path["station.goods.entry_count"]["shape"], "scalar")
        self.assertEqual(self.by_path["engine.road_engine_ids"]["count_source_field"], "engine.road_engine_count")
        self.assertEqual(self.by_path["industry.item.accepted_history_presence"]["count_source_field"], "industry.accepted_slot_count")
        for prefix in ("company", "industry", "station", "road_stop", "vehicle", "order_list", "cargo_packet", "town", "depot", "engine", "cargo_payment", "subsidy", "linkgraph", "linkgraph_job"):
            bitmap = self.by_path[f"{prefix}.pool.occupancy_bitmap"]
            self.assertEqual(bitmap["value_type"], "u64")
            self.assertEqual(bitmap["shape"], "dynamic_array")
            self.assertEqual(bitmap["count_source_field"], f"{prefix}.pool.bitmap_word_count")
            self.assertEqual(self.by_path[f"{prefix}.pool.native_free_list"]["classification"], "out_of_scope_unreachable")

    def test_reached_state_families_and_native_metadata_regressions(self) -> None:
        expected_authoritative = {
            "settings.vehicle.smoke_amount",
            "map.animated_tiles",
            "industry.builder.wanted_industries",
            "industry.builder.wait_counts",
            "effect_vehicle.item.ids",
            "effect_vehicle.item.current_sprite_id",
            "station.goods.packet_map_next_hop_keys",
            "station.item.industries_near_distances",
            "road_stop.item.entries_present",
            "order_list.order_offsets",
            "cache.town_kdtree.node_elements",
            "cache.station_kdtree.free_indices",
            "linkgraph.schedule_graph_ids",
            "linkgraph_job.item.settings.recalc_interval",
            "linkgraph_job.graph.edge_travel_time_sums",
        }
        for path in expected_authoritative:
            with self.subTest(path=path):
                self.assertEqual(self.by_path[path]["classification"], "authoritative_full")

        for prefix in ("cache.town_kdtree", "cache.station_kdtree"):
            self.assertEqual(self.by_path[f"{prefix}.node_left_indices"]["null_sentinel"], 0xFFFFFFFFFFFFFFFF)
            self.assertEqual(self.by_path[f"{prefix}.node_right_indices"]["null_sentinel"], 0xFFFFFFFFFFFFFFFF)
            self.assertEqual(self.by_path[f"{prefix}.root_index"]["null_sentinel"], 0xFFFFFFFFFFFFFFFF)
            self.assertEqual(self.by_path[f"{prefix}.free_indices"]["canonical_element_order"],
                             "native free_list order from front to back; the last element is reused first")

        self.assertEqual(self.by_path["linkgraph.node.edge_destination"]["width_bits"], 16)
        self.assertEqual(self.by_path["linkgraph.node.edge_destination"]["null_sentinel"], 0xFFFF)
        self.assertEqual(self.by_path["linkgraph_job.graph.edge_destination_nodes"]["null_sentinel"], 0xFFFF)
        self.assertEqual(self.by_path["linkgraph_job.graph.node_tiles"]["null_sentinel"], 0xFFFFFFFF)
        self.assertEqual(self.by_path["linkgraph_job.item.graph.cargo_type"]["source_symbol"], "CargoType cargo = INVALID_CARGO;")
        self.assertEqual(self.by_path["linkgraph_job.item.graph.cargo_type"]["null_sentinel"], 0xFF)
        self.assertEqual(self.by_path["linkgraph_job.item.join_date"]["null_sentinel"], -1)
        self.assertEqual(self.by_path["linkgraph_job.graph.node_supply"]["maximum_capacity"], 128)
        self.assertEqual(self.by_path["linkgraph_job.graph.edge_capacities"]["maximum_capacity"], 256)

        self.assertEqual(self.by_path["station.item.string_id"]["width_bits"], 32)
        self.assertEqual(self.by_path["vehicle.item.status"]["width_bits"], 8)
        self.assertEqual(self.by_path["vehicle.item.waiting_random_triggers"]["width_bits"], 8)
        self.assertEqual(self.by_path["engine.item.flags"]["width_bits"], 8)
        self.assertEqual(self.by_path["linkgraph.item.edge_travel_times"]["width_bits"], 64)

    def test_offset_projection_mutants(self) -> None:
        base = self.make_projection()
        path = "vehicle.cargo_packet_offsets"
        field_id = self.by_path[path]["field_id"]
        target_id = self.by_path["vehicle.cargo_packet_ref_count"]["field_id"]
        owner_count_id = self.by_path["vehicle.owner_offset_count"]["field_id"]

        valid = copy.deepcopy(base)
        by = {record["field_id"]: record for record in valid["fields"]}
        by[target_id]["encoded_hex"] = "02000000"
        by[owner_count_id]["encoded_hex"] = "03000000"
        by[field_id]["element_count"] = 3
        by[field_id]["encoded_hex"] = "000000000100000002000000"
        packet_id = self.by_path["vehicle.item.cargo_packet_ids"]["field_id"]
        by[packet_id]["element_count"] = 2
        by[packet_id]["encoded_hex"] = "0000000000000000"
        handle = dump_temp(valid); self.addCleanup(lambda: os.unlink(handle.name))
        validate_projection(Path(handle.name), self.registry)

        mutants = []
        p = copy.deepcopy(valid); next(r for r in p["fields"] if r["field_id"] == field_id)["encoded_hex"] = "010000000100000002000000"; mutants.append(p)
        p = copy.deepcopy(valid); next(r for r in p["fields"] if r["field_id"] == field_id)["encoded_hex"] = "000000000200000001000000"; mutants.append(p)
        p = copy.deepcopy(valid); next(r for r in p["fields"] if r["field_id"] == field_id)["encoded_hex"] = "000000000100000003000000"; mutants.append(p)
        for mutant in mutants:
            self.assert_projection_rejected(mutant)

    def test_conservative_cache_policy(self) -> None:
        caches = [f for f in self.registry["fields"] if f["cache_classification"] != "not_cache"]
        self.assertTrue(caches)
        self.assertFalse([f for f in caches if f["cache_classification"] == "derived_rebuild"])
        for field in caches:
            self.assertIn(field["cache_classification"], {"authoritative_cache", "diagnostic_cache", "unreachable_cache"})
            self.assertIsNone(field["cache_evidence_sha256"])
        for path in ("road_vehicle.item.path_trackdirs", "road_vehicle.item.path_tiles", "vehicle.item.cache.weight", "station.item.catchment_tiles"):
            self.assertEqual(self.by_path[path]["classification"], "authoritative_full")
        self.assertEqual(self.by_path["route.native_topology_revision_counter"]["classification"], "out_of_scope_unreachable")

    def test_fixture_rng_and_settings_manifest_agreement(self) -> None:
        expected_rng = {
            "rng.gameplay.state0": 1536594464,
            "rng.gameplay.state1": 1985458814,
            "rng.interactive.state0": 1230128689,
            "rng.interactive.state1": 1230128689,
        }
        for path, value in expected_rng.items():
            self.assertEqual(self.by_path[path]["sample_logical_value"], value)
            self.assertIn("pre-save", self.by_path[path]["sample_origin"])
        log = (ROOT / "oracle/fixtures/road_freight_v1/builder/evidence/run-a.stderr.log").read_text(encoding="utf-8")
        self.assertIn("random=5b969220:7657b27e", log)
        self.assertIn("interactive=49524631:49524631", log)

        settings_path = ROOT / "oracle/fixtures/road_freight_v1/settings.normalized.json"
        self.assertEqual(hashlib.sha256(settings_path.read_bytes()).hexdigest(), "6def2c6df29992747165e3b2c090561893d0fe4d3a80c5833f871b3ed7e584f2")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        behavior = {entry["id"]: int(entry["value"]) if isinstance(entry["value"], bool) else entry["value"] for entry in settings["settings"] if entry["authority"] == "behavior"}
        global_registry = {field["path"][len("settings."):]: field["sample_logical_value"] for field in self.registry["fields"] if field["path"].startswith("settings.") and field["field_id"] != 2099}
        self.assertEqual(global_registry, {key: value for key, value in behavior.items() if not key.startswith("vehicle.servint_")})
        self.assertEqual(self.by_path["company.item.settings.vehicle.servint_ispercent"]["sample_logical_value"][0], behavior["vehicle.servint_ispercent"])
        self.assertEqual(self.by_path["company.item.settings.vehicle.servint_roadveh"]["sample_logical_value"][0], behavior["vehicle.servint_roadveh"])
        manifest = json.loads((ROOT / "oracle/fixtures/road_freight_v1/fixture.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["normalized_settings"]["sha256"], "6def2c6df29992747165e3b2c090561893d0fe4d3a80c5833f871b3ed7e584f2")
        self.assertEqual(manifest["normalized_settings"]["authoritative_identity_sha256"], "fc5667d5b48a1ee760649150762ebae2f7dd43f0ed185b5671a1d632b8f7651c")


class InvariantTest(unittest.TestCase):
    def test_pool_bitmap_words_fragmentation_and_next_allocation(self) -> None:
        high_padding = ((1 << 64) - 1) ^ 0xFF
        good = {"capacity": 8, "storage_capacity": 8, "first_free": 1, "first_unused": 5,
                "occupied_count": 3, "bitmap_word_count": 1,
                "bitmap_words": [high_padding | 0b00010101], "next_id": 1}
        validate_pool(good, [0, 2])
        mutants = []
        for change in (
            {"occupied_count": 2}, {"bitmap_word_count": 2}, {"bitmap_words": [0b00010101]},
            {"next_id": 3}, {"first_unused": 9}, {"first_free": 6},
        ):
            value = copy.deepcopy(good); value.update(change); mutants.append(value)
        for value in mutants:
            with self.assertRaises(InvariantError): validate_pool(value)
        with self.assertRaises(InvariantError): validate_pool(good, [7])

    def test_cargo_conservation_order_and_ledger_mutants(self) -> None:
        good = {
            "produced": 12, "delivered": 3, "destroyed": 0,
            "packets": [
                {"id": 5, "amount": 4, "source_id": 0, "source_type": 1, "periods_in_transit": 2},
                {"id": 7, "amount": 5, "source_id": 0, "source_type": 1, "periods_in_transit": 1},
            ],
            "containers": {"station:0": [5], "vehicle:0": [7]},
            "ledger_delivery_units": 3,
        }
        validate_cargo(good)
        for mutate in ("drop", "duplicate", "provenance", "order", "ledger"):
            value = copy.deepcopy(good)
            if mutate == "drop": value["packets"][0]["amount"] -= 1
            if mutate == "duplicate": value["containers"]["vehicle:0"].append(5)
            if mutate == "provenance": value["packets"][0]["source_id"] = -1
            if mutate == "order": value["containers"] = {"station:0": [7], "vehicle:0": [5, 7]}
            if mutate == "ledger": value["ledger_delivery_units"] = 2
            with self.subTest(mutate=mutate), self.assertRaises(InvariantError): validate_cargo(value)
        validate_ledger(100, 87, [-10, -3])
        with self.assertRaises(InvariantError): validate_ledger(100, 86, [-10, -3])

    def test_timer_and_rng_mutations(self) -> None:
        initial = {"tick": 0, "calendar_date": 712223, "calendar_fraction": 0, "economy_date": 712223, "economy_fraction": 0,
                   "rng0": 1536594464, "rng1": 1985458814, "interactive0": 1230128689, "interactive1": 1230128689}
        validate_timer_rng(initial, initial.copy(), 0)
        tick = initial.copy(); tick["tick"] = 1; tick["calendar_fraction"] = 1; tick["economy_fraction"] = 1
        validate_timer_rng(initial, tick, 1)
        perturbed = initial.copy(); perturbed["rng0"] ^= 1
        with self.assertRaises(InvariantError): validate_timer_rng(initial, perturbed, 0)
        skipped = tick.copy(); skipped["tick"] = 2
        with self.assertRaises(InvariantError): validate_timer_rng(initial, skipped, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
