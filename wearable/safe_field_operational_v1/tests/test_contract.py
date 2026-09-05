from pathlib import Path
import re
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from contract_model import (  # noqa: E402
    ACTION_STATUSES,
    ROUTES,
    WearableModel,
    transport_ready,
)


SOURCE = (ROOT / "safe_field_operational_v1.ino").read_text(encoding="utf-8")
BUILD_SOURCE = (ROOT / "BUILD.ps1").read_text(encoding="utf-8")


class FirmwareSurfaceTests(unittest.TestCase):
    def test_exact_versioned_routes_are_compiled(self):
        for method, route in ROUTES.values():
            self.assertIn(f'"{route}"', SOURCE)
            if method == "POST":
                self.assertIn("http.POST(", SOURCE)

    def test_required_operational_labels_are_present(self):
        for label in (
            "STANDBY",
            "INICIAR OCORRENCIA",
            "OCORRENCIA ATIVA",
            "CAPTURA CONTINUA",
            "HIPOTESE PROPOSTA",
            "CONFIRMAR",
            "DESCARTAR",
            "MAIS DADOS",
            "PRIORIDADES",
            "REALIZADO",
            "PENDENTE",
            "NAO APLICAVEL",
            "REAVALIACAO NECESSARIA",
            "FINALIZAR OCORRENCIA",
            "FINALIZANDO",
            "CAPTURA ENCERRADA",
            "TENTAR FINALIZAR",
            "FALHA NA CAPTURA",
            "INTEGRIDADE PCM",
            "HISTORICO NAO GERADO",
        ):
            self.assertIn(label, SOURCE)

    def test_audio_activity_never_gates_capture(self):
        self.assertIn("FPGA VAD IS TELEMETRY ONLY", SOURCE)
        self.assertNotRegex(SOURCE, r'wearableState\s*==\s*"AUDIO_(QUIET|ACTIVE)"')

    def test_guidance_preserves_source_metadata(self):
        for field in ("source_document", "source_version", "section", "page", "item", "chunk_id"):
            self.assertIn(f'"{field}"', SOURCE)
        self.assertIn('hypothesisStatus == "OFFICER_CONFIRMED"', SOURCE)

    def test_no_camera_or_hardcoded_network_secret(self):
        self.assertNotIn("CAMERA_", SOURCE)
        self.assertNotIn("CAPTURE_PHOTO", SOURCE)
        self.assertNotRegex(SOURCE, r"192\.168\.\d+\.\d+")
        self.assertIn('preferences.getString("psk", "")', SOURCE)
        self.assertIn("password=REDACTED", SOURCE)

    def test_bearer_token_is_nvs_only_redacted_and_used_for_get_and_post(self):
        self.assertIn('preferences.getString("api_token", "")', SOURCE)
        self.assertIn('preferences.putString("api_token", apiToken)', SOURCE)
        self.assertIn('http.addHeader("Authorization", String("Bearer ") + apiToken)', SOURCE)
        self.assertGreaterEqual(SOURCE.count("addAuthorization(http)"), 2)
        self.assertIn("token=REDACTED", SOURCE)
        self.assertNotRegex(SOURCE, r'apiToken\s*=\s*"[^\"]+"')

    def test_bearer_transport_requires_validated_https_and_nvs_ca(self):
        self.assertIn("#include <WiFiClientSecure.h>", SOURCE)
        self.assertIn('preferences.getString("core_ca", "")', SOURCE)
        self.assertIn('preferences.putString("core_ca", candidate)', SOURCE)
        self.assertIn("tlsClient.setCACert(coreCaPem.c_str())", SOURCE)
        self.assertGreaterEqual(SOURCE.count("beginSecureHttp(http, tlsClient"), 2)
        self.assertIn("HTTPC_DISABLE_FOLLOW_REDIRECTS", SOURCE)
        self.assertIn("HTTPS_CORE_REQUIRED", SOURCE)
        self.assertIn("CA_CERT_REQUIRED", SOURCE)
        self.assertIn("bearer=NOT_SENT", SOURCE)
        self.assertNotIn("setInsecure", SOURCE)
        self.assertNotRegex(SOURCE, r"http\.begin\(\s*(?:coreBaseUrl|url)")

    def test_serial_provisioning_requires_https_and_redacts_ca(self):
        self.assertIn('command.startsWith("SET_CA_PEM ")', SOURCE)
        self.assertIn('command == "CLEAR_CA"', SOURCE)
        self.assertIn("requires https:// origin", SOURCE)
        self.assertNotIn("requires local http://", SOURCE)
        self.assertIn("ca=SET_REDACTED", SOURCE)

    def test_unauthorized_response_fails_closed(self):
        self.assertGreaterEqual(SOURCE.count("status == 401"), 2)
        self.assertIn("AUTORIZACAO NEGADA", SOURCE)
        self.assertIn("AUTH NECESSARIA", SOURCE)

    def test_official_ft3168_bsp_is_used(self):
        self.assertIn("Arduino_FT3x68", SOURCE)
        self.assertIn("FT3168_DEVICE_ADDRESS", SOURCE)
        self.assertIn("TP_INT", SOURCE)

    def test_stopping_preserves_explicit_capture_false(self):
        self.assertIn('const bool captureFlagPresent = jsonHasKey(payload, "capture_active")', SOURCE)
        self.assertIn('nextState == "STOPPING"', SOURCE)
        self.assertIn('serverState == "PROCESSING_PENDING" && captureFlagPresent && !captureActive', SOURCE)
        self.assertIn('!captureFlagPresent && occurrenceId.length() && !finalizationPending', SOURCE)

    def test_finish_timeout_and_pending_result_are_explicit(self):
        self.assertIn("kFinishProcessingTimeoutSeconds = 1.0f", SOURCE)
        self.assertIn("kFinishHttpTimeoutMs = 3500", SOURCE)
        self.assertIn("PostResult::PROCESSING_PENDING", SOURCE)
        self.assertIn('jsonBoolValue(payload, "retryable", false)', SOURCE)

    def test_pcm_integrity_failure_has_terminal_explicit_ui(self):
        self.assertIn("PostResult::CAPTURE_FAILED", SOURCE)
        self.assertIn('serverState == "CAPTURE_FAILED"', SOURCE)
        self.assertIn("UiMode::CAPTURE_FAILED", SOURCE)
        self.assertIn("renderCaptureFailed()", SOURCE)
        self.assertIn("FINALIZAR CAPTURA", SOURCE)
        self.assertIn("captureActive && !sourceQuiescent && y >= 414", SOURCE)
        self.assertIn("source_already_quiescent capture_failure_is_terminal", SOURCE)

    def test_apply_json_is_disabled_by_default_and_opt_in_only(self):
        self.assertIn("#define SAFE_FIELD_ENABLE_TEST_HOOKS 0", SOURCE)
        self.assertIn("#if SAFE_FIELD_ENABLE_TEST_HOOKS", SOURCE)
        self.assertIn("ERR APPLY_JSON disabled_in_production", SOURCE)
        self.assertIn("[switch]$EnableTestHooks", BUILD_SOURCE)
        self.assertIn("-DSAFE_FIELD_ENABLE_TEST_HOOKS=1", BUILD_SOURCE)


class ContractBehaviorTests(unittest.TestCase):
    _CA = (
        "-----BEGIN CERTIFICATE-----\n"
        + "A" * 80
        + "\n-----END CERTIFICATE-----\n"
    )

    def test_transport_gate_accepts_only_https_bearer_and_ca(self):
        self.assertTrue(transport_ready("https://safe-field.local:8770", "token", self._CA))
        self.assertFalse(transport_ready("http://safe-field.local:8770", "token", self._CA))
        self.assertFalse(transport_ready("https://safe-field.local:8770", "", self._CA))
        self.assertFalse(transport_ready("https://safe-field.local:8770", "token", ""))
        self.assertFalse(transport_ready("https://user@safe-field.local", "token", self._CA))
        self.assertFalse(transport_ready("https://safe-field.local/path", "token", self._CA))
        self.assertFalse(transport_ready("https://safe-field.local:bad", "token", self._CA))
        self.assertFalse(transport_ready("https://safe-field%0a.local", "token", self._CA))

    def test_start_audio_telemetry_finish_lifecycle(self):
        model = WearableModel()
        model.apply({"state": "OCCURRENCE_ACTIVE", "occurrence_id": "OCC_1", "capture_active": True})
        self.assertTrue(model.capture_active)
        model.apply({"state": "AUDIO_QUIET"})
        self.assertTrue(model.capture_active)
        model.apply({"state": "AUDIO_ACTIVE"})
        self.assertTrue(model.capture_active)
        model.apply({"state": "STANDBY", "capture_active": False})
        self.assertFalse(model.capture_active)

    def test_guidance_is_hidden_until_officer_confirmation(self):
        model = WearableModel(capture_active=True)
        guidance = {"items": [{"action_id": "A1", "text": "fixture"}]}
        model.apply({
            "state": "HYPOTHESIS_PROPOSED",
            "hypothesis": {"hypothesis_id": "H1", "status": "PROPOSED"},
            "guidance": guidance,
        })
        self.assertFalse(model.guidance_visible)
        model.apply({
            "state": "GUIDANCE_READY",
            "hypothesis": {"hypothesis_id": "H1", "status": "OFFICER_CONFIRMED"},
            "guidance": guidance,
        })
        self.assertTrue(model.guidance_visible)

    def test_all_action_statuses_are_accepted_only_with_guidance(self):
        model = WearableModel(guidance_visible=True)
        for index, status in enumerate(sorted(ACTION_STATUSES)):
            model.mark_action(f"A{index}", status)
        self.assertEqual(set(model.action_status.values()), ACTION_STATUSES)
        with self.assertRaises(ValueError):
            model.mark_action("BAD", "UNKNOWN")

    def test_reassessment_is_explicit(self):
        model = WearableModel(capture_active=True)
        model.apply({"state": "REASSESSMENT_REQUIRED", "capture_active": True})
        self.assertEqual(model.state, "REASSESSMENT_REQUIRED")
        self.assertTrue(model.capture_active)

    def test_http_401_sets_explicit_auth_failure(self):
        model = WearableModel()
        model.apply_http_status(401)
        self.assertTrue(model.auth_failed)
        model.apply_http_status(200)
        self.assertFalse(model.auth_failed)

    def test_stopping_normalizes_and_keeps_capture_closed(self):
        model = WearableModel(
            capture_active=True,
            occurrence_id="OCC_1",
            hypothesis_status="PROPOSED",
        )
        model.apply({
            "ok": False,
            "state": "STOPPING",
            "occurrence_id": "OCC_1",
            "capture_active": False,
            "finalization_pending": True,
            "retryable": True,
        })
        self.assertEqual(model.state, "PROCESSING_PENDING")
        self.assertFalse(model.capture_active)
        self.assertTrue(model.finalization_pending)
        self.assertEqual(model.visible_mode(), "PROCESSING_PENDING")

    def test_processing_pending_can_still_have_active_capture(self):
        model = WearableModel(occurrence_id="OCC_1")
        model.apply({"state": "PROCESSING_PENDING", "capture_active": True})
        self.assertTrue(model.capture_active)
        self.assertFalse(model.finalization_pending)

    def test_2xx_retryable_stop_is_not_discarded_as_error(self):
        payload = {"ok": False, "state": "STOPPING", "retryable": True}
        self.assertEqual(WearableModel.classify_post(200, payload), "PROCESSING_PENDING")
        self.assertEqual(WearableModel.classify_post(409, payload), "ERROR")
        self.assertEqual(WearableModel.classify_post(200, {"ok": True}), "ACCEPTED")

    def test_non_retryable_pcm_failure_is_not_standby_or_finalizing(self):
        payload = {
            "ok": False,
            "state": "CAPTURE_FAILED",
            "lifecycle_state": "STOPPING",
            "capture_active": False,
            "source_quiescent": True,
            "retryable": False,
        }
        self.assertEqual(WearableModel.classify_post(409, payload), "CAPTURE_FAILED")
        model = WearableModel(capture_active=True, occurrence_id="OCC_1")
        model.apply(payload)
        self.assertEqual(model.visible_mode(), "CAPTURE_FAILED")
        self.assertFalse(model.capture_active)
        self.assertTrue(model.source_quiescent)
        self.assertFalse(model.finalization_pending)
        self.assertFalse(model.can_finalize_failed_capture())

    def test_active_pcm_failure_remains_stoppable_until_source_is_quiescent(self):
        model = WearableModel(capture_active=True, source_quiescent=False,
                              occurrence_id="OCC_1")
        model.apply({
            "ok": False,
            "state": "CAPTURE_FAILED",
            "lifecycle_state": "ACTIVE",
            "capture_active": True,
            "source_quiescent": False,
            "retryable": False,
        })
        self.assertEqual(model.visible_mode(), "CAPTURE_FAILED")
        self.assertTrue(model.capture_active)
        self.assertFalse(model.source_quiescent)
        self.assertTrue(model.can_finalize_failed_capture())

        model.apply({
            "ok": False,
            "state": "CAPTURE_FAILED",
            "lifecycle_state": "STOPPING",
            "capture_active": False,
            "source_quiescent": True,
            "retryable": False,
        })
        self.assertFalse(model.capture_active)
        self.assertTrue(model.source_quiescent)
        self.assertFalse(model.can_finalize_failed_capture())


if __name__ == "__main__":
    unittest.main(verbosity=2)
