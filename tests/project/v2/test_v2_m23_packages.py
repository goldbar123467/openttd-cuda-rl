#!/usr/bin/env python3
"""Package, content-address, source-boundary, and mutation tests for M23."""

from __future__ import annotations

import contextlib
import pathlib
import tempfile
import unittest
from collections.abc import Iterator

import m23_package
import validate_m23_release_contract as contract_validator
from tests.project.v2 import m23_fixture_support as fixtures


class M23PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = contract_validator.load(cls.root / contract_validator.CONTRACT)
        cls.architecture = contract_validator.ARCHITECTURES[0]
        cls._temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._temporary.cleanup)
        fixture_root = pathlib.Path(cls._temporary.name).resolve()
        cls.base_packages: dict[str, pathlib.Path] = {}
        cls.base_snapshots: dict[str, tuple[tuple[str, str], ...]] = {}
        for index, architecture in enumerate(contract_validator.ARCHITECTURES):
            parent = fixture_root / architecture
            parent.mkdir()
            package = fixtures.make_package(
                parent,
                cls.root,
                cls.contract,
                architecture,
                fixtures.make_golden_records(index),
            )
            cls.base_packages[architecture] = package
            cls.base_snapshots[architecture] = fixtures.snapshot_tree(package)

    @classmethod
    def tearDownClass(cls) -> None:
        for architecture, package in cls.base_packages.items():
            observed = fixtures.snapshot_tree(package)
            if observed != cls.base_snapshots[architecture]:
                raise AssertionError(f"M23 base package mutated: {architecture}")

    @contextlib.contextmanager
    def cloned_package(self, architecture: str | None = None) -> Iterator[pathlib.Path]:
        selected = architecture or self.architecture
        with tempfile.TemporaryDirectory() as raw:
            yield fixtures.clone_package(
                self.base_packages[selected], pathlib.Path(raw).resolve(),
            )

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
        package = self.base_packages[self.architecture]
        summary = m23_package.validate_package(package, self.contract, inspect_graph=False)
        self.assertEqual(summary.architecture_id, self.architecture)
        self.assertEqual(summary.package_id, package.name)

    def test_manifest_is_canonical_and_package_id_excludes_only_itself(self) -> None:
        package = self.base_packages[self.architecture]
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
        mutations = (
            ("package-format", lambda value: value.__setitem__("format", "mutated")),
            ("compatibility-version", lambda value: value.__setitem__("compatibility_version", 2)),
            ("architecture-id", lambda value: value.__setitem__("architecture_id", "mutated")),
            ("architecture-version", lambda value: value.__setitem__("architecture_version", 2)),
            ("checkpoint-id", lambda value: value.__setitem__("checkpoint_id", "0" * 64)),
            ("learning-contract-id", lambda value: value.__setitem__("learning_contract_sha256", "0" * 64)),
            ("source-tree-id", lambda value: value.__setitem__("source_tree_id", "0" * 40)),
            ("onnx-opset", lambda value: value.__setitem__("onnx_opset", 19)),
            ("onnxruntime-version", lambda value: value.__setitem__("onnxruntime_version", "0.0.0")),
            ("recurrent-width", lambda value: value.__setitem__("recurrent_width", 128)),
            ("recurrent-reset-semantics", lambda value: value.__setitem__("recurrent_reset_semantics", "mutated")),
            ("normalization", lambda value: value.__setitem__("normalization", "mutated")),
        )
        for label, mutation in mutations:
            with self.subTest(label=label), self.cloned_package() as package:
                package = self.resign(package, mutation)
                self.assert_rejected(package, "compatibility|semantic|unsupported")

    def test_manifest_graph_signature_mutations_fail(self) -> None:
        mutations = (
            ("input-name", lambda value: value["graph"]["inputs"][0].__setitem__("name", "mutated")),
            ("input-shape", lambda value: value["graph"]["inputs"][0].__setitem__("shape", ["batch", 99])),
            ("input-dtype", lambda value: value["graph"]["inputs"][0].__setitem__("dtype", "int64")),
            ("output-name", lambda value: value["graph"]["outputs"][0].__setitem__("name", "mutated")),
            ("output-shape", lambda value: value["graph"]["outputs"][0].__setitem__("shape", ["batch", 99])),
            ("output-dtype", lambda value: value["graph"]["outputs"][0].__setitem__("dtype", "int64")),
        )
        for label, mutation in mutations:
            with self.subTest(label=label), self.cloned_package() as package:
                package = self.resign(package, mutation)
                self.assert_rejected(package, "graph contract")

    def test_package_id_and_file_digest_mutations_fail(self) -> None:
        with self.subTest(label="package-id"), self.cloned_package() as package:
            manifest = m23_package.load_json(package / "manifest.json")
            manifest["package_id"] = "0" * 64
            (package / "manifest.json").write_bytes(m23_package.canonical_json(manifest))
            self.assert_rejected(package, "identity|content address")
        with self.subTest(label="file-digest"), self.cloned_package() as package:
            package = self.resign(
                package, lambda value: value["files"].__setitem__("model.onnx", "0" * 64),
            )
            self.assert_rejected(package, "payload digest")

    def test_missing_unknown_and_symlink_entries_fail(self) -> None:
        for label in ("missing-file", "unknown-file", "symlink"):
            with self.subTest(label=label), self.cloned_package() as package:
                if label == "missing-file":
                    (package / "golden.jsonl").unlink()
                elif label == "unknown-file":
                    (package / "unknown").write_text("x", encoding="ascii")
                else:
                    (package / "golden.jsonl").unlink()
                    (package / "golden.jsonl").symlink_to("evaluation.json")
                self.assert_rejected(package, "inventory|entry is invalid")

    def test_golden_definition_carry_and_illegal_action_mutations_fail(self) -> None:
        mutations = (
            ("golden-definition", 0, lambda value: value.__setitem__("seed", value["seed"] + 1), "definition"),
            ("carried-hidden", 9, lambda value: value["hidden_input"].__setitem__(0, 1.0), "carried hidden"),
            ("illegal-action", 0, lambda value: value.__setitem__("greedy_program", [16]), "greedy program"),
        )
        for label, line_index, mutation, pattern in mutations:
            with self.subTest(label=label), self.cloned_package() as package:
                lines = (package / "golden.jsonl").read_bytes().splitlines()
                value = m23_package.load_json_bytes(lines[line_index], "fixture")
                mutation(value)
                lines[line_index] = m23_package.canonical_json(value)
                (package / "golden.jsonl").write_bytes(b"\n".join(lines) + b"\n")
                package = self.refresh(package, "golden.jsonl")
                self.assert_rejected(package, pattern)

    def test_evaluation_status_case_and_tolerance_mutations_fail(self) -> None:
        mutations = (
            ("evaluation-status", lambda value: value.__setitem__("status", "FAIL")),
            ("evaluation-case", lambda value: value["results"].pop()),
            ("evaluation-tolerance", lambda value: value.__setitem__("tolerance", {"absolute": 1.0, "relative": 1.0})),
        )
        for label, mutation in mutations:
            with self.subTest(label=label), self.cloned_package() as package:
                value = m23_package.load_json(package / "evaluation.json")
                mutation(value)
                (package / "evaluation.json").write_bytes(m23_package.canonical_json(value, newline=True))
                package = self.refresh(package, "evaluation.json")
                self.assert_rejected(package, "evaluation")

    def test_document_host_path_leak_fails(self) -> None:
        with self.subTest(label="host-path"), self.cloned_package() as package:
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
