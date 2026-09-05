from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mvp.tests.run_neural_speaker_reid_validation import (
    EXPECTED_MODEL,
    REQUIRED_MODEL_FILES,
    audit_model_bundle,
    nearest_rank,
)


class NeuralSpeakerValidationHelperTests(unittest.TestCase):
    def test_nearest_rank_keeps_cold_outlier_in_small_p95(self) -> None:
        observations = [float(value) for value in range(1, 16)] + [2165.0]
        self.assertEqual(nearest_rank(observations, 0.95), 2165.0)
        self.assertEqual(nearest_rank(observations[:-1], 0.95), 15.0)

    def test_model_manifest_uses_real_files_revision_and_dimension_independent_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in REQUIRED_MODEL_FILES:
                (root / name).write_bytes(f"fixture:{name}".encode("utf-8"))
            (root / "hyperparams.yaml").write_text(
                f"pretrained_path: {EXPECTED_MODEL}\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text('license: "apache-2.0"\n', encoding="utf-8")
            tree = root / ".cache" / "huggingface" / "trees"
            tree.mkdir(parents=True)
            (tree / "revision123.json").write_text(json.dumps({"format_version": 1}), encoding="utf-8")

            manifest = audit_model_bundle(root)

            self.assertEqual(manifest["source_repository"], EXPECTED_MODEL)
            self.assertEqual(manifest["source_revisions"], ["revision123"])
            self.assertEqual(manifest["license"], "apache-2.0")
            self.assertEqual(len(manifest["manifest_sha256"]), 64)
            self.assertIn("embedding_model.ckpt", {item["name"] for item in manifest["files"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
