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
    def test_increment_one_capture_contract_is_explicit(self):
        for route in (
            "/api/v1/occurrences/captures/start",
            "/api/v1/occurrences/captures/stop",
            "/api/v1/occurrences/conclude",
        ):
            self.assertIn(f'"{route}"', SOURCE)
        for label in ("PARAR CAPTURA", "NOVA CAPTURA", "CONCLUIR"):
            self.assertIn(label, SOURCE)
        self.assertIn("UiMode::OCCURRENCE_OPEN", SOURCE)
        self.assertIn('serverState == "OCCURRENCE_OPEN"', SOURCE)

    def test_control_https_runs_off_the_touch_render_loop(self):
        self.assertIn("xTaskCreatePinnedToCore", SOURCE)
        self.assertIn("xQueueCreate", SOURCE)
        self.assertIn("controlRequestQueued", SOURCE)
        self.assertIn("serviceControlResponses", SOURCE)

    def test_commands_and_state_snapshots_are_recoverable(self):
        self.assertIn('\\"command_id\\":\\"', SOURCE)
        self.assertIn("stateRevision", SOURCE)
        self.assertIn("coreBootId", SOURCE)
        self.assertIn("POLL_STALE", SOURCE)
        self.assertIn("CORE_BOOT_CHANGED", SOURCE)

    def test_exact_versioned_routes_are_compiled(self):
        for method, route in ROUTES.values():
            self.assertIn(f'"{route}"', SOURCE)
            if method == "POST":
                self.assertIn("http.POST(", SOURCE)

    def test_required_operational_labels_are_present(self):
        for label in (
            "STANDBY",
            "EM ATENDIMENTO",
            "OCORRENCIA ATIVA",
            "CAPTURA CONTINUA",
            "CAPTURA ATIVA - ESCUTA CONTINUA",
            "HIPOTESE PROPOSTA",
            "CONFIRMAR",
            "RECUSAR",
            "MAIS DADOS",
            "PROCEDIMENTOS",
            "REALIZADO",
            "PENDENTE",
            "NAO APLICAVEL",
            "REAVALIACAO NECESSARIA",
            "ENCERRAR ATENDIMENTO",
            "FINALIZANDO",
            "INICIANDO CAPTURA",
            "INICIANDO",
            "FALE AGORA",
            "PROCESSANDO...",
            "TOQUE ACEITO",
            "VALIDANDO TOQUE",
            "VALIDANDO COM O CORE",
            "CAPTURA ENCERRADA",
            "TENTAR ENCERRAR",
            "FALHA NA CAPTURA",
            "INTEGRIDADE PCM",
            "HISTORICO NAO GERADO",
        ):
            self.assertIn(label, SOURCE)

    def test_audio_activity_never_gates_capture(self):
        self.assertIn("FPGA VAD IS TELEMETRY ONLY", SOURCE)
        self.assertNotRegex(SOURCE, r'wearableState\s*==\s*"AUDIO_(QUIET|ACTIVE)"')

    def test_touch_coordinate_mapping_is_explicit_and_traceable(self):
        self.assertIn("const int32_t y = rawY", SOURCE)
        self.assertIn("TOUCH_DOWN raw_x=%ld raw_y=%ld ui_x=%ld ui_y=%ld", SOURCE)
        self.assertIn("y <= 480", SOURCE)

    def test_touch_initialization_is_bounded_retry_not_single_early_probe(self):
        self.assertIn("attempt <= 10 && !touchReady", SOURCE)
        self.assertIn("FT3168 retry %u/10", SOURCE)

    def test_touch_stays_active_and_has_hardware_edge_fallback(self):
        self.assertIn("TOUCH_POWER_ACTIVE", SOURCE)
        self.assertIn("attachInterrupt(digitalPinToInterrupt(TP_INT)", SOURCE)
        self.assertIn("const bool directFallingEdge", SOURCE)

    def test_touch_recovers_without_watch_reboot(self):
        self.assertIn("bool initializeTouchController(bool recovery)", SOURCE)
        self.assertIn("FT3168 RECOVERY PROBE FAILED", SOURCE)
        self.assertIn("PASS FT3168 RECOVERED", SOURCE)

    def test_standby_after_stop_releases_processing_screen(self):
        self.assertIn('if (serverState == "STANDBY") {', SOURCE)
        self.assertIn('if (stopAwaitingCore) {', SOURCE)
        self.assertIn('CAPTURE_LATENCY stop_to_standby', SOURCE)

    def test_request_error_is_reconciled_by_authoritative_poll(self):
        self.assertIn("START_ERROR_RECONCILE_CORE", SOURCE)
        self.assertIn("STOP_ERROR_RECONCILE_CORE", SOURCE)
        self.assertIn("CORE_RECONCILED_STANDBY", SOURCE)
        self.assertIn("CORE_RECONCILED_CAPTURE_ACTIVE", SOURCE)
        self.assertIn("reconcilePending", SOURCE)

    def test_touch_audit_events_cover_one_post_per_action(self):
        for event in ("TOUCH_DOWN", "TOUCH_START", "START_SENT", "START_ACK",
                      "TOUCH_STOP", "STOP_SENT", "STOP_ACK"):
            self.assertIn(event, SOURCE)

    def test_saved_result_is_read_only_and_does_not_block_standby(self):
        api_source = Path("mvp/operational_intelligence/http_api.py").read_text(encoding="utf-8")
        self.assertIn('"last_result"', api_source)
        self.assertIn("UiMode::SAVED_RESULT", SOURCE)
        self.assertIn("RESULTADO PRONTO", SOURCE)
        self.assertIn("TOUCH_SUGGESTION", SOURCE)

    def test_touch_feedback_is_flushed_before_http(self):
        self.assertIn("startHttpNotBeforeMs = now + 80", SOURCE)
        self.assertIn("stopHttpNotBeforeMs = tStopTap + 80", SOURCE)
        self.assertIn("void serviceDeferredRequests()", SOURCE)
        self.assertIn("Flush touch acknowledgement before any potentially slow HTTPS", SOURCE)

    def test_guidance_preserves_source_metadata(self):
        for field in ("source_document", "source_version", "section", "page", "item", "chunk_id"):
            self.assertIn(f'"{field}"', SOURCE)
        self.assertIn('hypothesisStatus == "OFFICER_CONFIRMED"', SOURCE)

    def test_guidance_is_unbounded_and_touch_scrollable(self):
        self.assertIn("std::vector<GuidanceItem> guidance", SOURCE)
        self.assertNotIn("kMaxGuidanceItems", SOURCE)
        self.assertIn("while (cursor < static_cast<int>(items.length()))", SOURCE)
        self.assertIn("void scrollGuidance(int8_t direction)", SOURCE)
        self.assertIn("guidanceScrollOffset", SOURCE)
        self.assertIn("PROCEDIMENTOS", SOURCE)

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
        # The official BSP is retained; the operational firmware intentionally
        # keeps the controller scanning in ACTIVE mode for reliable dispatch.
        self.assertIn("TOUCH_POWER_ACTIVE", SOURCE)
        self.assertIn("PASS FT3168 ACTIVE MODE", SOURCE)

    def test_touch_uses_interrupt_first_with_finger_count_fallback(self):
        self.assertIn("touch->IIC_Interrupt_Flag", SOURCE)
        self.assertIn("const bool interruptSignalled", SOURCE)
        self.assertIn("TOUCH_FINGER_NUMBER", SOURCE)
        self.assertIn("if (fingers <= 0)", SOURCE)
        self.assertIn("touch->IIC_Interrupt_Flag = false", SOURCE)
        self.assertIn("touchArmNotBeforeMs = millis() + 1500", SOURCE)
        self.assertIn("if (!elapsed(millis(), touchArmNotBeforeMs))", SOURCE)
        self.assertIn("if (!interruptSignalled)", SOURCE)
        self.assertIn("!interruptSignalled return above", SOURCE)

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

    def test_capture_readiness_labels_do_not_claim_audio_before_raw24(self):
        self.assertIn('"TOQUE ACEITO"', SOURCE)
        self.assertIn('"VALIDANDO TOQUE"', SOURCE)
        self.assertIn('"AGUARDANDO AUDIO REAL"', SOURCE)
        self.assertIn('"FALE AGORA"', SOURCE)
        self.assertIn('"VALIDANDO COM O CORE"', SOURCE)
        self.assertIn('void renderProgress(uint16_t color)', SOURCE)

    def test_identical_poll_does_not_force_full_screen_redraw(self):
        self.assertIn("uint32_t visualStateFingerprint()", SOURCE)
        self.assertIn("const uint32_t previousVisualState = visualStateFingerprint();", SOURCE)
        self.assertIn(
            "if (visualStateFingerprint() != previousVisualState) uiDirty = true;",
            SOURCE,
        )
        self.assertIn("kPollPeriodMs = 700", SOURCE)

    def test_progress_and_battery_are_partial_updates(self):
        self.assertIn("kProgressUpdatePeriodMs = 1000", SOURCE)
        self.assertIn("void updateProgressIndicator()", SOURCE)
        self.assertIn("updateProgressIndicator();", SOURCE)
        self.assertIn("void renderBatteryField()", SOURCE)
        self.assertIn("else if (batteryDirty)", SOURCE)

    def test_active_capture_counts_are_separate_and_legible(self):
        self.assertIn('"CAPTURA ATUAL: "', SOURCE)
        self.assertIn('"CAPTURAS SALVAS: "', SOURCE)

    def test_rejected_start_resets_visual_state_to_standby(self):
        # A failed local POST is not proof either way. The next Core poll
        # resolves it without emitting another command.
        self.assertIn("START_ERROR_RECONCILE_CORE", SOURCE)
        self.assertIn('statusMessage = "CONFIRMANDO CORE"', SOURCE)
        self.assertIn("reconcileWasStart = true", SOURCE)

    def test_ready_to_speak_requires_start_ack_and_verified_raw24_frame(self):
        model = WearableModel()
        model.start_acked = True
        model.apply({"state": "OCCURRENCE_ACTIVE", "occurrence_id": "OCC_2",
                     "capture_active": True, "pcm_source": {"valid_frames": 0}})
        self.assertEqual(model.visible_mode(), "STARTING_CAPTURE")
        self.assertFalse(model.ready_to_speak)
        model.apply({"state": "OCCURRENCE_ACTIVE", "capture_active": True,
                     "pcm_source": {"valid_frames": 1}})
        self.assertTrue(model.ready_to_speak)
        self.assertEqual(model.visible_mode(), "OCCURRENCE_ACTIVE")

    def test_core_standby_releases_pending_start_without_audio(self):
        model = WearableModel(start_acked=True, first_valid_audio_frame=False,
                              state="OCCURRENCE_ACTIVE", capture_active=True)
        self.assertEqual(model.visible_mode(), "STARTING_CAPTURE")
        model.apply({"state": "STANDBY", "capture_active": False,
                     "occurrence_id": None})
        self.assertEqual(model.visible_mode(), "STANDBY")
        self.assertFalse(model.capture_active)

    def test_stop_waits_for_core_closed_and_source_quiescent(self):
        model = WearableModel(capture_active=True, source_quiescent=False,
                              occurrence_id="OCC_3", stop_acked=True)
        model.apply({"state": "STOPPING", "capture_active": True,
                     "source_quiescent": False, "finalization_pending": True})
        self.assertTrue(model.capture_active)
        model.apply({"state": "PROCESSING_PENDING", "capture_active": False,
                     "source_quiescent": True, "finalization_pending": True})
        self.assertFalse(model.capture_active)
        self.assertTrue(model.finalization_pending)

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
