#!/usr/bin/env python3
"""Offline mutation tests for the pre-PORT003 PORT-002 fixture contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pathlib
import random
import shutil
import sys
from collections.abc import Callable

from port002_contract import (
    ContractError,
    assert_frozen_settings,
    authoritative_settings_identity,
    canonical_bytes,
    normalized_settings_bytes,
    sha256_bytes,
    sha256_file,
    strict_json,
    validate_fixture_data,
)


class TestFailure(AssertionError):
    pass


class Harness:
    def __init__(self, repository: pathlib.Path, work: pathlib.Path, seed: int) -> None:
        self.repository = repository.resolve()
        self.work = work.resolve()
        self.seed = seed
        self.schema_path = self.repository / "oracle/manifests/schema/fixture.schema.json"
        self.manifest_path = self.repository / "oracle/fixtures/road_freight_v1/fixture.manifest.json"
        self.settings_path = self.repository / "oracle/fixtures/road_freight_v1/settings.normalized.json"
        self.schema = strict_json(self.schema_path)
        self.manifest = strict_json(self.manifest_path)
        self.settings = strict_json(self.settings_path)
        self.schema_digest = sha256_file(self.schema_path)
        self.passed: list[str] = []
        self.counter = 0

    def fresh(self, label: str) -> pathlib.Path:
        self.counter += 1
        path = self.work / f"{self.counter:03d}-{label}"
        path.mkdir(parents=True, exist_ok=False)
        return path

    def final_fixture(self, label: str) -> tuple[dict[str, object], pathlib.Path]:
        root = self.fresh(label)
        shutil.copyfile(self.settings_path, root / "settings.normalized.json")
        save_bytes = b"synthetic PORT002 validator fixture; not an OpenTTD savegame\n"
        (root / "fixture.sav").write_bytes(save_bytes)
        manifest = copy.deepcopy(self.manifest)
        manifest["schema_sha256"] = self.schema_digest
        manifest["review_status"] = "PORT002B_PASS"
        manifest["fixture_bytes"] = {
            "state": "frozen",
            "relative_path": "fixture.sav",
            "sha256": hashlib.sha256(save_bytes).hexdigest(),
            "size_bytes": len(save_bytes),
        }
        manifest["initial_boundary"] = {
            "state": "verified",
            "declared_boundary": "after-load-before-first-scripted-command",
            "tick": 0,
            "calendar_date": 712223,
            "economy_date": 712223,
            "calendar_timer": 0,
            "economy_timer": 0,
            "state_rng": [1, 2],
            "interactive_rng": [3, 4],
        }
        manifest["funding_proof"] = {
            "state": "verified",
            "opening_balance": 10000000,
            "command_cost_total": 5000000,
            "safety_margin": 2500000,
            "cost_evidence": "synthetic semantic-validator test evidence",
        }
        manifest["milestones"] = {
            "state": "verified",
            "first_pickup_tick": 100,
            "first_loading_tick": 101,
            "first_delivery_tick": 500,
            "first_payment_tick": 500,
            "payment_amount": 1000,
        }
        manifest["closure_blockers"] = []
        return manifest, root

    def validate(self, manifest: dict[str, object], root: pathlib.Path) -> None:
        validate_fixture_data(
            manifest,
            self.schema,
            root,
            require_final=True,
            schema_sha256=self.schema_digest,
        )

    def positive(self, label: str) -> None:
        manifest, root = self.final_fixture(label)
        self.validate(manifest, root)

    def review_fixture(self, label: str) -> tuple[dict[str, object], pathlib.Path]:
        root = self.fresh(label)
        shutil.copyfile(self.settings_path, root / "settings.normalized.json")
        shutil.copyfile(self.manifest_path.parent / "fixture.sav", root / "fixture.sav")
        return copy.deepcopy(self.manifest), root

    def mutant(
        self,
        label: str,
        mutate: Callable[[dict[str, object]], None],
        needle: str,
    ) -> None:
        manifest, root = self.final_fixture(label)
        mutate(manifest)
        try:
            self.validate(manifest, root)
        except ContractError as exc:
            if needle not in str(exc):
                raise TestFailure(f"expected failure containing {needle!r}, got: {exc}") from exc
            return
        raise TestFailure("mutated fixture unexpectedly passed")

    def case(self, test_id: str, description: str, function: Callable[[], None]) -> None:
        try:
            function()
        except Exception as exc:
            print(f"not ok {len(self.passed) + 1} - {test_id} {description}")
            print(f"# {type(exc).__name__}: {exc}")
            raise
        self.passed.append(test_id)
        print(f"ok {len(self.passed)} - {test_id} {description}")

    @staticmethod
    def setting_entry(document: dict[str, object], identifier: str) -> dict[str, object]:
        for entry in document["settings"]:
            if entry["id"] == identifier:
                return entry
        raise TestFailure(f"setting not found: {identifier}")

    @staticmethod
    def expect_contract_error(function: Callable[[], object], needle: str) -> None:
        try:
            function()
        except ContractError as exc:
            if needle not in str(exc):
                raise TestFailure(f"expected {needle!r}, got {exc!r}") from exc
            return
        raise TestFailure("expected contract failure")

    def run(self) -> None:
        cases: list[tuple[str, str, Callable[[], None]]] = [
            ("P002-FIX-001", "width equals 64", lambda: self.positive("width")),
            ("P002-FIX-002", "height equals 64", lambda: self.positive("height")),
            (
                "P002-FIX-003",
                "other dimensions fail",
                lambda: (
                    self.mutant("width-63", lambda m: m["world"]["map"].__setitem__("width", 63), "map width must equal 64"),
                    self.mutant("height-65", lambda m: m["world"]["map"].__setitem__("height", 65), "map height must equal 64"),
                ),
            ),
            ("P002-FIX-004", "NewGRF list is empty", lambda: self.positive("newgrf-empty")),
            (
                "P002-FIX-005",
                "one NewGRF fails",
                lambda: self.mutant("newgrf", lambda m: m["content"]["newgrfs"].append("deadbeef"), "fixture schema validation failed"),
            ),
            ("P002-FIX-006", "exactly one human company", lambda: self.positive("human-company")),
            (
                "P002-FIX-007",
                "AI company fails",
                lambda: self.mutant(
                    "ai-company",
                    lambda m: m["companies"].append({"id": 1, "kind": "ai", "name_policy": "generated-default-no-custom-string", "opening_balance": 100000, "opening_loan": 100000, "cheat_state": False}),
                    "exactly human company ID 0",
                ),
            ),
            ("P002-FIX-008", "producer ID and tiles match", lambda: self.positive("producer")),
            ("P002-FIX-009", "acceptor ID and tiles match", lambda: self.positive("acceptor")),
            (
                "P002-FIX-010",
                "cargo incompatibility fails",
                lambda: self.mutant("cargo", lambda m: m["industries"][0].__setitem__("produces", ["wood"]), "cargo incompatibility"),
            ),
            (
                "P002-FIX-011",
                "unavailable vehicle fails",
                lambda: self.mutant("unavailable", lambda m: m["vehicle_engine"].__setitem__("available_from_year", 1951), "vehicle unavailable"),
            ),
            (
                "P002-FIX-012",
                "insufficient funds fail",
                lambda: self.mutant("funds", lambda m: m["funding_proof"].__setitem__("command_cost_total", 8000000), "insufficient opening funds"),
            ),
            (
                "P002-FIX-013",
                "out-of-map coordinate fails",
                lambda: self.mutant("bounds", lambda m: m["coordinate_plan"]["road_segments"][0].__setitem__("from", [-1, 31]), "coordinate outside map"),
            ),
            (
                "P002-FIX-014",
                "forbidden road branch fails",
                lambda: self.mutant("slope", lambda m: m["coordinate_plan"]["road_segments"][0]["forbidden_branches"].__setitem__("slope", True), "forbidden tile branch"),
            ),
            (
                "P002-FIX-015",
                "pickup outside producer catchment fails",
                lambda: self.mutant("pickup-catchment", lambda m: m["coordinate_plan"]["pickup_stop"].__setitem__("tile", [30, 30]), "pickup stop outside producer catchment"),
            ),
            (
                "P002-FIX-016",
                "delivery outside acceptor catchment fails",
                lambda: self.mutant("delivery-catchment", lambda m: m["coordinate_plan"]["delivery_stop"].__setitem__("tile", [30, 30]), "delivery stop outside acceptor catchment"),
            ),
            (
                "P002-FIX-017",
                "inaccessible depot fails",
                lambda: self.mutant("depot", lambda m: m["coordinate_plan"]["depot"].__setitem__("tile", [30, 29]), "depot inaccessible"),
            ),
            (
                "P002-FIX-018",
                "disconnected route fails",
                lambda: self.mutant("route", lambda m: m["coordinate_plan"]["road_segments"][1].__setitem__("from", [30, 31]), "route disconnected"),
            ),
            (
                "P002-FIX-019",
                "duplicate object coordinate fails",
                lambda: self.mutant("duplicate-object", lambda m: m["coordinate_plan"]["delivery_stop"].__setitem__("tile", [12, 30]), "duplicate planned object coordinate"),
            ),
            (
                "P002-FIX-020",
                "personal data string fails",
                lambda: self.mutant("personal-data", lambda m: m["command_plan"]["actions"][0].__setitem__("intent", "contact person@example.com"), "personal data string present"),
            ),
            (
                "P002-SET-001",
                "repeated normalized export is byte-identical",
                lambda: self._assert_equal(normalized_settings_bytes(self.settings), normalized_settings_bytes(copy.deepcopy(self.settings))),
            ),
            (
                "P002-SET-002",
                "shuffled input order canonicalizes equally",
                self._test_shuffled_settings,
            ),
            ("P002-SET-003", "behavior change changes identity and fails preflight", self._test_behavior_change),
            ("P002-SET-004", "GUI-only change preserves authoritative identity", self._test_gui_only_change),
            ("P002-SET-005", "duplicate setting identifier fails", self._test_duplicate_setting),
            ("P002-SET-006", "unknown required setting fails", self._test_unknown_setting),
            ("P002-SET-007", "missing required setting fails", self._test_missing_setting),
            ("P002-SET-008", "user override fails before replay", self._test_user_override),
            ("P002-SET-009", "locale does not change normalized settings or identity", lambda: self._test_environment_independence("LC_ALL", "tr_TR.UTF-8")),
            ("P002-SET-010", "timezone does not change normalized settings or identity", lambda: self._test_environment_independence("TZ", "Pacific/Chatham")),
            ("P002-LOD-003", "one-bit save mutation fails digest preflight", self._test_save_bit_mutation),
            ("P002-LOD-004", "wrong content profile fails identity preflight", self._test_wrong_content_profile),
        ]
        random.Random(self.seed).shuffle(cases)
        for test_id, description, function in cases:
            self.case(test_id, description, function)
        expected = (
            {f"P002-FIX-{number:03d}" for number in range(1, 21)}
            | {f"P002-SET-{number:03d}" for number in range(1, 11)}
            | {"P002-LOD-003", "P002-LOD-004"}
        )
        if set(self.passed) != expected or len(self.passed) != 32:
            raise TestFailure("pre-PORT003 PORT-002 contract ID inventory mismatch")
        print(f"1..{len(self.passed)}")
        print(f"# Pre-PORT003 PORT-002 contract tests passed: {len(self.passed)}/32; schedule_seed={self.seed}")
        print("# Mutation tests do not assign status; the committed manifest separately validates as PORT002A_FROZEN. PORT002B remains open.")

    @staticmethod
    def _assert_equal(left: object, right: object) -> None:
        if left != right:
            raise TestFailure(f"values differ: {left!r} != {right!r}")

    def _test_shuffled_settings(self) -> None:
        shuffled = copy.deepcopy(self.settings)
        random.Random(self.seed ^ 0x2002).shuffle(shuffled["settings"])
        self._assert_equal(normalized_settings_bytes(shuffled), normalized_settings_bytes(self.settings))

    def _test_behavior_change(self) -> None:
        changed = copy.deepcopy(self.settings)
        self.setting_entry(changed, "economy.inflation")["value"] = True
        if authoritative_settings_identity(changed) == authoritative_settings_identity(self.settings):
            raise TestFailure("behavior change did not change authoritative identity")
        self.expect_contract_error(lambda: assert_frozen_settings(changed, self.settings), "behavior-affecting settings identity mismatch")

    def _test_gui_only_change(self) -> None:
        changed = copy.deepcopy(self.settings)
        self.setting_entry(changed, "gui.pause_on_newgame")["value"] = True
        self._assert_equal(authoritative_settings_identity(changed), authoritative_settings_identity(self.settings))
        if normalized_settings_bytes(changed) == normalized_settings_bytes(self.settings):
            raise TestFailure("GUI-only document change was not represented in full normalized bytes")

    def _test_duplicate_setting(self) -> None:
        changed = copy.deepcopy(self.settings)
        changed["settings"].append(copy.deepcopy(changed["settings"][0]))
        self.expect_contract_error(lambda: normalized_settings_bytes(changed), "duplicate setting identifier")

    def _test_unknown_setting(self) -> None:
        changed = copy.deepcopy(self.settings)
        changed["settings"][0]["id"] = "ai.unknown_required"
        self.expect_contract_error(lambda: normalized_settings_bytes(changed), "unknown required setting")

    def _test_missing_setting(self) -> None:
        changed = copy.deepcopy(self.settings)
        changed["settings"].pop()
        self.expect_contract_error(lambda: normalized_settings_bytes(changed), "missing required setting")

    def _test_user_override(self) -> None:
        changed = copy.deepcopy(self.settings)
        self.setting_entry(changed, "gui.autosave_interval")["value"] = 10
        self.expect_contract_error(lambda: assert_frozen_settings(changed, self.settings), "user configuration overrides frozen setting")

    def _test_environment_independence(self, key: str, value: str) -> None:
        before_bytes = normalized_settings_bytes(self.settings)
        before_identity = authoritative_settings_identity(self.settings)
        previous = os.environ.get(key)
        os.environ[key] = value
        try:
            self._assert_equal(normalized_settings_bytes(self.settings), before_bytes)
            self._assert_equal(authoritative_settings_identity(self.settings), before_identity)
        finally:
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous

    def _test_save_bit_mutation(self) -> None:
        manifest, root = self.review_fixture("save-bit-mutation")
        save_path = root / "fixture.sav"
        raw = bytearray(save_path.read_bytes())
        raw[len(raw) // 2] ^= 0x01
        save_path.write_bytes(raw)
        self.expect_contract_error(
            lambda: validate_fixture_data(manifest, self.schema, root, require_final=False, schema_sha256=self.schema_digest),
            "fixture save size or SHA-256 mismatch",
        )

    def _test_wrong_content_profile(self) -> None:
        manifest, root = self.review_fixture("wrong-content-profile")
        manifest["content"]["profile"] = "wrong-profile"
        self.expect_contract_error(
            lambda: validate_fixture_data(manifest, self.schema, root, require_final=False, schema_sha256=self.schema_digest),
            "fixture schema validation failed",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--work-root", required=True, type=pathlib.Path)
    parser.add_argument("--schedule-seed", type=int, default=2002)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    if any(args.work_root.iterdir()):
        print("ERROR: --work-root must be empty", file=sys.stderr)
        return 64
    try:
        Harness(args.repository_root, args.work_root, args.schedule_seed).run()
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
