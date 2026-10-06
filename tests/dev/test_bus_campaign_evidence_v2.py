"""Evidence archives and held-out corpus adapters fail closed on changed data."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_action_inputs_v2 import artifact
from compare_human_imitation_v2 import corpus
from evaluate_bus_orders_campaign_v2 import archive_metadata


class BusCampaignEvidenceTests(unittest.TestCase):
    def test_archiving_preserves_complete_metadata_and_hash_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            path = artifacts / "tensors-000001-observation.json"
            original = json.dumps({"binary": {"sha256": "example"}, "records": list(range(128))}).encode()
            path.write_bytes(original)
            archive_metadata(root)
            self.assertFalse(path.exists())
            with gzip.open(path.with_suffix(".json.gz"), "rb") as stream:
                self.assertEqual(stream.read(), original)
            rows = json.loads((root / "metadata-archives.json").read_text())
            self.assertEqual(rows[0]["archive"], artifact(path.with_suffix(".json.gz")))

    def fixture(self, root):
        refs = {}
        for name in ("source", "replay", "metadata", "transfer", "obs", "cand"):
            path = root / (name + ".bin")
            path.write_bytes(name.encode())
            refs[name] = artifact(path)
        export = {"source_dataset": refs["source"], "replay_validation": refs["replay"],
                  "recording_metadata": refs["metadata"], "capture_transfer": refs["transfer"],
                  "example_count": 1, "split": "test", "records": [{"split": "test", "sample_id": "one",
                  "verified_tensors": {"observation": refs["obs"], "candidates": refs["cand"]}}]}
        path = root / "export.json"
        path.write_text(json.dumps(export))
        report = root / "report.json"
        report.write_text(json.dumps({"kind": "native-human-evaluation-audit", "status": "passed",
                                      "split": "test", "example_count": 1, "dataset": artifact(path)}))
        return report, export, path

    def test_read_only_test_corpus_keeps_partition_and_delegates_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, export, _ = self.fixture(root)
            with patch("audit_human_evaluation_v2.validate", return_value=export) as validate:
                labels, tensors, _ = corpus(report)
            validate.assert_called_once_with(Path(export["source_dataset"]["path"]), "test")
            self.assertEqual(labels[0]["split"], "test")
            self.assertEqual(tensors[0], labels[0]["archived_tensors"])
            self.assertFalse((root / "native-imitation.tsv").exists())

    def test_changed_evaluation_export_cannot_override_revalidation(self):
        with tempfile.TemporaryDirectory() as temporary:
            report, export, path = self.fixture(Path(temporary))
            corrupted = {**export, "example_count": 2}
            path.write_text(json.dumps(corrupted))
            data = json.loads(report.read_text())
            data["dataset"] = artifact(path)
            report.write_text(json.dumps(data))
            with patch("audit_human_evaluation_v2.validate", return_value=export):
                with self.assertRaisesRegex(ValueError, "exact integrity audit"):
                    corpus(report)


if __name__ == "__main__":
    unittest.main()
