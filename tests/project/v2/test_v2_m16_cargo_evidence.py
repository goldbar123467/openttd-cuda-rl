#!/usr/bin/env python3
"""Mutation and relocated-live tests for complete native M16 cargo evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
import validate_m16_cargo_evidence as validator


def _m16_probe(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record["metrics"]
    if record["probe"] == "catalog":
        return {"status": "CATALOG_ONLY"}
    if record["probe"] in ("single-leg", "subsidy"):
        multiplier = 2 if record["probe"] == "subsidy" else 1
        return {
            "accounting": {
                "company_income_delta": metrics["income"],
                "delivered_delta": metrics["delivered"],
                "payment_events": [{
                    "base_income": metrics["income"] // multiplier,
                    "cargo": record["cargo"],
                    "final_income": metrics["income"],
                    "transfer": False,
                }],
            },
            "ticks": metrics["ticks"],
            "vehicle": {"cargo": record["cargo"], "refit_capacity": 8},
        }
    if record["probe"] == "coordination":
        passenger_income = metrics["income"] // 2
        return {
            "accounting": {
                "company_income_delta": metrics["income"],
                "delivered_mail": 8,
                "delivered_passengers": metrics["delivered"] - 8,
                "payment_events": [
                    {"cargo": "PASS", "final_income": passenger_income},
                    {"cargo": "MAIL", "final_income": metrics["income"] - passenger_income},
                ],
            },
            "shared_stations": True,
            "ticks": metrics["ticks"],
        }
    return {
        "final": {
            "company_income_delta": metrics["income"],
            "delivered_delta": metrics["delivered"],
            "ticks": metrics["ticks"] - 1,
        },
        "first_leg": {"company_income_delta": 0, "ticks": 1, "transfer_waiting": 8},
        "payment_events": [
            {"final_income": 0, "transfer": True},
            {"final_income": metrics["income"], "transfer": False},
        ],
        "single_final_payment": True,
    }


def _m17_probe(record: dict[str, Any]) -> dict[str, Any]:
    probe, metrics = record["probe"], record["metrics"]
    if probe == "catalog":
        return {"status": "CATALOG_ONLY"}
    if probe == "construction":
        return {
            "commands": [
                {"command": "CMD_BUILD_RAIL_INVALID_TYPE", "status": "REJECTED"},
                {"command": "CMD_REMOVE_RAIL_FOREIGN_OWNER", "status": "REJECTED"},
                {"command": "CMD_REMOVE_FROM_RAIL_STATION", "status": "SUCCESS"},
            ],
            "crossing": True,
            "foreign_owner_rejected": True,
            "junction": True,
            "observations": {"junction_track_bits": 37, "level_crossing": True, "rail_crossing_track_bits": 3, "slope": 8},
            "orientations": [{"name": name, "removed": True} for name in ("x", "y", "upper", "lower", "left", "right")],
            "station": {"catchment_radius": 4, "footprint": {"height": 1, "tile": 2056, "width": 2}, "platform_length": 2, "removed_roundtrip": True},
            "waypoint_roundtrip": True,
        }
    if probe == "signals":
        names = ("block", "entry", "exit", "combo", "path", "path-one-way")
        signals = [
            {"name": name, "present_bits": (4, 8, 12)[(index + variant) % 3], "type": index, "variant": variant}
            for index, name in enumerate(names)
            for variant in (0, 1)
        ]
        return {
            "commands": [{"command": "CMD_REMOVE_SIGNAL", "status": "SUCCESS"} for _ in signals],
            "reservation": {"duplicate_rejected": True, "released": True, "reserved": True},
            "signals": signals,
        }
    if probe == "lifecycle":
        names = ("CMD_CLONE_VEHICLE", "CMD_SET_AUTOREPLACE", "CMD_AUTOREPLACE_VEHICLE", "CMD_CLEAR_AUTOREPLACE", "CMD_SELL_VEHICLE")
        return {
            "clone_and_sale": True,
            "commands": [{"command": name, "status": "SUCCESS"} for name in names],
            "consist_capacity": 30,
            "order_flags": {"invalid_rejected": True, "load": True, "non_stop": True, "stop_location": True, "unload": True},
            "orders": 2,
            "replacement": {"configured": True, "executed": True, "from_engine": 1, "to_engine": 2},
            "safety_fixture": {"collision_negative": True, "collision_positive": True, "lost_negative": True, "lost_positive": True},
            "save_load": {"bytes": 64, "restored": True},
            "service_interval": 120,
            "timetable": {"speed": 96, "travel": 256, "wait": 64},
        }
    if probe in ("passenger", "freight"):
        return {
            "accounting": {"delivered": metrics["delivered"], "income": metrics["income"]},
            "safety": {"crashed": False, "maximum_wait": 1, "stuck": False},
            "ticks": metrics["ticks"],
        }
    return {
        "delivered": metrics["delivered"],
        "income": metrics["income"],
        "junction_connectors": 1,
        "maximum_wait": 1,
        "shared_destination": True,
        "shared_physical_network": True,
        "shared_station": False,
        "signals": 2,
        "terminal_stations": 3,
        "ticks": metrics["ticks"],
        "trains": 2,
        "unexplained_collision": False,
        "unresolved_deadlock": False,
    }


def _m18_probe(record: dict[str, Any]) -> dict[str, Any]:
    probe, metrics = record["probe"], record["metrics"]
    if probe == "catalog":
        return {"status": "CATALOG_ONLY"}
    if probe == "construction":
        commands = ("CMD_BUILD_LOCK", "CMD_BUILD_AQUEDUCT", "CMD_BUILD_DOCK", "CMD_BUILD_SHIP_DEPOT", "CMD_BUILD_BUOY")
        return {
            "commands": [
                *({"command": name, "status": "SUCCESS"} for name in commands),
                {"command": "CMD_BUILD_CANAL_INVALID_CLASS", "status": "REJECTED"},
                {"command": "CMD_REMOVE_FOREIGN_CANAL", "status": "REJECTED"},
            ],
            "distant_dock_join": True,
            "invalid_class_rejected": True,
            "removal_roundtrip": {"aqueduct": True, "buoy": True, "canal": True, "depot": True, "dock": True, "lock": True},
            "water_classes": ["canal", "river", "sea"],
        }
    if probe == "connectivity":
        return {
            "after_cut": {"engine": False, "independent": False},
            "before_cut": {"engine": True, "independent": True},
            "reconnected": True,
            "start_patch": {"label": 1},
            "start_region": {"x": 0, "y": 2},
        }
    if probe == "lifecycle":
        return {
            "clone_and_sale": True,
            "order_flags": {"invalid_rejected": True, "load": True, "unload": True},
            "replacement": {"configured": True, "executed": True, "from_engine": 1, "to_engine": 2},
            "safety_fixture": {"crashed": False, "lost_cleared": True, "lost_positive": True},
            "save_load": {"bytes": 64, "restored": True},
            "service_interval": 120,
            "timetable": {"speed": 48, "travel": 256, "wait": 64},
        }
    if probe in ("natural", "constructed"):
        route = {"aqueduct_traversed": False, "constructed": False, "lock_traversed": False, "water_class": "sea" if record["cargo"] == "PASS" else "river"}
        if probe == "constructed":
            route = {"aqueduct_traversed": True, "constructed": True, "lock_traversed": True, "water_class": "canal"}
        return {
            "accounting": {"delivered": metrics["delivered"], "income": metrics["income"], "payment_events": [{"transfer": False}]},
            "route": route,
            "ship": {"lost": False},
            "ticks": metrics["ticks"],
        }
    if probe == "transfer":
        return {
            "final": {"company_income_delta": metrics["income"], "delivered": metrics["delivered"], "payment_count": 1, "ticks": metrics["ticks"]},
            "first_leg": {"cash_delta": 0, "transferred": metrics["delivered"]},
            "payment_events": [{"transfer": True}, {"transfer": False}],
            "shared_road_dock_station": True,
        }
    return {
        "delivery": {"delivered": metrics["delivered"], "income": metrics["income"]},
        "disconnected": True,
        "lost_detected": True,
        "reconnected": True,
        "recovery_ticks": metrics["ticks"],
        "safe_stopped": True,
    }


def _report_fixture(
    record: dict[str, Any],
    twin_name: str,
    evidence: dict[str, Any],
    logical_set: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    run_id = f"{record['case_id']}-{twin_name}"
    if logical_set == "v2-m16-cargo-matrix-a":
        actual_classes = evidence["aggregate"]["actual_cargo_classes"]
        return {
            "cargo_catalog": [
                {"classes": actual_classes if index == 0 else [], "label": label}
                for index, label in enumerate(contract["climates"][record["climate"]])
            ],
            "climate": record["climate"],
            "executable_sha256": evidence["executable_sha256"],
            "industry_graph": {
                "industries": [{"id": 0}],
                "production_transitions": [
                    {"accepted": f"A{index}", "industry_id": index, "produced": f"P{index}"}
                    for index in range(6)
                ],
            },
            "lifecycle_and_economy": {
                "cargo_distribution": {"manual": True},
                "economy": {"normal": True},
                "industry_closure": {"exact_pool_roundtrip": True},
            },
            "probe": _m16_probe(record),
            "request": {"run_id": run_id},
            "run_id": run_id,
            "schema_version": "openttd-rl-v2-m16-cargo-report-1",
            "status": "PASS",
        }
    if logical_set == "v2-m17-rail-matrix-a":
        return {
            "catalog": {
                "engines": [{"id": index} for index in range(116)],
                "railtypes": [{"id": index} for index in range(4)],
                "signal_types": contract["semantics"]["signal_types"],
                "track_orientations": contract["semantics"]["track_orientations"],
            },
            "executable_sha256": evidence["executable_sha256"],
            "map": {"height": 64, "width": 64},
            "probe": _m17_probe(record),
            "request": {"cargo_label": record["cargo"], "probe": record["probe"], "run_id": run_id, "seed": record["seed"]},
            "run_id": run_id,
            "schema_version": "openttd-rl-v2-m17-rail-report-1",
            "status": "PASS",
        }
    return {
        "catalog": {
            "engines": [{"id": index} for index in range(11)],
            "water_classes": [{"id": 0, "name": "sea"}, {"id": 1, "name": "canal"}, {"id": 2, "name": "river"}],
            "water_region_edge_length": 16,
        },
        "executable_sha256": evidence["executable_sha256"],
        "map": {"height": 64, "width": 64},
        "probe": _m18_probe(record),
        "request": {"cargo_label": record["cargo"], "probe": record["probe"], "run_id": run_id, "seed": record["seed"]},
        "run_id": run_id,
        "schema_version": "openttd-rl-v2-m18-ship-report-1",
        "status": "PASS",
    }


def make_live_evidence_fixture(
    directory: pathlib.Path,
    evidence: dict[str, Any],
    *,
    logical_set: str,
    matrix: Any,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path]:
    value = copy.deepcopy(evidence)
    artifact_set = directory / logical_set
    artifact_set.mkdir(parents=True)
    for record in value["cases"]:
        for twin in record["twins"]:
            path = artifact_set / twin["report_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            report = _report_fixture(record, twin["name"], value, logical_set, contract)
            path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
            twin["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            twin["normalized_sha256"] = hashlib.sha256(matrix.normalized(report)).hexdigest()
    config_path = directory / "evidence.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, artifact_set


class M16CargoEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.contract = validator.load(cls.root / validator.matrix.CONTRACT)
        cls.schema = cls.root / validator.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raised = self.assertRaisesRegex(validator.M16EvidenceError, pattern) if pattern else self.assertRaises((validator.M16EvidenceError, ValueError))
            with raised:
                validator.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_evidence_passes(self) -> None:
        summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual((summary["cases"], summary["runs"], summary["edges"]), (102, 204, 24))

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(validator.matrix, "validate_common", side_effect=AssertionError("unexpected live read")):
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_retained_live_evidence_passes(self) -> None:
        summary = validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary["live"])

    def test_required_live_inputs_are_the_exact_report_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        expected = [
            (twin["report_path"], twin["report_sha256"])
            for record in self.config["cases"]
            for twin in record["twins"]
        ]
        self.assertEqual(len(requirements), 204)
        self.assertEqual(len(set(requirements)), 204)
        self.assertEqual(
            [(item.relative_path, item.expected_sha256) for item in requirements],
            expected,
        )
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m16-cargo-matrix-a"})
        self.assertEqual({item.kind for item in requirements}, {"file"})
        self.assertEqual({item.consumer for item in requirements}, {"m16-cargo-evidence"})

    def test_relocated_live_reports_pass(self) -> None:
        retained = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _ = make_live_evidence_fixture(
                base,
                self.config,
                logical_set="v2-m16-cargo-matrix-a",
                matrix=validator.matrix,
                contract=self.contract,
            )
            summary = validator.validate(
                self.root,
                config_path,
                self.schema,
                artifact_context=ArtifactContext.live(base),
            )
        self.assertTrue(summary["live"])
        self.assertEqual(self.config, retained)

    def test_relocated_live_report_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(
                base,
                self.config,
                logical_set="v2-m16-cargo-matrix-a",
                matrix=validator.matrix,
                contract=self.contract,
            )
            report = artifact_set / self.config["cases"][0]["twins"][0]["report_path"]
            report.write_bytes(report.read_bytes() + b"tamper\n")
            with mock.patch.object(
                validator.matrix,
                "validate_common",
                side_effect=AssertionError("preflight did not run first"),
            ) as common:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    validator.validate(
                        self.root,
                        config_path,
                        self.schema,
                        artifact_context=ArtifactContext.live(base),
                    )
            common.assert_not_called()

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_occurrence_count_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["aggregate"]["climate_occurrences"] = 44
        self.mutation_fails(value)

    def test_case_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][10]["seed"] ^= 1
        self.mutation_fails(value, "metadata")

    def test_vacuous_income_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        target = next(item for item in value["cases"] if item["probe"] == "single-leg")
        target["metrics"]["income"] = 0
        self.mutation_fails(value, "metrics")

    def test_twin_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["twins"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "twin reports differ")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
