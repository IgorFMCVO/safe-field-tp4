from pathlib import Path
import re
import unittest
S = (Path(__file__).resolve().parents[1] / 'safe_field_operational_v1.ino').read_text()
def body(name):
    found = re.search(r"(?:void|bool) " + name + r"\([^;]*?\)\s*\{", S)
    assert found, name
    start=found.end(); depth=1; i=start
    while depth:
        depth += (S[i] == '{') - (S[i] == '}'); i+=1
    return S[start:i-1]
class NetworkOwnershipTests(unittest.TestCase):
    def test_http_only_in_network_task(self):
        worker=body('controlNetworkTask')
        self.assertIn('http.GET()',worker); self.assertIn('http.POST(',worker)
        remainder=S.replace(worker,'')
        self.assertNotIn('http.GET()',remainder); self.assertNotIn('http.POST(',remainder)
    def test_network_task_does_not_apply_or_draw(self):
        worker=body('controlNetworkTask')
        self.assertNotRegex(worker, r'applyStatePayload\s*\(')
        self.assertNotRegex(worker, r'gfx->|preferences\.')
        self.assertIn('request->token',worker); self.assertIn('request->ca',worker)
    def test_poll_is_queue_only(self):
        self.assertIn('enqueueControlRequest',body('pollCore'))
        self.assertNotIn('HTTPClient',body('pollCore'))
    def test_every_command_has_bounded_payload_and_scoped_response(self):
        self.assertIn('http.getSize() <= 32768',body('controlNetworkTask'))
        self.assertIn('responseOrder.accept',body('serviceControlResponses'))
        self.assertIn('applyStatePayload(response->payload)',body('serviceControlResponses'))
    def test_no_sync_post_helper_remains(self):
        self.assertNotRegex(S, r'\bpostJson\s*\(')
    def test_demo_never_forces_a_new_recording(self):
        loop=body('loop')
        self.assertNotIn('startOccurrence()',loop)
        self.assertNotIn('startNextCapture()',loop)
    def test_incomplete_stop_is_not_converted_to_standby_by_watchdog(self):
        code=body('serviceNetworkWatchdog')
        self.assertNotIn('captureActive = false', code)
        self.assertNotIn('serverState = "STANDBY"', code)
    def test_display_fingerprint_kept(self):
        self.assertIn('visualStateFingerprint() != previousVisualState',S)
        self.assertIn('kProgressUpdatePeriodMs = 1000', S)
if __name__=='__main__': unittest.main()
