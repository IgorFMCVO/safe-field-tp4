from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mvp import razer_worker_service as service


class Gate2DWorkerCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models = Path("frozen-models")
        self.asr = object()
        self.embedding = object()
        self.recovery = SimpleNamespace(embedding_provider=self.embedding)
        self.community_engine = SimpleNamespace(
            startup_metrics={"model_load_seconds": 5.25, "device": "cpu"},
            model_load_count=1,
        )
        self.community_bridge = object()

    def compose(self, selected: str):
        with (
            patch.object(service, "enable_cuda_dlls"),
            patch.object(service, "FrozenRecoveryASRProvider", return_value=self.asr),
            patch.object(service, "RecoveryDiarizer", return_value=self.recovery),
            patch.object(
                service.Community1DiarizerAdapter,
                "from_local_snapshot",
                return_value=self.community_engine,
            ) as factory,
            patch.object(
                service,
                "DiarizationProviderBridge",
                return_value=self.community_bridge,
            ) as bridge,
        ):
            providers, readiness = service.compose_frozen_worker_providers(
                self.models,
                diarization_engine=selected,
                community1_python=Path("community-python.exe"),
                community1_cache_root=Path("community-cache"),
                community1_model_snapshot=Path(service.COMMUNITY1_REVISION),
            )
        return providers, readiness, factory, bridge

    def test_community1_is_explicit_and_reuses_frozen_ecapa_for_identity(self):
        providers, readiness, factory, bridge = self.compose("community1")

        factory.assert_called_once()
        bridge.assert_called_once_with(self.community_engine, embedding_provider=self.embedding)
        self.assertIs(providers.asr, self.asr)
        self.assertIs(providers.diarization, self.community_bridge)
        self.assertIs(providers.embedding, self.embedding)
        self.assertEqual(readiness["diarization_engine"], "community1")
        self.assertEqual(readiness["observation_quality"], "ECAPA_REIDENTIFICATION_SEPARATE")
        self.assertIn("load_count1", readiness["diarization"])

    def test_recovery_rollback_does_not_start_community_runtime(self):
        providers, readiness, factory, bridge = self.compose("recovery")

        factory.assert_not_called()
        bridge.assert_not_called()
        self.assertIs(providers.diarization, self.recovery)
        self.assertIs(providers.embedding, self.embedding)
        self.assertEqual(readiness["diarization_engine"], "recovery")
        self.assertEqual(readiness["observation_quality"], "REQUIRED")

    def test_restart_selection_sequence_is_reversible_without_commit_revert(self):
        observed = []
        for selected in ("community1", "recovery", "community1"):
            providers, readiness, _, _ = self.compose(selected)
            observed.append((readiness["diarization_engine"], providers.diarization))

        self.assertEqual([item[0] for item in observed], ["community1", "recovery", "community1"])
        self.assertIs(observed[0][1], self.community_bridge)
        self.assertIs(observed[1][1], self.recovery)
        self.assertIs(observed[2][1], self.community_bridge)


if __name__ == "__main__":
    unittest.main(verbosity=2)
