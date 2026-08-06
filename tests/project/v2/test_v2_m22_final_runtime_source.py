#!/usr/bin/env python3
"""Mutation tests for the retained M22 final native runtime source."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

import jsonschema

from artifact_context import ARTIFACT_ROOT_ENV, ArtifactContext, ArtifactContextError
import prepare_m22_final_runtime as preparation
from tests.project.v2.test_v2_m15_native_source import _write_patch_preimage
import validate_m22_final_runtime_source as validator


def _git(repository: pathlib.Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments], text=True,
    ).strip()


def _patch_side(patch: pathlib.Path, side: str) -> dict[str, dict[int, str]]:
    """Return literal old/new hunk lines keyed by their target line numbers."""

    lines = patch.read_text(encoding="utf-8").splitlines(keepends=True)
    result: dict[str, dict[int, str]] = {}
    index = 0
    while index < len(lines):
        header = re.match(r"diff --git a/(\S+) b/(\S+)", lines[index])
        if header is None:
            index += 1
            continue
        relative = header.group(1)
        positions = result.setdefault(relative, {})
        index += 1
        while index < len(lines) and not lines[index].startswith("diff --git "):
            hunk = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", lines[index])
            if hunk is None:
                index += 1
                continue
            old_line, new_line = int(hunk.group(1)), int(hunk.group(2))
            index += 1
            while (index < len(lines) and not lines[index].startswith("@@ ") and
                   not lines[index].startswith("diff --git ")):
                line = lines[index]
                if line.startswith("\\ No newline"):
                    index += 1
                    continue
                marker, payload = line[:1], line[1:]
                if marker in {" ", "-"}:
                    if side == "old":
                        if old_line in positions and positions[old_line] != payload:
                            raise AssertionError(f"old-side patch overlap drifted: {relative}:{old_line}")
                        positions[old_line] = payload
                    old_line += 1
                if marker in {" ", "+"}:
                    if side == "new":
                        if new_line in positions and positions[new_line] != payload:
                            raise AssertionError(f"new-side patch overlap drifted: {relative}:{new_line}")
                        positions[new_line] = payload
                    new_line += 1
                index += 1
    return result


def _write_patch_chain_preimage(patches: tuple[pathlib.Path, ...], repository: pathlib.Path) -> None:
    if len(patches) == 1:
        _write_patch_preimage(patches[0], repository)
        return
    if len(patches) != 2:
        raise AssertionError("runtime fixture supports the frozen one- or two-patch series")
    intermediate: dict[str, dict[int, str]] = {}
    for source in (_patch_side(patches[0], "new"), _patch_side(patches[1], "old")):
        for relative, positions in source.items():
            destination = intermediate.setdefault(relative, {})
            for line_number, line in positions.items():
                if line_number in destination and destination[line_number] != line:
                    raise AssertionError(f"patch-chain overlap drifted: {relative}:{line_number}")
                destination[line_number] = line
    for relative, positions in intermediate.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(
            positions.get(line_number, f"// fixture filler {line_number}\n")
            for line_number in range(1, max(positions) + 1)
        ), encoding="utf-8")
    subprocess.run(
        ["git", "apply", "--reverse", "--whitespace=error-all", str(patches[0])],
        cwd=repository, check=True,
    )


def _relative(recorded_root: str, recorded_path: str) -> pathlib.PurePosixPath:
    return pathlib.PurePosixPath(recorded_path).relative_to(pathlib.PurePosixPath(recorded_root))


def _write_record_file(
    result_root: pathlib.Path,
    recorded_root: str,
    record: dict[str, Any],
    payload: bytes,
) -> pathlib.Path:
    path = result_root.joinpath(*_relative(recorded_root, record["path"]).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if "bytes" in record:
        record["bytes"] = len(payload)
    record["sha256"] = hashlib.sha256(payload).hexdigest()
    return path


def _write_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _project_authorities(
    root: pathlib.Path,
    project: pathlib.Path,
    directory: pathlib.Path,
    value: dict[str, Any],
    base_source: pathlib.Path,
) -> None:
    for relative in ("config", "docs/project/schema", "integration/openttd/patches/15.3/m22"):
        shutil.copytree(root / relative, project / relative)

    m20_content_path = project / preparation.M20_CONTENT
    m20_content = json.loads(m20_content_path.read_text(encoding="utf-8"))
    for authority, record in zip(m20_content["ai_archives"], value["runtime"]["ai_archives"], strict=True):
        authority["path"] = str(directory / "v2-m20-competition-a" / _relative(value["retained_artifact"], record["path"]))
        authority["sha256"] = record["sha256"]
    for authority, record in zip(m20_content["libraries"], value["runtime"]["ai_libraries"], strict=True):
        authority["path"] = str(directory / "v2-m20-competition-a" / _relative(value["retained_artifact"], record["path"]))
        authority["sha256"] = record["sha256"]
    _write_json(m20_content_path, m20_content)
    m20_contract_path = project / preparation.native.m20.CONTRACT
    m20_contract = json.loads(m20_contract_path.read_text(encoding="utf-8"))
    m20_contract["identities"]["content_manifest_sha256"] = hashlib.sha256(m20_content_path.read_bytes()).hexdigest()
    _write_json(m20_contract_path, m20_contract)

    lock_path = project / preparation.M21_CONTENT_LOCK
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for package, archive, grf in zip(lock["packages"], value["runtime"]["newgrf_archives"],
                                     value["runtime"]["newgrf_files"], strict=True):
        package["archive"]["bytes"] = archive["bytes"]
        package["archive"]["sha256"] = archive["sha256"]
        package["grf_files"][0]["bytes"] = grf["bytes"]
        package["grf_files"][0]["sha256"] = grf["sha256"]
    _write_json(lock_path, lock)

    broad_contract_path = project / preparation.native.m21.CONTRACT
    broad_contract = json.loads(broad_contract_path.read_text(encoding="utf-8"))
    scripts = value["runtime"]["gamescript_files"]
    broad_contract["identities"]["content_lock_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    broad_contract["identities"]["gamescript_info_sha256"] = scripts[0]["sha256"]
    broad_contract["identities"]["gamescript_main_sha256"] = scripts[1]["sha256"]
    _write_json(broad_contract_path, broad_contract)
    (project / preparation.native.m21.GAMESCRIPT_INFO).write_bytes(b"gamescript_files-0\n")
    (project / preparation.native.m21.GAMESCRIPT_MAIN).write_bytes(b"gamescript_files-1\n")

    m21_path = project / preparation.M21_SOURCE
    m21 = json.loads(m21_path.read_text(encoding="utf-8"))
    m21_root = directory / "v2-m21-broad-a"
    m21["retained_artifact"] = str(m21_root)
    m21["source"] = {"commit": _git(base_source, "rev-parse", "HEAD"), "path": str(base_source),
                     "tree": _git(base_source, "rev-parse", "HEAD^{tree}")}
    m21["build"]["open_gfx"] = {
        "bytes": value["runtime"]["open_gfx"]["bytes"],
        "path": str(m21_root / "build-broad/baseset/opengfx-8.0.tar"),
        "sha256": value["runtime"]["open_gfx"]["sha256"],
    }
    for name, record in value["runtime"]["configs"].items():
        m21["runtime"]["configs"][name] = {"path": str(m21_root / f"{name}.cfg"), "sha256": record["sha256"]}
    m21["runtime"]["content_root"] = str(m21_root / "build-broad/newgrf/m21")
    m21["runtime"]["gamescript_root"] = str(m21_root / "build-broad/game/m21coverage")
    for authority, record in zip(m21["runtime"]["content_files"], value["runtime"]["newgrf_files"], strict=True):
        authority.update({"bytes": record["bytes"], "sha256": record["sha256"]})
    _write_json(m21_path, m21)

    m20_path = project / preparation.M20_SOURCE
    m20 = json.loads(m20_path.read_text(encoding="utf-8"))
    m20["retained_artifact"] = str(directory / "v2-m20-competition-a")
    _write_json(m20_path, m20)
    value["base"] = {"commit": m21["source"]["commit"], "source_record_sha256": hashlib.sha256(m21_path.read_bytes()).hexdigest(),
                     "tree": m21["source"]["tree"]}
    value["prerequisites"]["m20_source_record_sha256"] = hashlib.sha256(m20_path.read_bytes()).hexdigest()
    value["prerequisites"]["m21_source_record_sha256"] = hashlib.sha256(m21_path.read_bytes()).hexdigest()


def _smoke_report(root: pathlib.Path, source: dict[str, Any], case: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    from tests.project.v2.test_v2_m16_cargo_evidence import _report_fixture
    from tests.project.v2.test_v2_m19_air_evidence import _probe as m19_probe
    from tests.project.v2.test_v2_m21_broad_evidence import _probe_result as m21_probe

    native = preparation.native
    gate, probe = case["source_gate"], native.canonical_probe(case)
    executable_sha = source["executable"]["sha256"]
    record = {"case_id": case["case_id"], "climate": case["climate"], "cargo": case["cargo"],
              "probe": probe, "seed": case["seed"], "metrics": metrics}
    if gate == "G15":
        return {"steps": [{"operation": "SERVICE", "service": {
            "company": {"delivered_passengers": metrics["delivered"], "income": metrics["income"]},
            "ticks": {"executed": metrics["ticks"]},
            "vehicle": {"capacity": metrics["vehicle_capacity"], "running": True},
        }}]}
    if gate in {"G16", "G17", "G18"}:
        logical = {"G16": "v2-m16-cargo-matrix-a", "G17": "v2-m17-rail-matrix-a", "G18": "v2-m18-ship-matrix-c"}[gate]
        module = {"G16": native.m16, "G17": native.m17, "G18": native.m18}[gate]
        contract = json.loads((root / module.CONTRACT).read_text(encoding="utf-8"))
        evidence = {"aggregate": {"actual_cargo_classes": []}, "executable_sha256": executable_sha}
        report = _report_fixture(record, "fixture", evidence, logical, contract)
        report["map"] = {"height": case["map_height"], "width": case["map_width"]}
        return report
    if gate == "G19":
        return {
            "catalog": {"aircraft_engines": [{"kind": "helicopter" if index < 3 else "airplane"} for index in range(41)],
                        "airport_specs": [{"enabled": index < 9} for index in range(10)],
                        "movement_blocks": 64, "movement_headings": 22},
            "executable_sha256": executable_sha, "map": {"height": case["map_height"], "width": case["map_width"]},
            "probe": m19_probe(record),
            "request": {"cargo_label": case["cargo"], "probe": probe, "run_id": case["case_id"], "seed": case["seed"]},
            "run_id": case["case_id"], "schema_version": "openttd-rl-v2-m19-air-report-1", "status": "PASS",
        }
    if gate == "G20":
        contract = native.m20.load(root / native.m20.CONTRACT)
        identities = native.m20.expected_identities(root, contract)
        return {
            "identity": identities, "request": {"split": "final"}, "status": "PASS",
            "result": {"policy_input": {"public_map": {"width": case["map_width"], "height": case["map_height"]}},
                       "privileged_inputs": [], "save_load_public_exact": True,
                       "score": {"rl": {"alive": True, "aircraft": 1, "delivered_cargo_units": metrics["delivered"],
                                        "operating_profit": metrics["income"], "company_value": metrics["company_value"]},
                                 "opponents": [{"name": case["opponent"]}]}}
        }
    contract = native.m21.load(root / native.m21.CONTRACT)
    result = m21_probe({"probe": probe}, contract)
    if probe == "authority_economy":
        result["commands"] = [{"command": f"fixture-{index}", "status": "SUCCESS"}
                              for index in range(metrics["commands"])]
    elif probe == "events":
        result["breakdown"]["recovery_ticks"] = metrics["recovery_ticks"]
    return {
        "active_content": [{"id": item["id"], "md5": item["md5"]} for item in contract["newgrfs"]] if probe == "content" else [],
        "map": {"height": case["map_height"], "width": case["map_width"]},
        "request": {"landscape": case["climate"], "probe": probe}, "result": result,
        "status": "PASS",
    }


def _replace_record_file(
    result_root: pathlib.Path,
    recorded_root: str,
    record: dict[str, Any],
    payload: bytes,
) -> pathlib.Path:
    path = result_root.joinpath(*_relative(recorded_root, record["path"]).parts)
    path.write_bytes(payload)
    record["bytes"] = len(payload)
    record["sha256"] = hashlib.sha256(payload).hexdigest()
    return path


def _run_producer_smoke(
    root: pathlib.Path,
    runtime: preparation.native.RuntimePaths,
    case_root: pathlib.Path,
    case: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Create the retained smoke through the producer dispatch, stubbing only native launch."""

    native = preparation.native

    def launch(_command: list[str], _runtime: preparation.native.RuntimePaths,
               run_root: pathlib.Path, launched_case: dict[str, Any]) -> tuple[float, str]:
        native.write_new(run_root / "report.json", report)
        if launched_case["source_gate"] == "G15":
            native.write_new(run_root / "reset.json", {"request": {
                "width": launched_case["map_width"], "height": launched_case["map_height"],
                "climate": launched_case["climate"], "split": "final",
            }})
        (run_root / "openttd.log").write_text("", encoding="utf-8")
        return 0.0, ""

    with mock.patch.object(native, "launch", side_effect=launch):
        return native.run_native_case(root, runtime, case_root, case)


def expected_runtime_closure(
    logical_set: str,
    build_name: str,
    smoke_ids: tuple[str, ...],
) -> tuple[tuple[str, str, str], ...]:
    archive_names = (
        "414e0201-Squid_Ate_FISH_FISH_2_Ships-2.0.3.tar",
        "415a1001-RattRoads-1.2.1.tar",
        "43415000-OpenGFX_Airports-0.5.0.tar",
        "454e1401-OpenGFX_Stations-1.0.tar",
        "4e445903-Age_of_Industry_Replacement_Set-1.3.2.tar",
        "4f472b31-OpenGFX_Trains-0.3.0.tar",
        "52415608-RAV8_Rangless_Av8-1.00.tar",
        "52580101-FIRS_and_CHIPS_style_objects-0.1.10.tar",
        "54574606-Timberwolf_s_Tracks-1.3.0.tar",
        "9787eafe-Road_Hog_Buses_Trucks_Trams-1.4.1.tar",
    )
    grf_names = (
        "fish.grf", "rattroads.grf", "airports.grf", "stations.grf", "industries.grf",
        "trains.grf", "aircraft.grf", "objects.grf", "tracks.grf", "roadhog.grf",
    )
    runtime_paths = (
        f"{build_name}/openttd",
        "build.log", "configure.log", "ctest.log", "ctest.xml", "ctest-inventory.json",
        f"{build_name}/baseset/opengfx-8.0.tar",
        "base.cfg", "content.cfg", "gamescript.cfg",
        "content_download/ai/484f4745-AAAHogEx-115.tar",
        "content_download/ai/4b524132-KrakenAI2-3.tar",
        "content_download/ai/4e6f7041-NoOpAI-4.tar",
        "content_download/ai/library/4752412a-Graph.AyStar-6.tar",
        "content_download/ai/library/5046524f-Pathfinder.Road-4.tar",
        "content_download/ai/library/51554248-Queue.BinaryHeap-1.tar",
        "content_download/ai/library/5350524c-SuperLib-40.tar",
        f"{build_name}/game/m21coverage/info.nut",
        f"{build_name}/game/m21coverage/main.nut",
        *(f"{build_name}/content_download/newgrf/{name}" for name in archive_names),
        *(f"{build_name}/newgrf/m21/{name}" for name in grf_names),
    )
    return (
        ("v2-m21-broad-a", "source", "directory"),
        ("v2-m21-broad-a", "source/.git", "directory"),
        (logical_set, "source", "directory"),
        (logical_set, "source/.git", "directory"),
        *((logical_set, path, "file") for path in runtime_paths),
        *((logical_set, f"smokes/{case_id}/{name}", "file")
          for case_id in smoke_ids for name in ("manifest.json", "report.json", "openttd.log")),
    )


def make_live_runtime_fixture(
    root: pathlib.Path,
    directory: pathlib.Path,
    source: dict[str, Any],
    *,
    patches: tuple[pathlib.Path, ...],
    logical_set: str,
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path, pathlib.Path]:
    """Create real relocated Git/runtime/smoke bytes while retaining frozen path strings."""

    value = copy.deepcopy(source)
    project = directory / "project"
    base_source = directory / "v2-m21-broad-a/source"
    base_source.mkdir(parents=True)
    resolved_patches = tuple((root / path).resolve() for path in patches)
    _write_patch_chain_preimage(resolved_patches, base_source)
    subprocess.run(["git", "init", "-q", str(base_source)], check=True)
    subprocess.run(["git", "-C", str(base_source), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(base_source), "-c", "user.name=runtime fixture",
        "-c", "user.email=runtime-fixture@example.invalid", "commit", "-q", "-m", "base",
    ], check=True)
    value["base"]["commit"] = _git(base_source, "rev-parse", "HEAD")
    value["base"]["tree"] = _git(base_source, "rev-parse", "HEAD^{tree}")

    result_root = directory / logical_set
    result_source = result_root / "source"
    result_root.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(result_source)], check=True)
    for patch in resolved_patches:
        subprocess.run([
            "git", "-C", str(result_source), "apply", "--index", "--whitespace=error-all", str(patch),
        ], check=True)
    subprocess.run([
        "git", "-C", str(result_source), "-c", "user.name=runtime fixture",
        "-c", "user.email=runtime-fixture@example.invalid", "commit", "-q", "-m", "result",
    ], check=True)
    value["source"]["commit"] = _git(result_source, "rev-parse", "HEAD")
    value["source"]["tree"] = _git(result_source, "rev-parse", "HEAD^{tree}")

    recorded_root = value["retained_artifact"]
    executable = _write_record_file(
        result_root, recorded_root, value["executable"], b"#!/bin/sh\nexit 0\n",
    )
    executable.chmod(0o700)
    names = [f"upstream-{index:03d}" for index in range(98)]
    for name, record in value["build"]["logs"].items():
        if name == "junit":
            cases = "".join(f'<testcase name="{test}"/>' for test in names)
            payload = f'<testsuite tests="98" failures="0" errors="0" skipped="0">{cases}</testsuite>\n'.encode()
        elif name == "ctest":
            payload = b"100% tests passed, 0 tests failed out of 98\n"
        else:
            payload = f"M22 {name} completed successfully\n".encode()
        _write_record_file(result_root, recorded_root, record, payload)
    inventory = preparation.canonical_bytes({"tests": names})
    _write_record_file(result_root, recorded_root, value["build"]["test_inventory"], inventory)
    _write_record_file(result_root, recorded_root, value["runtime"]["open_gfx"], b"OpenGFX fixture archive\n")
    for name, record in value["runtime"]["configs"].items():
        _write_record_file(result_root, recorded_root, record, f"[{name}]\n".encode())
    for group in ("ai_archives", "ai_libraries", "gamescript_files", "newgrf_archives", "newgrf_files"):
        for ordinal, record in enumerate(value["runtime"][group]):
            _write_record_file(
                result_root, recorded_root, record, f"{group}-{ordinal}\n".encode(),
            )
    _project_authorities(root, project, directory, value, base_source)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(project), "-c", "user.name=runtime fixture",
        "-c", "user.email=runtime-fixture@example.invalid", "commit", "-q", "-m", "fixture authorities",
    ], check=True)
    value["repository"] = {"commit": _git(project, "rev-parse", "HEAD"), "tree": _git(project, "rev-parse", "HEAD^{tree}")}

    runtime = preparation.native.RuntimePaths(
        executable=executable,
        opengfx=result_root.joinpath(*_relative(recorded_root, value["runtime"]["open_gfx"]["path"]).parts),
        base_config=result_root.joinpath(*_relative(recorded_root, value["runtime"]["configs"]["base"]["path"]).parts),
        content_config=result_root.joinpath(*_relative(recorded_root, value["runtime"]["configs"]["content"]["path"]).parts),
        gamescript_config=result_root.joinpath(*_relative(recorded_root, value["runtime"]["configs"]["gamescript"]["path"]).parts),
        source_tree=value["source"]["tree"],
    )
    if len(value["smokes"]) == len(preparation.SMOKE_CASES):
        smoke_cases = preparation.SMOKE_CASES
    else:
        import prepare_m22_followup_runtime as followup_preparation
        smoke_cases = followup_preparation.SMOKE_CASES
    (result_root / "smokes").mkdir(mode=0o700)
    for expected, smoke in zip(smoke_cases, value["smokes"], strict=True):
        smoke["executable_sha256"] = value["executable"]["sha256"]
        smoke["source_tree"] = value["source"]["tree"]
        case_root = result_root.joinpath(*_relative(recorded_root, smoke["artifact_root"]).parts)
        report = _smoke_report(project, value, expected, smoke["metrics"])
        produced = _run_producer_smoke(project, runtime, case_root, expected, report)
        smoke.update(produced)
    if "final_runtime_source_record_sha256" in value["prerequisites"]:
        value["prerequisites"]["final_runtime_source_record_sha256"] = hashlib.sha256(
            (project / "config/v2/m22-final-runtime-source.json").read_bytes()
        ).hexdigest()
    config_path = project / f"{logical_set}.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, base_source, result_source


class M22FinalRuntimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "runtime-source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M22RuntimeSourceError, pattern) if pattern else self.assertRaises(
                validator.M22RuntimeSourceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value),
                                   artifact_context=ArtifactContext.offline())

    def test_repository_runtime_source_passes(self) -> None:
        result = validator.validate(self.root)
        self.assertEqual((result["files"], result["smokes"], result["live"]), (9, 8, False))

    def test_live_runtime_source_and_all_artifacts_pass(self) -> None:
        artifact_root = os.environ.get(ARTIFACT_ROOT_ENV)
        if artifact_root is None:
            self.skipTest("live artifact validation is outside offline mode")
        result = validator.validate(self.root, artifact_context=ArtifactContext.live(artifact_root))
        self.assertTrue(result["live"])

    def test_relocated_root_does_not_rewrite_retained_artifact(self) -> None:
        retained = (self.root / validator.CONFIG).read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            validator.validate(
                config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
            )
        self.assertEqual((self.root / validator.CONFIG).read_bytes(), retained)

    def test_offline_validation_never_opens_recorded_runtime_paths(self) -> None:
        recorded_root = self.source["retained_artifact"]
        original_open = pathlib.Path.open
        original_is_file = pathlib.Path.is_file
        original_is_dir = pathlib.Path.is_dir
        original_stat = pathlib.Path.stat

        def reject_open(path: pathlib.Path, *args: object, **kwargs: object):
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path opened offline: {path}")
            return original_open(path, *args, **kwargs)

        def reject_is_file(path: pathlib.Path) -> bool:
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path probed offline: {path}")
            return original_is_file(path)

        def reject_is_dir(path: pathlib.Path) -> bool:
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path probed offline: {path}")
            return original_is_dir(path)

        def reject_stat(path: pathlib.Path, *args: object, **kwargs: object):
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path stated offline: {path}")
            return original_stat(path, *args, **kwargs)

        real_git = validator.git

        def reject_recorded_git(repository: pathlib.Path, *arguments: str) -> str:
            if str(repository).startswith(recorded_root):
                raise AssertionError(f"recorded Git path opened offline: {repository}")
            return real_git(repository, *arguments)

        with mock.patch.object(pathlib.Path, "open", reject_open), \
             mock.patch.object(pathlib.Path, "is_file", reject_is_file), \
             mock.patch.object(pathlib.Path, "is_dir", reject_is_dir), \
             mock.patch.object(pathlib.Path, "stat", reject_stat), \
             mock.patch.object(validator, "git", side_effect=reject_recorded_git):
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_relocated_live_runtime_and_smokes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            summary = validator.validate(
                config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
            )
        self.assertTrue(summary["live"])

    def test_relocated_m21_base_is_used_for_patch_check(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, result_source = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            summary = validator.validate(
                config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
            )
            observed_tree = _git(result_source, "rev-parse", "HEAD^{tree}")
        self.assertEqual(summary["source_tree"], observed_tree)

    def test_required_live_inputs_are_the_exact_runtime_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        keys = tuple((item.logical_set, item.relative_path, item.kind) for item in requirements)
        expected = expected_runtime_closure(
            "v2-m22-final-runtime-c",
            "build-final",
            (
                "source-g15-toyland-road", "source-g16-toyland-cargo", "source-g17-arctic-rail",
                "source-g18-tropic-water", "source-g19-toyland-air", "source-g20-tropic-aaahogex",
                "source-g21-arctic-content", "source-g21-tropic-gamescript",
            ),
        )
        self.assertEqual(keys, expected)
        self.assertEqual(len(keys), len(set(keys)))

    def test_missing_live_input_fails_before_git_or_semantic_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            (base / "v2-m22-final-runtime-c/base.cfg").unlink()
            with mock.patch.object(validator, "git", side_effect=AssertionError("Git ran before preflight")), \
                 mock.patch.object(validator, "_validate_live_source", side_effect=AssertionError("source reader ran before preflight")), \
                 mock.patch.object(validator, "_validate_live_files", side_effect=AssertionError("file reader ran before preflight")):
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(
                        config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                    )

    def test_recorded_runtime_path_traversal_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["executable"]["path"] = value["retained_artifact"] + "/../escape"
        self.mutation_fails(value, "normalized POSIX")

    def test_runtime_file_alias_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["logs"]["build"] = copy.deepcopy(value["build"]["logs"]["configure"])
        self.mutation_fails(value, "layout|duplicate")

    def test_custom_config_cannot_substitute_m21_base_identity(self) -> None:
        value = copy.deepcopy(self.source)
        value["base"]["commit"] = "1" * 40
        value["base"]["tree"] = "2" * 40
        self.mutation_fails(value, "base identity")

    def test_offline_custom_authorities_reject_zeroed_content_digest_links(self) -> None:
        links = (
            (preparation.native.m20.CONTRACT, "content_manifest_sha256"),
            (preparation.native.m21.CONTRACT, "content_lock_sha256"),
        )
        for relative, identity in links:
            with self.subTest(identity=identity), tempfile.TemporaryDirectory() as raw:
                base = pathlib.Path(raw).resolve()
                _, config_path, _, _ = make_live_runtime_fixture(
                    self.root, base, self.source,
                    patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
                )
                authority_path = config_path.parent / relative
                authority = json.loads(authority_path.read_text(encoding="utf-8"))
                authority["identities"][identity] = "0" * 64
                _write_json(authority_path, authority)
                with self.assertRaisesRegex(validator.M22RuntimeSourceError, "identity"):
                    validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.offline())

    def test_offline_custom_authorities_reject_wrong_referenced_content_bytes(self) -> None:
        references = (preparation.M20_CONTENT, preparation.M21_CONTENT_LOCK)
        for relative in references:
            with self.subTest(relative=str(relative)), tempfile.TemporaryDirectory() as raw:
                base = pathlib.Path(raw).resolve()
                _, config_path, _, _ = make_live_runtime_fixture(
                    self.root, base, self.source,
                    patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
                )
                authority_path = config_path.parent / relative
                authority_path.write_bytes(authority_path.read_bytes() + b"\n")
                with self.assertRaisesRegex(validator.M22RuntimeSourceError, "identity"):
                    validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.offline())

    def test_renamed_base_config_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["configs"]["base"]["path"] = value["retained_artifact"] + "/renamed.cfg"
        self.mutation_fails(value, "canonical runtime")

    def test_wrong_ai_name_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["ai_archives"][0]["name"] = "SubstituteAI"
        self.mutation_fails(value)

    def test_duplicated_ai_name_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["ai_archives"][1]["name"] = value["runtime"]["ai_archives"][0]["name"]
        self.mutation_fails(value, "AI archive inventory")

    def test_zero_newgrf_digest_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["newgrf_archives"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "NewGRF archive inventory")

    def test_reordered_build_logs_fail_offline(self) -> None:
        value = copy.deepcopy(self.source)
        logs = value["build"]["logs"]
        value["build"]["logs"] = {name: logs[name] for name in reversed(tuple(logs))}
        self.mutation_fails(value, "canonical runtime")

    def test_substituted_config_digest_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["configs"]["base"]["sha256"] = value["runtime"]["configs"]["content"]["sha256"]
        self.mutation_fails(value, "canonical runtime")

    def test_hardlinked_live_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            result = base / "v2-m22-final-runtime-c"
            first = result / "smokes/source-g15-toyland-road/openttd.log"
            second = result / "smokes/source-g16-toyland-cargo/openttd.log"
            second.unlink()
            os.link(first, second)
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "hard link"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_symlinked_live_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            result = base / "v2-m22-final-runtime-c"
            config = result / "base.cfg"
            target = result / "untracked-target.cfg"
            target.write_bytes(config.read_bytes())
            config.unlink()
            config.symlink_to(target)
            with self.assertRaisesRegex(ArtifactContextError, "symlink"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_historical_repository_commit_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["repository"]["commit"] = "0" * 40
        self.mutation_fails(value, "git cat-file")

    def test_historical_repository_tree_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["repository"]["tree"] = "0" * 40
        self.mutation_fails(value, "historical repository identity")

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_prerequisite_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["prerequisites"]["m20_source_record_sha256"] = "0" * 64
        self.mutation_fails(value, "prerequisite identity")

    def test_final_manifest_open_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["final_boundary"]["manifest_opened"] = True
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_public_smoke_seed_leak_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["case"]["seed"] = 1
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_smoke_order_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0], value["smokes"][1] = value["smokes"][1], value["smokes"][0]
        self.mutation_fails(value, "inventory/order")

    def test_vacuous_service_metric_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["metrics"]["delivered"] = 0
        self.mutation_fails(value, "useful-service smoke is vacuous")

    def test_executable_identity_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            value["executable"]["sha256"] = "0" * 64
            for smoke in value["smokes"]:
                smoke["executable_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_smoke_report_digest_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            value["smokes"][0]["report_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(
                    config_path.parent, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_non_executable_live_binary_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            (base / "v2-m22-final-runtime-c/build-final/openttd").chmod(0o600)
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "executable"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_matched_malformed_ctest_json_is_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            _replace_record_file(
                base / "v2-m22-final-runtime-c", value["retained_artifact"],
                value["build"]["test_inventory"], b"{not-json\n",
            )
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "CTest inventory"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_matched_invalid_junit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            _replace_record_file(
                base / "v2-m22-final-runtime-c", value["retained_artifact"],
                value["build"]["logs"]["junit"], b"not XML\n",
            )
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "JUnit"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_matched_failing_junit_totals_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            names = [f"upstream-{index:03d}" for index in range(98)]
            cases = "".join(f'<testcase name="{name}"/>' for name in names)
            payload = f'<testsuite tests="98" failures="1" errors="0" skipped="0">{cases}</testsuite>\n'.encode()
            _replace_record_file(base / "v2-m22-final-runtime-c", value["retained_artifact"],
                                 value["build"]["logs"]["junit"], payload)
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "JUnit results"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_matched_smoke_manifest_semantic_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            smoke = value["smokes"][0]
            path = base / "v2-m22-final-runtime-c/smokes/source-g15-toyland-road/manifest.json"
            payload = b'{"schema_version":"wrong"}\n'
            path.write_bytes(payload)
            smoke["manifest_sha256"] = hashlib.sha256(payload).hexdigest()
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "smoke .*manifest"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_live_fixture_manifest_is_independent_of_validator_expectation(self) -> None:
        with tempfile.TemporaryDirectory() as raw, mock.patch.object(
            validator, "_expected_smoke_manifest", return_value={"schema_version": "validator-substitute"},
        ):
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "smoke .*manifest"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_matched_smoke_report_semantic_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            smoke = value["smokes"][6]
            path = base / "v2-m22-final-runtime-c/smokes/source-g21-arctic-content/report.json"
            report = json.loads(path.read_text(encoding="utf-8"))
            report["status"] = "FAIL"
            payload = preparation.canonical_bytes(report)
            path.write_bytes(payload)
            smoke["report_sha256"] = hashlib.sha256(payload).hexdigest()
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "G21 smoke"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_digest_honest_gamescript_response_shapes_are_domain_errors_without_traceback(self) -> None:
        variants = (
            ("list", []),
            ("null", None),
            ("wrong-keys", {"wrong_one": True, "wrong_two": True}),
            ("nested-wrong-type", {"goal_question": {"nested": True}, "story_button": True}),
        )
        for label, responses in variants:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                base = pathlib.Path(raw).resolve()
                value, config_path, _, _ = make_live_runtime_fixture(
                    self.root, base, self.source,
                    patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
                )
                smoke = next(item for item in value["smokes"]
                             if item["case"]["case_id"] == "source-g21-tropic-gamescript")
                report_path = base / "v2-m22-final-runtime-c/smokes/source-g21-tropic-gamescript/report.json"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report["result"]["responses"] = responses
                payload = preparation.canonical_bytes(report)
                report_path.write_bytes(payload)
                smoke["report_sha256"] = hashlib.sha256(payload).hexdigest()
                config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                with self.assertRaises(Exception) as raised:
                    validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))
                self.assertIsInstance(raised.exception, validator.M22RuntimeSourceError)
                self.assertRegex(str(raised.exception), "GameScript responses")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = validator.main([
                        "--root", str(config_path.parent), "--config", str(config_path),
                        "--artifact-root", str(base),
                    ])
                self.assertEqual(status, 1)
                self.assertNotIn("Traceback", output.getvalue())

    def test_digest_honest_content_assets_container_is_a_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            smoke = next(item for item in value["smokes"]
                         if item["case"]["case_id"] == "source-g21-arctic-content")
            report_path = base / "v2-m22-final-runtime-c/smokes/source-g21-arctic-content/report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["result"]["assets"] = []
            payload = preparation.canonical_bytes(report)
            report_path.write_bytes(payload)
            smoke["report_sha256"] = hashlib.sha256(payload).hexdigest()
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaises(Exception) as raised:
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))
            self.assertIsInstance(raised.exception, validator.M22RuntimeSourceError)
            self.assertRegex(str(raised.exception), "content assets")

    def test_digest_matched_smoke_log_failure_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            smoke = value["smokes"][0]
            path = base / "v2-m22-final-runtime-c/smokes/source-g15-toyland-road/openttd.log"
            payload = b"Traceback (most recent call last):\nfixture\n"
            path.write_bytes(payload)
            smoke["openttd_log_sha256"] = hashlib.sha256(payload).hexdigest()
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "log semantics"):
                validator.validate(config_path.parent, config_path, artifact_context=ArtifactContext.live(base))

    def test_removed_base_source_option_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                validator.main(["--root", str(self.root), "--base" + "-source", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_artifact_root_wins_over_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = pathlib.Path(raw).resolve()
            configured = parent / "configured"
            configured.mkdir()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, configured, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(parent / "wrong")}, clear=False):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = validator.main([
                        "--root", str(config_path.parent), "--config", str(config_path),
                        "--artifact-root", str(configured),
                    ])
        self.assertEqual(status, 0)

    def test_relative_cli_artifact_root_fails_without_environment_fallback(self) -> None:
        with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(self.root)}, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                status = validator.main(["--root", str(self.root), "--artifact-root", "relative/artifacts"])
        self.assertEqual(status, 1)

    def test_ctest_claim_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["upstream_ctest"]["passed"] = 97
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
