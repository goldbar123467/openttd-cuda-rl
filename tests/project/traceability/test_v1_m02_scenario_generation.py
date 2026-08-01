#!/usr/bin/env python3
"""Corpus, seed partition, generation, identity, and rejection tests for M02."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import generate_m02_scenario


class V1M02ScenarioGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract, cls.corpus, cls.ledger = generate_m02_scenario.load_and_validate(
            cls.root / "config/v1/m02-scenario-contract.json",
            cls.root / "docs/project/schema/v1-m02-scenario-contract.schema.json",
            cls.root / "config/v1/m02-scenario-corpus.json",
            cls.root / "docs/project/schema/v1-m02-scenario-corpus.schema.json",
            cls.root / "config/v1/m02-seed-ledger.json",
            cls.root / "docs/project/schema/v1-m02-seed-ledger.schema.json",
        )
        cls.instance_schema = (
            cls.root / "docs/project/schema/v1-m02-scenario-instance.schema.json"
        )

    def test_corpus_and_ledger_identities_are_frozen(self) -> None:
        self.assertEqual(
            self.corpus["identity"]["corpus_sha256"],
            "07898d94a56fd080c9cea57dbdf90384e1f0f269e360fb35423de16bc89d2e14",
        )
        self.assertEqual(
            self.ledger["identity"]["ledger_sha256"],
            "fcfdb820abb6db783df412d6496f68ce41bfd3def630ced637fe1d00dbbcd8ed",
        )
        self.assertEqual(
            self.corpus["identity"]["schema_sha256"],
            "1760ae8c53c15d399e6c6284c8152d7dc2919a9e3d2b21a3e740506b45643d3a",
        )
        self.assertEqual(
            self.ledger["identity"]["schema_sha256"],
            "da2ae845ccdc349e0cb31e92a14c6236773ccff194901abcb301b5c3e480f3da",
        )

    def test_seed_sets_are_pairwise_disjoint_and_final_is_withheld(self) -> None:
        by_split: dict[str, set[int]] = {}
        for entry in self.ledger["entries"]:
            by_split.setdefault(entry["split"], set()).add(entry["seed"])
            self.assertEqual(
                entry["trainer_visible"],
                entry["split"] != "final-evaluation",
            )
        self.assertEqual({name: len(values) for name, values in by_split.items()}, {
            "development": 2,
            "final-evaluation": 2,
            "training": 4,
        })
        self.assertFalse(by_split["training"] & by_split["development"])
        self.assertFalse(by_split["training"] & by_split["final-evaluation"])
        self.assertFalse(by_split["development"] & by_split["final-evaluation"])

    def test_all_templates_pass_geometry_without_retry(self) -> None:
        for template in self.corpus["templates"]:
            with self.subTest(template=template["template_id"]):
                generate_m02_scenario.validate_template(template, self.contract)
        self.assertEqual(self.corpus["generation"]["implicit_retries"], 0)

    def test_all_scenario_identities_are_exact_and_distinct(self) -> None:
        expected = {
            "m02-template-01": "ab38d1a1115c0f86de43c53a9b360bb6432fe8bf3e3d7d03d5dbe3ab59693d26",
            "m02-template-02": "13b3feacd7ad108eeba4c27219512e0ca72c7b2b7a19a7d734e2b44d3e261698",
            "m02-template-03": "f91d2bee8ff52b220e8536fc1840ec7fd4ae35f0994c0bb83d3c876958b2398c",
            "m02-template-04": "c55e8987d75c62af91a2d48fde7aec9524e0a6c23ba718b9bc3acfa2440f4b47",
            "m02-template-05": "63b678e4f54c34f6e83ce4d89602d03d5ea74aec36f21cf62f8869e00cdd5795",
            "m02-template-06": "e33f83bf36275466a65e7824a89c2938492c8fde7f1d13c1573ed61d7628cbcb",
            "m02-template-07": "d3b7b254e602164407c66181b78086358d645d1bbf0884c6a740ff402814d141",
            "m02-template-08": "8577bacf18df6b86c19fc9f6218ef39d4a3f1f5a7f9ffe7133373d085b87e99b",
        }
        actual: dict[str, str] = {}
        for template in self.corpus["templates"]:
            instance = generate_m02_scenario.build_instance(
                self.contract,
                self.corpus,
                self.ledger,
                template,
                self.instance_schema,
            )
            actual[template["template_id"]] = instance["identity"]["scenario_sha256"]
            repeated = generate_m02_scenario.build_instance(
                self.contract,
                self.corpus,
                self.ledger,
                copy.deepcopy(template),
                self.instance_schema,
            )
            self.assertEqual(
                generate_m02_scenario.canonical_bytes(instance),
                generate_m02_scenario.canonical_bytes(repeated),
            )
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual.values())), 8)

    def test_geometry_mutations_have_explicit_predicates(self) -> None:
        diagonal = copy.deepcopy(self.corpus["templates"][0])
        diagonal["road_waypoints"][1]["y"] += 1
        with self.assertRaisesRegex(
            generate_m02_scenario.M02ScenarioGenerationError,
            "predicate=route-segment-not-axis-aligned",
        ):
            generate_m02_scenario.validate_template(diagonal, self.contract)

        stop = copy.deepcopy(self.corpus["templates"][0])
        stop["bus_stops"][0]["y"] += 1
        with self.assertRaisesRegex(
            generate_m02_scenario.M02ScenarioGenerationError,
            "predicate=stop-off-route",
        ):
            generate_m02_scenario.validate_template(stop, self.contract)

        depot = copy.deepcopy(self.corpus["templates"][0])
        depot["road_depot"]["y"] = 20
        with self.assertRaisesRegex(
            generate_m02_scenario.M02ScenarioGenerationError,
            "predicate=depot-not-adjacent-to-route",
        ):
            generate_m02_scenario.validate_template(depot, self.contract)

    def test_cli_rejects_split_drift_final_exposure_unknown_seed_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw)
            common = ["--root", str(self.root), "--output", str(temporary / "scenario.json")]
            self.assertEqual(
                generate_m02_scenario.main(
                    [
                        *common,
                        "--template-id",
                        "m02-template-01",
                        "--declared-split",
                        "development",
                    ]
                ),
                1,
            )
            self.assertEqual(
                generate_m02_scenario.main(
                    [
                        *common,
                        "--template-id",
                        "m02-template-07",
                        "--declared-split",
                        "final-evaluation",
                    ]
                ),
                1,
            )
            self.assertEqual(
                generate_m02_scenario.main(
                    [*common, "--seed", "1", "--declared-split", "training"]
                ),
                1,
            )
            self.assertEqual(
                generate_m02_scenario.main(
                    [
                        *common,
                        "--template-id",
                        "m02-template-01",
                        "--declared-split",
                        "training",
                    ]
                ),
                0,
            )
            first = (temporary / "scenario.json").read_bytes()
            self.assertEqual(
                generate_m02_scenario.main(
                    [
                        *common,
                        "--template-id",
                        "m02-template-01",
                        "--declared-split",
                        "training",
                    ]
                ),
                1,
            )
            self.assertEqual((temporary / "scenario.json").read_bytes(), first)

    def test_seed_overlap_mutation_is_rejected_before_generation(self) -> None:
        mutant = copy.deepcopy(self.ledger)
        mutant["entries"][4]["seed"] = mutant["entries"][0]["seed"]
        with self.assertRaisesRegex(
            generate_m02_scenario.M02ScenarioGenerationError,
            "predicate=seed-partition-overlap",
        ):
            generate_m02_scenario.validate_seed_entries(
                mutant["entries"],
                self.corpus["templates"],
            )

    def test_final_evaluation_requires_explicit_authority_and_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            first = pathlib.Path(raw) / "first.json"
            second = pathlib.Path(raw) / "second.json"
            base = [
                "--root",
                str(self.root),
                "--template-id",
                "m02-template-07",
                "--declared-split",
                "final-evaluation",
                "--allow-final-evaluation",
            ]
            self.assertEqual(
                generate_m02_scenario.main([*base, "--output", str(first)]),
                0,
            )
            self.assertEqual(
                generate_m02_scenario.main([*base, "--output", str(second)]),
                0,
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())
            value = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(value["split"], "final-evaluation")


if __name__ == "__main__":
    unittest.main()
