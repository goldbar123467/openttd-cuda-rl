#!/usr/bin/env python3
"""Package, content-address, source-boundary, and mutation tests for M23."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import m23_golden
import m23_package
import validate_m23_release_contract as contract_validator


class M23PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = contract_validator.load(cls.root / contract_validator.CONTRACT)
        cls.checkpoints, cls.deployments = m23_package.architecture_maps(cls.contract)
        cls.architecture = contract_validator.ARCHITECTURES[0]

    def golden_records(self) -> list[m23_golden.GoldenRecord]:
        records: list[m23_golden.GoldenRecord] = []
        carried: list[list[float] | None] = [None, None]
        for local in range(m23_golden.CASES_PER_ARCHITECTURE):
            definition = m23_golden.generate_definition(0, local)
            hidden = definition.initial_hidden
            if definition.hidden_mode == 1:
                hidden = carried[definition.sequence] or []
            logits = [-1.0] * (definition.batch * m23_golden.PROGRAMS)
            actions: list[int] = []
            for row in range(definition.batch):
                action = next(index for index, legal in enumerate(
                    definition.program_mask[row * m23_golden.PROGRAMS:(row + 1) * m23_golden.PROGRAMS]
                ) if legal)
                logits[row * m23_golden.PROGRAMS + action] = 1.0
                actions.append(action)
            next_hidden = [0.0] * (definition.batch * m23_golden.HIDDEN)
            record = m23_golden.GoldenRecord(
                definition, list(hidden), logits, [0.0] * definition.batch, next_hidden, actions,
            )
            if definition.case_class == 1:
                carried[definition.sequence] = next_hidden
            records.append(record)
        return records

    def create_package(self, parent: pathlib.Path) -> pathlib.Path:
        stage = parent / ".stage"
        stage.mkdir()
        (stage / "model.onnx").write_bytes(b"fixture-onnx")
        m23_golden.write_jsonl((stage / "golden.jsonl").resolve(), self.golden_records(), self.architecture)
        checkpoint = self.checkpoints[self.architecture]
        deployment = self.deployments[self.architecture]
        results = [{"action_exact": True, "case_id": item.definition.case_id, "passed": True}
                   for item in self.golden_records()]
        evaluation = {
            "architecture_id": self.architecture,
            "case_count": 24,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "compared_runtimes": ["native-libtorch-cpu", "standalone-onnxruntime-cpu"],
            "equivalence_report_sha256": "4" * 64,
            "failure_counts": {"action": 0, "float": 0, "total": 0},
            "golden_binary_sha256": "5" * 64,
            "maximum_error": {"hidden_absolute": 0.0},
            "model_sha256": m23_package.sha256_file(stage / "model.onnx"),
            "result_runtime": "onnxruntime-1.28.0-cpu",
            "results": results,
            "row_count": sum(item.definition.batch for item in self.golden_records()),
            "schema_version": "openttd-rl-v2-m23-package-evaluation-1",
            "status": "PASS",
            "tolerance": {"absolute": 0.00005, "relative": 0.00005},
        }
        (stage / "evaluation.json").write_bytes(m23_package.canonical_json(evaluation, newline=True))
        (stage / "INSTALL.md").write_bytes(m23_package.install_text(self.contract["deployment_packages"]["format"]))
        (stage / "MODEL_CARD.md").write_bytes(m23_package.model_card_text(
            self.architecture, deployment["role"], checkpoint["checkpoint_id"],
        ))
        files = {name: m23_package.sha256_file(stage / name) for name in m23_package.PAYLOAD_FILES}
        graph = self.contract["deployment_packages"]["graph"]
        graph_value = {"inputs": graph["inputs"], "outputs": graph["outputs"], "training_nodes": False}
        provenance = {
            "contract_sha256": m23_package.sha256_file(self.root / contract_validator.CONTRACT),
            "equivalence_report_sha256": "4" * 64,
            "export_report_sha256": "6" * 64,
            "golden_binary_sha256": "5" * 64,
            "model_sha256": m23_package.sha256_file(stage / "model.onnx"),
        }
        manifest = m23_package.package_manifest(
            self.contract, deployment, checkpoint, graph_value, files, provenance,
        )
        package_id = m23_package.sha256_bytes(m23_package.canonical_json(manifest))
        manifest["package_id"] = package_id
        (stage / "manifest.json").write_bytes(m23_package.canonical_json(manifest))
        package = parent / package_id
        stage.rename(package)
        return package.resolve()

    def resign(self, package: pathlib.Path, mutate: object) -> pathlib.Path:
        manifest = m23_package.load_json(package / "manifest.json")
        mutate(manifest)  # type: ignore[operator]
        manifest.pop("package_id", None)
        package_id = m23_package.sha256_bytes(m23_package.canonical_json(manifest))
        manifest["package_id"] = package_id
        (package / "manifest.json").write_bytes(m23_package.canonical_json(manifest))
        destination = package.parent / package_id
        package.rename(destination)
        return destination.resolve()

    def refresh(self, package: pathlib.Path, filename: str) -> pathlib.Path:
        return self.resign(package, lambda value: value["files"].__setitem__(
            filename, m23_package.sha256_file(package / filename),
        ))

    def assert_rejected(self, package: pathlib.Path, pattern: str) -> None:
        with self.assertRaisesRegex(m23_package.M23PackageError, pattern):
            m23_package.validate_package(package, self.contract, inspect_graph=False)

    def test_fixture_package_passes_content_and_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            package = self.create_package(pathlib.Path(raw))
            summary = m23_package.validate_package(package, self.contract, inspect_graph=False)
            self.assertEqual(summary.architecture_id, self.architecture)
            self.assertEqual(summary.package_id, package.name)

    def test_manifest_is_canonical_and_package_id_excludes_only_itself(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            package = self.create_package(pathlib.Path(raw))
            value = m23_package.load_json(package / "manifest.json")
            observed = value.pop("package_id")
            self.assertEqual(observed, m23_package.sha256_bytes(m23_package.canonical_json(value)))
            self.assertNotIn(b"\n", (package / "manifest.json").read_bytes())

    def test_duplicate_json_bom_and_nonfinite_json_fail_closed(self) -> None:
        with self.assertRaisesRegex(m23_package.M23PackageError, "duplicate JSON key"):
            m23_package.load_json_bytes(b'{"a":1,"a":2}', "fixture")
        with self.assertRaisesRegex(m23_package.M23PackageError, "BOM"):
            m23_package.load_json_bytes(b"\xef\xbb\xbf{}", "fixture")
        with self.assertRaises(ValueError):
            m23_package.canonical_json({"bad": float("nan")})

    def test_manifest_compatibility_mutations_fail(self) -> None:
        mutations = {
            "format": lambda value: value.__setitem__("format", "mutated"),
            "version": lambda value: value.__setitem__("compatibility_version", 2),
            "architecture": lambda value: value.__setitem__("architecture_id", "mutated"),
            "architecture version": lambda value: value.__setitem__("architecture_version", 2),
            "checkpoint": lambda value: value.__setitem__("checkpoint_id", "0" * 64),
            "learning": lambda value: value.__setitem__("learning_contract_sha256", "0" * 64),
            "source": lambda value: value.__setitem__("source_tree_id", "0" * 40),
            "opset": lambda value: value.__setitem__("onnx_opset", 19),
            "runtime": lambda value: value.__setitem__("onnxruntime_version", "0.0.0"),
            "normalization": lambda value: value.__setitem__("normalization", "mutated"),
            "recurrent width": lambda value: value.__setitem__("recurrent_width", 128),
            "recurrent reset": lambda value: value.__setitem__("recurrent_reset_semantics", "mutated"),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                package = self.resign(self.create_package(pathlib.Path(raw)), mutation)
                self.assert_rejected(package, "compatibility|semantic|unsupported")

    def test_manifest_graph_signature_mutations_fail(self) -> None:
        mutations = (
            lambda value: value["graph"]["inputs"][0].__setitem__("name", "mutated"),
            lambda value: value["graph"]["inputs"][0].__setitem__("shape", ["batch", 99]),
            lambda value: value["graph"]["inputs"][0].__setitem__("dtype", "int64"),
            lambda value: value["graph"]["outputs"][0].__setitem__("name", "mutated"),
            lambda value: value["graph"]["outputs"][0].__setitem__("shape", ["batch", 99]),
            lambda value: value["graph"]["outputs"][0].__setitem__("dtype", "int64"),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as raw:
                package = self.resign(self.create_package(pathlib.Path(raw)), mutation)
                self.assert_rejected(package, "graph contract")

    def test_package_id_and_file_digest_mutations_fail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            package = self.create_package(pathlib.Path(raw))
            manifest = m23_package.load_json(package / "manifest.json")
            manifest["package_id"] = "0" * 64
            (package / "manifest.json").write_bytes(m23_package.canonical_json(manifest))
            self.assert_rejected(package, "identity|content address")
        with tempfile.TemporaryDirectory() as raw:
            package = self.resign(self.create_package(pathlib.Path(raw)),
                                  lambda value: value["files"].__setitem__("model.onnx", "0" * 64))
            self.assert_rejected(package, "payload digest")

    def test_missing_unknown_and_symlink_entries_fail(self) -> None:
        for label in ("missing", "unknown", "symlink"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                package = self.create_package(pathlib.Path(raw))
                if label == "missing":
                    (package / "golden.jsonl").unlink()
                elif label == "unknown":
                    (package / "unknown").write_text("x", encoding="ascii")
                else:
                    (package / "golden.jsonl").unlink()
                    (package / "golden.jsonl").symlink_to("evaluation.json")
                self.assert_rejected(package, "inventory|entry is invalid")

    def test_golden_definition_carry_and_illegal_action_mutations_fail(self) -> None:
        mutations = (
            (0, lambda value: value.__setitem__("seed", value["seed"] + 1), "definition"),
            (9, lambda value: value["hidden_input"].__setitem__(0, 1.0), "carried hidden"),
            (0, lambda value: value.__setitem__("greedy_program", [16]), "greedy program"),
        )
        for line_index, mutation, pattern in mutations:
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as raw:
                package = self.create_package(pathlib.Path(raw))
                lines = (package / "golden.jsonl").read_bytes().splitlines()
                value = m23_package.load_json_bytes(lines[line_index], "fixture")
                mutation(value)
                lines[line_index] = m23_package.canonical_json(value)
                (package / "golden.jsonl").write_bytes(b"\n".join(lines) + b"\n")
                package = self.refresh(package, "golden.jsonl")
                self.assert_rejected(package, pattern)

    def test_evaluation_status_case_and_tolerance_mutations_fail(self) -> None:
        mutations = (
            lambda value: value.__setitem__("status", "FAIL"),
            lambda value: value["results"].pop(),
            lambda value: value.__setitem__("tolerance", {"absolute": 1.0, "relative": 1.0}),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as raw:
                package = self.create_package(pathlib.Path(raw))
                value = m23_package.load_json(package / "evaluation.json")
                mutation(value)
                (package / "evaluation.json").write_bytes(m23_package.canonical_json(value, newline=True))
                package = self.refresh(package, "evaluation.json")
                self.assert_rejected(package, "evaluation")

    def test_document_host_path_leak_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            package = self.create_package(pathlib.Path(raw))
            (package / "INSTALL.md").write_bytes(b"/home/developer/secret\n")
            package = self.refresh(package, "INSTALL.md")
            self.assert_rejected(package, "forbidden")

    def test_builder_exact_copies_and_never_embeds_repository_commit(self) -> None:
        source = (self.root / "scripts/v2/m23_package.py").read_text(encoding="utf-8")
        self.assertIn("shutil.copyfile(source / name, destination / name)", source)
        self.assertIn("before == after", source)
        self.assertNotIn("repository_commit", source)
        self.assertIn("not output_root.exists()", source)

    def test_onnx_inspector_forbids_training_and_external_data(self) -> None:
        source = (self.root / "scripts/v2/m23_package.py").read_text(encoding="utf-8")
        self.assertIn("TRAINING_NODES", source)
        self.assertIn("ai.onnx.preview.training", source)
        self.assertIn("TensorProto.EXTERNAL", source)
        self.assertIn("onnx.checker.check_model(model, full_check=True)", source)

    def test_mutation_runner_implements_the_exact_frozen_matrix(self) -> None:
        source = (self.root / "scripts/v2/run_m23_package_mutations.py").read_text(encoding="utf-8")
        for label in self.contract["equivalence"]["rejection_matrix"]:
            self.assertIn(f'"{label}"', source)
        self.assertIn('contract["equivalence"]["rejection_matrix"]', source)
        self.assertIn("python_rejected and runtime_rejected", source)

    def test_cpp_loader_validates_identity_payloads_and_runtime_version(self) -> None:
        source = (self.root / "training/v2/src/m23_onnx.cpp").read_text(encoding="utf-8")
        for token in ("manifest_identity_payload", "validate_package_inventory", "m23_sha256_file",
                      "OrtGetApiBase()->GetVersionString()", "training_dependencies", "recurrent_width"):
            self.assertIn(token, source)
        self.assertIn("std::make_unique<M23OnnxModel>", source)

    def test_runtime_smoke_owns_all_request_rejections(self) -> None:
        source = (self.root / "training/v2/src/m23_package_smoke_main.cpp").read_text(encoding="utf-8")
        for probe in ("nonfinite", "all-illegal", "batch-zero", "batch-over-32"):
            self.assertIn(probe, source)
        cmake = (self.root / "training/v2/m23/CMakeLists.txt").read_text(encoding="utf-8")
        smoke_position = cmake.index("add_executable(m23_package_smoke")
        deployment_return = cmake.index("if(V2_M23_DEPLOYMENT_ONLY)")
        self.assertLess(smoke_position, deployment_return)


if __name__ == "__main__":
    unittest.main()
