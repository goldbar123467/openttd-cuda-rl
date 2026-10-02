"""The replay auditor must read actual archived inputs and reject corruption."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from compare_v2_resume import binary_digest, canonical_transition, check_coverage, owned_path, saved_checkpoint


class ResumeInputAuditTests(unittest.TestCase):
    def test_cross_run_evidence_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            own, other = root / "resumed", root / "original"
            own.mkdir(); other.mkdir()
            self.assertEqual(owned_path(own / "input.bin", own), own / "input.bin")
            with self.assertRaisesRegex(ValueError, "outside its own run"):
                owned_path(other / "input.bin", own)

    def test_identically_truncated_or_reordered_traces_are_not_complete(self):
        updates = [{"update": 3, "transitions": 384}, {"update": 4, "transitions": 512}]
        rows = [{"step": i} for i in range(257, 513)]
        boundary = {"update": 2, "transitions": 256}
        check_coverage(updates, rows, boundary, 4, 128)
        for bad in (rows[:-1], rows[1:], rows[::-1], rows + rows[-1:]):
            with self.assertRaisesRegex(ValueError, "trajectory"):
                check_coverage(updates, bad, boundary, 4, 128)
        with self.assertRaisesRegex(ValueError, "updates"):
            check_coverage(updates[1:], rows, boundary, 4, 128)

    def test_mutated_checkpoint_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "trainer.pt").write_bytes(b"checkpoint")
            manifest = root / "checkpoint.json"
            manifest.write_text(json.dumps({"update": 2, "trainer_sha256": hashlib.sha256(b"checkpoint").hexdigest()}))
            entry = {"path": str(root), "update": 2, "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
            saved_checkpoint(entry)
            manifest.write_text(manifest.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "manifest digest"):
                saved_checkpoint(entry)

    def test_plain_and_archived_payloads_are_hash_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.bin"
            payload = b"actual input bytes"
            expected = hashlib.sha256(payload).hexdigest()
            path.write_bytes(payload)
            self.assertEqual(binary_digest(path, expected), expected)
            path.unlink()
            Path(str(path) + ".gz").write_bytes(gzip.compress(payload))
            self.assertEqual(binary_digest(path, expected), expected)
            with self.assertRaisesRegex(ValueError, "digest differs"):
                binary_digest(path, "0" * 64)

    def test_path_and_duration_normalization_preserves_decision_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "data.bin"
            path.write_bytes(b"evidence")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            meta = root / "data.json"
            meta.write_text(json.dumps({"binary": {"file": path.name, "sha256": expected}}))
            row = {"step": 257, "prediction": {"row": 3842, "log_probability": -.3},
                   "transition": {"after": {"balance": 10000}}, "inference_elapsed_ns": 17,
                   "observation_metadata": str(meta), "candidates_metadata": str(meta),
                   "guidance": {"sampling_binary": str(path), "sampling_binary_sha256": expected}}
            result = canonical_transition(row, root)
            self.assertEqual(result["prediction"], row["prediction"])
            self.assertEqual(result["transition"], row["transition"])
            self.assertEqual(result["observation_metadata_sha256"], expected)
            self.assertNotIn("inference_elapsed_ns", result)
            self.assertIn("sampling_binary", row["guidance"])
            path.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "digest differs"):
                canonical_transition(row, root)


if __name__ == "__main__":
    unittest.main()
