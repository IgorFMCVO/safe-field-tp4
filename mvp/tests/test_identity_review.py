from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mvp.operational_intelligence.identity_review import (
    build_identity_review,
    confirm_identity,
    extract_identity_cues,
    persist_identity_cues,
)
from mvp.operational_intelligence.models import TranscriptSegment
from mvp.operational_intelligence.storage import SESSION_DIRECTORIES, atomic_json


class IdentityReviewTests(unittest.TestCase):
    def test_explicit_name_cues_remain_inferred_until_officer_confirmation(self):
        text = (
            "Fale Ana Monteiro, agora fale você Joao, qual o seu nome? "
            "Meu nome é Joao Pereira."
        )
        cues = extract_identity_cues(
            text,
            "segment_0001",
            ["SPEAKER_01", "UNVERIFIED_segment_0001_02"],
        )
        found = {(item["cue_type"], item["candidate_name"]) for item in cues}
        self.assertIn(("OFFICER_CUE", "Ana Monteiro"), found)
        self.assertIn(("OFFICER_CUE", "Joao"), found)
        self.assertIn(("SELF_DECLARED", "Joao Pereira"), found)
        self.assertTrue(all(item["evidence_status"] == "INFERRED" for item in cues))
        self.assertTrue(all(item["validation_status"] == "PENDING" for item in cues))

    def test_low_quality_observation_requires_review_but_does_not_block_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in SESSION_DIRECTORIES:
                (root / name).mkdir(parents=True, exist_ok=True)
            atomic_json(root / "speakers" / "registry.json", {"speakers": []})
            speaker_id = "UNVERIFIED_segment_0001_01"
            atomic_json(
                root / "speakers" / f"segment_0001_{speaker_id}.json",
                {
                    "segment_id": "segment_0001",
                    "local_speaker": "SPEAKER_00",
                    "speaker_id": speaker_id,
                    "status": "UNVERIFIED_LOW_QUALITY",
                    "reason": "LOW_QUALITY",
                    "quality": {"confidence": 0.637},
                },
            )
            transcript = TranscriptSegment(
                segment_id="segment_0001",
                speaker_ids=[speaker_id],
                start=0.0,
                end=3.0,
                raw_transcript="Meu nome é Ana Monteiro.",
                asr_confidence=0.91,
                audio_path=str(root / "segments" / "segment_0001.wav"),
            )
            atomic_json(
                root / "transcripts" / "segment_0001.json",
                transcript.to_dict(),
            )
            cues = persist_identity_cues(root, transcript)
            review = build_identity_review(root)

            self.assertEqual(review["status"], "REQUIRES_IDENTITY_VALIDATION")
            self.assertFalse(review["report_finalization_allowed"])
            self.assertGreaterEqual(review["pending_count"], 2)
            self.assertTrue(cues)

            confirmation = confirm_identity(
                root,
                [speaker_id],
                "Ana Monteiro",
                cue_ids=[item["cue_id"] for item in cues],
            )
            self.assertEqual(confirmation["status"], "OFFICER_CONFIRMED")
            review = build_identity_review(root)
            self.assertEqual(review["pending_count"], 0)
            self.assertTrue(review["report_finalization_allowed"])
            self.assertEqual(
                review["confirmed_identity_by_speaker"][speaker_id],
                "Ana Monteiro",
            )

    def test_unknown_speaker_cannot_be_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in SESSION_DIRECTORIES:
                (root / name).mkdir(parents=True, exist_ok=True)
            atomic_json(root / "speakers" / "registry.json", {"speakers": []})
            with self.assertRaises(ValueError):
                confirm_identity(root, ["SPEAKER_99"], "Pessoa Inexistente")


if __name__ == "__main__":
    unittest.main()
