#include <Arduino.h>
#include <Arduino_DriveBus_Library.h>
#include <Arduino_GFX_Library.h>
#include <HTTPClient.h>
#include <HWCDC.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <memory>
#include <vector>
#include <new>
#include "response_order.h"

#include "pin_config.h"
#include <XPowersLib.h>

#ifndef SAFE_FIELD_ENABLE_TEST_HOOKS
#define SAFE_FIELD_ENABLE_TEST_HOOKS 0
#endif

namespace {

constexpr uint32_t kSerialBaud = 115200;
constexpr uint32_t kPollPeriodMs = 700;
constexpr uint32_t kProgressUpdatePeriodMs = 1000;
constexpr uint32_t kWifiRetryMs = 10000;
constexpr uint32_t kHttpTimeoutMs = 1800;
constexpr uint32_t kFinishHttpTimeoutMs = 3500;
constexpr float kFinishProcessingTimeoutSeconds = 1.0f;
constexpr uint32_t kTouchDebounceMs = 350;
// A CA certificate is provisioned as one escaped-PEM serial command. 8192
// bytes covers normal root/intermediate certificates while keeping the input
// buffer explicitly bounded.
constexpr size_t kMaxCommandLength = 8192;
// ESP-IDF NVS strings are bounded to 4000 bytes; retain margin for the NUL.
constexpr size_t kMaxCaPemLength = 3900;
// Guidance is operational content, not a dashboard summary. Keep every item
// supplied by the Core and render it through a touch-scrollable viewport.
constexpr uint8_t kGuidanceVisibleRows = 5;

constexpr char kStatePath[] = "/api/v1/operational/wearable/state";
constexpr char kStartPath[] = "/api/v1/occurrences/start";
constexpr char kStartCapturePath[] = "/api/v1/occurrences/captures/start";
constexpr char kStopCapturePath[] = "/api/v1/occurrences/captures/stop";
constexpr char kConfirmPath[] = "/api/v1/hypotheses/confirm";
constexpr char kRejectPath[] = "/api/v1/hypotheses/reject";
constexpr char kDeferPath[] = "/api/v1/hypotheses/defer";
constexpr char kActionPath[] = "/api/v1/guidance/action";
constexpr char kFinishPath[] = "/api/v1/occurrences/conclude";
constexpr char kAnalyzePath[] = "/api/v1/occurrences/analyze";

constexpr uint16_t kBlack = 0x0000;
constexpr uint16_t kWhite = 0xFFFF;
constexpr uint16_t kMuted = 0x8410;
constexpr uint16_t kBlue = 0x05FF;
constexpr uint16_t kGreen = 0x07E0;
constexpr uint16_t kRed = 0xF800;
constexpr uint16_t kAmber = 0xFD20;
constexpr uint16_t kPanel = 0x1082;
constexpr uint16_t kDarkRed = 0x7800;

enum class UiMode : uint8_t {
  STANDBY,
  STARTING_CAPTURE,
  SAVING_CAPTURE,
  OCCURRENCE_OPEN,
  CONCLUDING_OCCURRENCE,
  OCCURRENCE_ACTIVE,
  HYPOTHESIS_PROPOSED,
  GUIDANCE,
  REASSESSMENT_REQUIRED,
  PROCESSING_PENDING,
  GUIDANCE_NOT_AVAILABLE,
  CAPTURE_FAILED,
  SAVED_RESULT,
};

enum class ControlCommand : uint8_t {
  NONE,
  START_OCCURRENCE,
  START_CAPTURE,
  STOP_CAPTURE,
  CONCLUDE_OCCURRENCE,
  POLL_STATE,
  ANALYZE_OCCURRENCE,
  HYPOTHESIS_DECISION,
  GUIDANCE_ACTION,
};

enum class PostResult : uint8_t {
  ERROR,
  ACCEPTED,
  PROCESSING_PENDING,
  CAPTURE_FAILED,
};

// Queues transfer ownership of pointers, never copy Arduino String storage.
// The UI constructs an immutable request; only the network task uses its client.
struct ControlRequest {
  ControlCommand command;
  String url, body, token, ca;
  uint32_t timeoutMs, epoch, requestId, queuedAt;
};
struct ControlResponse {
  ControlCommand command;
  PostResult result = PostResult::ERROR;
  int httpStatus = 0;
  uint32_t epoch, requestId;
  String payload;
};

struct GuidanceItem {
  String actionId;
  String text;
  String status;
  String sourceDocument;
  String sourceVersion;
  String section;
  String page;
  String item;
  String chunkId;
};

HWCDC USBSerial;
Preferences preferences;
XPowersPMU power;

Arduino_DataBus *displayBus = new Arduino_ESP32QSPI(
    LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
Arduino_GFX *gfx = new Arduino_CO5300(displayBus, LCD_RESET, 0,
                                      LCD_WIDTH, LCD_HEIGHT, 22, 0, 0, 0);

std::shared_ptr<Arduino_IIC_DriveBus> touchBus =
    std::make_shared<Arduino_HWIIC>(IIC_SDA, IIC_SCL, &Wire);
void touchInterrupt();
std::unique_ptr<Arduino_IIC> touch(new Arduino_FT3x68(
    touchBus, FT3168_DEVICE_ADDRESS, DRIVEBUS_DEFAULT_VALUE, TP_INT,
    touchInterrupt));

String wifiSsid;
String wifiPassword;
String configuredCoreUrl;
String coreBaseUrl;
String apiToken;
String coreCaPem;
String serialLine;

String serverState = "STANDBY";
String occurrenceId;
String activeCaptureId;
String coreBootId;
uint32_t captureCount = 0;
uint32_t stateRevision = 0;
uint32_t commandSequence = 0;
uint32_t commandBootNonce = 0;
ControlCommand pendingControlCommand = ControlCommand::NONE;
String hypothesisId;
String hypothesisLabel;
String hypothesisStatus;
String statusMessage;
String apiVersion;
std::vector<GuidanceItem> guidance;
uint16_t selectedGuidance = 0;
uint16_t guidanceScrollOffset = 0;

bool displayReady = false;
bool touchReady = false;
bool pmuReady = false;
bool coreOnline = false;
bool authFailed = false;
bool transportSecurityFailed = false;
bool captureActive = false;
bool sourceQuiescent = true;
bool finalizationPending = false;
// These gates deliberately follow Core evidence. A tap is never evidence that
// the UART reader is delivering verified RAW24 frames.
bool startAwaitingAudio = false;
bool stopAwaitingCore = false;
bool startRequestInFlight = false;
bool stopRequestInFlight = false;
bool concludeAwaitingCore = false;
bool concludeRequestInFlight = false;
// An HTTPS error is inconclusive. One normal poll reconciles it against the
// Core; no automatic POST retry is ever emitted from this state.
bool reconcilePending = false;
bool reconcileWasStart = false;
bool savedResultAvailable = false;
bool savedSuggestionAvailable = false;
String savedResultLabel;
uint32_t savedResultFactCount = 0;
uint32_t startHttpNotBeforeMs = 0;
uint32_t stopHttpNotBeforeMs = 0;
uint32_t concludeHttpNotBeforeMs = 0;
bool touchContactActive = false;
bool touchIrqWasHigh = true;
uint32_t lastValidRaw24Frames = 0;
uint32_t tStartTap = 0;
uint32_t tStartHttpSent = 0;
uint32_t tStartAck = 0;
uint32_t tFirstValidAudioFrame = 0;
uint32_t tRecordingUi = 0;
uint32_t tStopTap = 0;
uint32_t tStopAck = 0;
uint32_t tLastAudioFrame = 0;
uint32_t tProcessingUi = 0;
bool requestPending = false;
bool controlRequestQueued = false;
bool uiDirty = true;
bool batteryDirty = false;
int batteryPercent = -1;
uint32_t lastPollMs = 0;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastBatteryReadMs = 0;
uint32_t lastTouchMs = 0;
uint32_t lastTouchProbeMs = 0;
uint32_t lastUiAnimationMs = 0;
uint32_t touchArmNotBeforeMs = 0;
QueueHandle_t controlRequestQueue = nullptr;
QueueHandle_t controlResponseQueue = nullptr;
ResponseOrder responseOrder;
bool pollQueued = false;
bool networkWarningShown = false;
uint32_t networkQueuedAt = 0;
uint32_t lastCoreResponseMs = 0;
uint32_t latestCommandRequest = 0;
uint32_t networkRequestSequence = 0;
String analysisStatus;
String analysisMessage;
bool showAnalysis = false;
bool showGuidance = false;



bool enqueueControlRequest(ControlCommand command, const String &path, const String &body, uint32_t timeoutMs);
void serviceNetworkWatchdog();
void analyzeOccurrence();

void touchInterrupt() { touch->IIC_Interrupt_Flag = true; }

bool initializeTouchController(bool recovery) {
  if (!touch->begin()) {
    if (recovery) USBSerial.println("FT3168 RECOVERY PROBE FAILED");
    return false;
  }
  pinMode(TP_INT, INPUT_PULLUP);
  detachInterrupt(digitalPinToInterrupt(TP_INT));
  attachInterrupt(digitalPinToInterrupt(TP_INT), touchInterrupt, FALLING);
  touchIrqWasHigh = digitalRead(TP_INT) == HIGH;
  touch->IIC_Interrupt_Flag = false;
  touchContactActive = false;
  // Discovery and USB reset can leave a stale interrupt/coordinate pair.
  // Arm only after the controller has settled.
  touchArmNotBeforeMs = millis() + 1500;
  const bool touchActive = touch->IIC_Write_Device_State(
      touch->Arduino_IIC_Touch::Device::TOUCH_POWER_MODE,
      touch->Arduino_IIC_Touch::Device_Mode::TOUCH_POWER_ACTIVE);
  USBSerial.println(touchActive ? "PASS FT3168 ACTIVE MODE" :
                    "WARN FT3168 ACTIVE MODE");
  if (recovery) USBSerial.println("PASS FT3168 RECOVERED");
  return true;
}

bool elapsed(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

void captureTimestamp(const char *name, uint32_t value) {
  USBSerial.printf("CAPTURE_TS %s=%lu\n", name,
                   static_cast<unsigned long>(value));
}

String clipped(const String &value, size_t maxLength) {
  if (value.length() <= maxLength) return value;
  if (maxLength < 4) return value.substring(0, maxLength);
  return value.substring(0, maxLength - 3) + "...";
}

String jsonEscape(const String &value) {
  String escaped;
  escaped.reserve(value.length() + 8);
  for (size_t i = 0; i < value.length(); ++i) {
    const char c = value[i];
    if (c == '\\' || c == '"') escaped += '\\';
    if (c == '\n') {
      escaped += "\\n";
    } else if (c != '\r') {
      escaped += c;
    }
  }
  return escaped;
}

int jsonValueStart(const String &json, const char *key) {
  const String marker = String('"') + key + '"';
  int index = json.indexOf(marker);
  if (index < 0) return -1;
  index = json.indexOf(':', index + marker.length());
  if (index < 0) return -1;
  ++index;
  while (index < static_cast<int>(json.length()) &&
         (json[index] == ' ' || json[index] == '\t' || json[index] == '\n' ||
          json[index] == '\r')) {
    ++index;
  }
  return index;
}

String jsonStringValue(const String &json, const char *key) {
  int index = jsonValueStart(json, key);
  if (index < 0 || json[index] != '"') return "";
  String value;
  bool escape = false;
  for (++index; index < static_cast<int>(json.length()); ++index) {
    const char c = json[index];
    if (escape) {
      value += c == 'n' ? '\n' : c;
      escape = false;
    } else if (c == '\\') {
      escape = true;
    } else if (c == '"') {
      return value;
    } else {
      value += c;
    }
  }
  return "";
}

String jsonScalarValue(const String &json, const char *key) {
  const int start = jsonValueStart(json, key);
  if (start < 0) return "";
  if (json[start] == '"') return jsonStringValue(json, key);
  int end = start;
  while (end < static_cast<int>(json.length()) && json[end] != ',' &&
         json[end] != '}' && json[end] != ']' && json[end] != ' ' &&
         json[end] != '\n' && json[end] != '\r' && json[end] != '\t') {
    ++end;
  }
  return json.substring(start, end);
}

uint32_t jsonUnsignedValue(const String &json, const char *key,
                           uint32_t fallback = 0) {
  const String value = jsonScalarValue(json, key);
  if (!value.length()) return fallback;
  char *end = nullptr;
  const unsigned long parsed = strtoul(value.c_str(), &end, 10);
  return end != value.c_str() && *end == '\0'
      ? static_cast<uint32_t>(parsed) : fallback;
}

bool jsonBoolValue(const String &json, const char *key, bool fallback) {
  const int index = jsonValueStart(json, key);
  if (index < 0) return fallback;
  if (json.startsWith("true", index)) return true;
  if (json.startsWith("false", index)) return false;
  return fallback;
}

String jsonContainerValue(const String &json, const char *key,
                          char opening, char closing) {
  const int start = jsonValueStart(json, key);
  if (start < 0 || json[start] != opening) return "";
  int depth = 0;
  bool quoted = false;
  bool escape = false;
  for (int index = start; index < static_cast<int>(json.length()); ++index) {
    const char c = json[index];
    if (quoted) {
      if (escape) escape = false;
      else if (c == '\\') escape = true;
      else if (c == '"') quoted = false;
      continue;
    }
    if (c == '"') {
      quoted = true;
    } else if (c == opening) {
      ++depth;
    } else if (c == closing && --depth == 0) {
      return json.substring(start, index + 1);
    }
  }
  return "";
}

String jsonObjectValue(const String &json, const char *key) {
  return jsonContainerValue(json, key, '{', '}');
}

String jsonArrayValue(const String &json, const char *key) {
  return jsonContainerValue(json, key, '[', ']');
}

bool jsonOk(const String &json) {
  return jsonBoolValue(json, "ok", false);
}

bool jsonHasKey(const String &json, const char *key) {
  return jsonValueStart(json, key) >= 0;
}

String normalizeCoreBase(String configured) {
  configured.trim();
  const int api = configured.indexOf("/api/");
  if (api >= 0) configured = configured.substring(0, api);
  while (configured.endsWith("/")) configured.remove(configured.length() - 1);
  return configured;
}

bool isValidPort(const String &port) {
  if (!port.length() || port.length() > 5) return false;
  uint32_t value = 0;
  for (size_t index = 0; index < port.length(); ++index) {
    if (port[index] < '0' || port[index] > '9') return false;
    value = value * 10 + static_cast<uint32_t>(port[index] - '0');
  }
  return value > 0 && value <= 65535;
}

bool isValidDnsHost(const String &host) {
  if (!host.length() || host.startsWith(".") || host.endsWith(".") ||
      host.startsWith("-") || host.endsWith("-")) {
    return false;
  }
  for (size_t index = 0; index < host.length(); ++index) {
    const char c = host[index];
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '.' || c == '-')) {
      return false;
    }
  }
  return true;
}

bool isValidHttpsBase(const String &base) {
  if (!base.startsWith("https://") || base.length() <= 8) return false;
  if (base.indexOf(' ') >= 0 || base.indexOf('\t') >= 0 ||
      base.indexOf('\r') >= 0 || base.indexOf('\n') >= 0 ||
      base.indexOf('@', 8) >= 0 || base.indexOf('?', 8) >= 0 ||
      base.indexOf('#', 8) >= 0 || base.indexOf('\\', 8) >= 0) {
    return false;
  }
  // A Core base is an origin, not an arbitrary path. normalizeCoreBase()
  // already removes legacy /api/... endpoint suffixes.
  if (base.indexOf('/', 8) >= 0) return false;
  const String authority = base.substring(8);
  if (!authority.length() || authority.startsWith(":")) return false;
  if (authority.startsWith("[")) {
    const int closing = authority.indexOf(']');
    if (closing <= 1) return false;
    for (int index = 1; index < closing; ++index) {
      const char c = authority[index];
      const bool hex = (c >= '0' && c <= '9') ||
                       (c >= 'a' && c <= 'f') ||
                       (c >= 'A' && c <= 'F');
      if (!hex && c != ':' && c != '.') return false;
    }
    if (closing == static_cast<int>(authority.length()) - 1) return true;
    return authority[closing + 1] == ':' &&
           isValidPort(authority.substring(closing + 2));
  }
  const int colon = authority.lastIndexOf(':');
  if (colon < 0) return isValidDnsHost(authority);
  if (authority.indexOf(':') != colon) return false;
  return isValidDnsHost(authority.substring(0, colon)) &&
         isValidPort(authority.substring(colon + 1));
}

bool isValidCaPem(const String &pem) {
  return pem.length() >= 64 && pem.length() <= kMaxCaPemLength &&
         pem.startsWith("-----BEGIN CERTIFICATE-----\n") &&
         pem.indexOf("\n-----END CERTIFICATE-----") >= 0;
}

void failTransportSecurity(const char *reason) {
  transportSecurityFailed = true;
  coreOnline = false;
  statusMessage = "TLS CONFIG NECESSARIA";
  uiDirty = true;
  USBSerial.printf("ERR TLS %s bearer=NOT_SENT\n", reason);
}

bool secureTransportReady() {
  if (!isValidHttpsBase(coreBaseUrl)) {
    failTransportSecurity("HTTPS_CORE_REQUIRED");
    return false;
  }
  if (!isValidCaPem(coreCaPem)) {
    failTransportSecurity("CA_CERT_REQUIRED");
    return false;
  }
  transportSecurityFailed = false;
  return true;
}

bool beginSecureHttp(HTTPClient &http, WiFiClientSecure &tlsClient,
                     const String &url, uint32_t timeoutMs, const String &ca) {
  tlsClient.setCACert(ca.c_str());
  tlsClient.setHandshakeTimeout(max<uint32_t>(1, (timeoutMs + 999) / 1000));
  http.setConnectTimeout(timeoutMs);
  http.setTimeout(timeoutMs);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  return http.begin(tlsClient, url);
}

void clearOperationalDetails() {
  occurrenceId = "";
  activeCaptureId = "";
  captureCount = 0;
  hypothesisId = "";
  hypothesisLabel = "";
  hypothesisStatus = "";
  statusMessage = "";
  guidance.clear();
  selectedGuidance = 0;
  guidanceScrollOffset = 0;
  finalizationPending = false;
}

void ensureGuidanceSelectionVisible() {
  if (guidance.empty()) {
    selectedGuidance = 0;
    guidanceScrollOffset = 0;
    return;
  }
  if (selectedGuidance >= guidance.size()) {
    selectedGuidance = static_cast<uint16_t>(guidance.size() - 1);
  }
  if (guidanceScrollOffset > selectedGuidance) {
    guidanceScrollOffset = selectedGuidance;
  }
  if (selectedGuidance >= guidanceScrollOffset + kGuidanceVisibleRows) {
    guidanceScrollOffset = selectedGuidance - kGuidanceVisibleRows + 1;
  }
}

uint32_t visualHashMix(uint32_t hash, uint32_t value) {
  hash ^= value;
  return hash * 16777619UL;
}

uint32_t visualHashText(uint32_t hash, const String &value) {
  for (size_t index = 0; index < value.length(); ++index) {
    hash = visualHashMix(hash, static_cast<uint8_t>(value[index]));
  }
  return visualHashMix(hash, 0xFF);
}

// The transport payload contains fast-changing telemetry (for example the
// RAW24 frame count) that is not drawn.  Hash only values that can alter the
// visible screen so an identical poll never clears and rebuilds the panel.
uint32_t visualStateFingerprint() {
  uint32_t hash = 2166136261UL;
  hash = visualHashText(hash, serverState);
  hash = visualHashText(hash, occurrenceId);
  hash = visualHashText(hash, hypothesisLabel);
  hash = visualHashText(hash, hypothesisStatus);
  hash = visualHashText(hash, savedResultLabel);
  hash = visualHashMix(hash, captureCount);
  hash = visualHashMix(hash, selectedGuidance);
  hash = visualHashMix(hash, guidanceScrollOffset);
  hash = visualHashMix(hash, captureActive);
  hash = visualHashMix(hash, finalizationPending);
  hash = visualHashMix(hash, startAwaitingAudio);
  hash = visualHashMix(hash, stopAwaitingCore);
  hash = visualHashMix(hash, concludeAwaitingCore);
  hash = visualHashMix(hash, startRequestInFlight);
  hash = visualHashMix(hash, stopRequestInFlight);
  hash = visualHashMix(hash, concludeRequestInFlight);
  hash = visualHashMix(hash, requestPending);
  hash = visualHashMix(hash, savedResultAvailable);
  hash = visualHashMix(hash, savedSuggestionAvailable);
  hash = visualHashMix(hash, savedResultFactCount);
  for (const GuidanceItem &entry : guidance) {
    hash = visualHashText(hash, entry.actionId);
    hash = visualHashText(hash, entry.text);
    hash = visualHashText(hash, entry.status);
  }
  return hash;
}

void parseGuidance(const String &payload) {
  const String previouslySelectedId =
      (guidance.empty() || selectedGuidance >= guidance.size())
          ? "" : guidance[selectedGuidance].actionId;
  guidance.clear();
  selectedGuidance = 0;
  guidanceScrollOffset = 0;
  const String guidanceObject = jsonObjectValue(payload, "guidance");
  String items = jsonArrayValue(guidanceObject.length() ? guidanceObject : payload,
                                "items");
  if (!items.length()) return;

  int cursor = 1;
  while (cursor < static_cast<int>(items.length())) {
    const int objectStart = items.indexOf('{', cursor);
    if (objectStart < 0) break;
    int depth = 0;
    bool quoted = false;
    bool escape = false;
    int objectEnd = -1;
    for (int index = objectStart; index < static_cast<int>(items.length()); ++index) {
      const char c = items[index];
      if (quoted) {
        if (escape) escape = false;
        else if (c == '\\') escape = true;
        else if (c == '"') quoted = false;
        continue;
      }
      if (c == '"') quoted = true;
      else if (c == '{') ++depth;
      else if (c == '}' && --depth == 0) {
        objectEnd = index;
        break;
      }
    }
    if (objectEnd < 0) break;
    const String object = items.substring(objectStart, objectEnd + 1);
    GuidanceItem entry;
    entry.actionId = jsonStringValue(object, "action_id");
    if (!entry.actionId.length()) entry.actionId = jsonStringValue(object, "id");
    entry.text = jsonStringValue(object, "text");
    if (!entry.text.length()) entry.text = jsonStringValue(object, "action");
    entry.status = jsonStringValue(object, "status");
    String source = jsonObjectValue(object, "source");
    if (!source.length()) {
      const String sources = jsonArrayValue(object, "sources");
      const int sourceStart = sources.indexOf('{');
      if (sourceStart >= 0) {
        const String wrapper = String("{\"first\":") + sources.substring(sourceStart) + "}";
        source = jsonObjectValue(wrapper, "first");
      }
    }
    const String &metadata = source.length() ? source : object;
    entry.sourceDocument = jsonStringValue(metadata, "source_document");
    entry.sourceVersion = jsonStringValue(metadata, "source_version");
    entry.section = jsonStringValue(metadata, "section");
    entry.page = jsonScalarValue(metadata, "page");
    entry.item = jsonScalarValue(metadata, "item");
    entry.chunkId = jsonStringValue(metadata, "chunk_id");
    if (entry.actionId.length() && entry.text.length()) {
      guidance.push_back(entry);
      if (entry.actionId == previouslySelectedId) {
        selectedGuidance = static_cast<uint16_t>(guidance.size() - 1);
      }
    }
    cursor = objectEnd + 1;
  }
  ensureGuidanceSelectionVisible();
}

void applyStatePayload(const String &payload) {
  const uint32_t previousVisualState = visualStateFingerprint();
  const String priorAnalysisStatus = analysisStatus;
  const String nextBootId = jsonStringValue(payload, "boot_id");
  const uint32_t nextRevision = jsonUnsignedValue(payload, "state_revision", 0);
  if (nextBootId.length()) {
    if (nextBootId == coreBootId && nextRevision < stateRevision) {
      USBSerial.printf("POLL_STALE revision=%lu current=%lu\n",
                       static_cast<unsigned long>(nextRevision),
                       static_cast<unsigned long>(stateRevision));
      return;
    }
    if (coreBootId.length() && nextBootId != coreBootId) {
      USBSerial.println("CORE_BOOT_CHANGED RESYNCHRONIZING");
      startAwaitingAudio = false;
      stopAwaitingCore = false;
      concludeAwaitingCore = false;
      startRequestInFlight = false;
      stopRequestInFlight = false;
      concludeRequestInFlight = false;
      reconcilePending = false;
    }
    coreBootId = nextBootId;
    stateRevision = nextRevision;
  }
  String nextVersion = jsonStringValue(payload, "version");
  if (!nextVersion.length()) nextVersion = jsonStringValue(payload, "api_version");
  if (nextVersion.length()) apiVersion = nextVersion;

  String nextState = jsonStringValue(payload, "state");
  if (!nextState.length()) nextState = jsonStringValue(payload, "ui_state");
  if (!nextState.length()) nextState = jsonStringValue(payload, "wearable_state");
  if (nextState == "SYSTEM_READY" || nextState == "OCCURRENCE_FINISHED") {
    nextState = "STANDBY";
  }
  const bool literalStopping = nextState == "STOPPING" ||
                               nextState == "FINALIZATION_PENDING";
  if (literalStopping) nextState = "PROCESSING_PENDING";

  // FPGA VAD IS TELEMETRY ONLY: AUDIO_QUIET/AUDIO_ACTIVE never gates capture.
  if (nextState == "AUDIO_QUIET" || nextState == "AUDIO_ACTIVE") {
    nextState = captureActive ? "OCCURRENCE_ACTIVE" : "STANDBY";
  }
  if (nextState == "OPEN") nextState = "OCCURRENCE_OPEN";
  if (nextState == "ACTIVE") nextState = "OCCURRENCE_ACTIVE";
  if (nextState.length()) serverState = nextState;
  if (jsonHasKey(payload, "analysis_status")) {
    analysisStatus = jsonStringValue(payload, "analysis_status");
    analysisMessage = jsonStringValue(payload, "analysis_message");
  }

  String nextOccurrence = jsonStringValue(payload, "occurrence_id");
  if (!nextOccurrence.length()) {
    const String occurrence = jsonObjectValue(payload, "occurrence");
    nextOccurrence = jsonStringValue(occurrence, "occurrence_id");
  }
  if (nextOccurrence.length()) occurrenceId = nextOccurrence;
  const String nextCapture = jsonStringValue(payload, "active_capture_id");
  if (nextCapture.length()) activeCaptureId = nextCapture;
  else if (jsonHasKey(payload, "active_capture_id")) activeCaptureId = "";
  captureCount = jsonUnsignedValue(payload, "capture_count", captureCount);

  // This is a read-only summary of an already persisted, closed occurrence.
  // It has no authority over capture; Core state below remains authoritative.
  const String lastResult = jsonObjectValue(payload, "last_result");
  if (lastResult.length()) {
    savedResultAvailable = jsonBoolValue(lastResult, "available", false);
    savedSuggestionAvailable = jsonBoolValue(lastResult, "suggestion_available", false);
    savedResultLabel = jsonStringValue(lastResult, "hypothesis_label");
    savedResultFactCount = jsonUnsignedValue(lastResult, "fact_count", 0);
  } else if (serverState != "STANDBY") {
    savedResultAvailable = false;
    savedSuggestionAvailable = false;
  }

  const bool captureFlagPresent = jsonHasKey(payload, "capture_active");
  if (captureFlagPresent) {
    captureActive = jsonBoolValue(payload, "capture_active", captureActive);
  }
  const bool sourceQuiescentPresent = jsonHasKey(payload, "source_quiescent");
  if (sourceQuiescentPresent) {
    sourceQuiescent = jsonBoolValue(payload, "source_quiescent", sourceQuiescent);
  } else if (captureFlagPresent) {
    sourceQuiescent = !captureActive;
  }
  finalizationPending = literalStopping ||
      jsonBoolValue(payload, "finalization_pending", false) ||
      (serverState == "PROCESSING_PENDING" && captureFlagPresent && !captureActive);
  if (serverState == "STANDBY") {
    // A later authoritative poll can report STANDBY after an external STOP,
    // even if this watch never observed the first audio frame.  Release the
    // local start gate or currentMode() would keep rendering capture startup.
    startAwaitingAudio = false;
    startRequestInFlight = false;
    // STOP may legitimately return STANDBY while ASR/diarization continue in
    // the Core's detached worker.  That is the completed capture boundary,
    // not an unfinished watch operation.
    if (stopAwaitingCore) {
      stopAwaitingCore = false;
      stopRequestInFlight = false;
      finalizationPending = false;
      tLastAudioFrame = millis();
      captureTimestamp("t_last_audio_frame", tLastAudioFrame);
      USBSerial.printf("CAPTURE_LATENCY stop_to_standby=%lu\n",
                       static_cast<unsigned long>(tLastAudioFrame - tStopTap));
    }
    concludeAwaitingCore = false;
    concludeRequestInFlight = false;
    captureActive = false;
    sourceQuiescent = true;
    clearOperationalDetails();
    showAnalysis = false; showGuidance = false; analysisStatus = "";
    if (reconcilePending) {
      reconcilePending = false;
      reconcileWasStart = false;
      USBSerial.println("CORE_RECONCILED_STANDBY");
    }
  } else if (serverState == "CAPTURE_FAILED") {
    startAwaitingAudio = false;
    // The Core can detect corruption while its reader still has in-flight
    // delivery. Preserve its explicit capture flag until source_quiescent.
    if (sourceQuiescentPresent && sourceQuiescent) captureActive = false;
    finalizationPending = false;
  } else if (serverState == "OCCURRENCE_OPEN") {
    reconcilePending = false; reconcileWasStart = false;
    if (stopAwaitingCore) {
      tLastAudioFrame = millis();
      captureTimestamp("t_last_audio_frame", tLastAudioFrame);
      USBSerial.printf("CAPTURE_LATENCY stop_to_open=%lu\n",
                       static_cast<unsigned long>(tLastAudioFrame - tStopTap));
    }
    startAwaitingAudio = false;
    startRequestInFlight = false;
    stopAwaitingCore = false;
    stopRequestInFlight = false;
    captureActive = false;
    sourceQuiescent = true;
    finalizationPending = false;
  } else if (!captureFlagPresent && occurrenceId.length() && !finalizationPending) {
    captureActive = true;
    sourceQuiescent = false;
  }

  // Local timeout/error is not proof of failure. A following poll that sees
  // a real Core capture adopts it; STANDBY above releases all local gates.
  if (reconcilePending && captureActive) {
    const bool wasStart = reconcileWasStart;
    reconcilePending = false;
    reconcileWasStart = false;
    stopAwaitingCore = false;
    stopRequestInFlight = false;
    finalizationPending = false;
    if (wasStart && tStartAck == 0) {
      tStartAck = millis();
      captureTimestamp("t_start_ack", tStartAck);
    }
    startAwaitingAudio = wasStart;
    serverState = "OCCURRENCE_ACTIVE";
    USBSerial.println("CORE_RECONCILED_CAPTURE_ACTIVE");
  }

  // PCM source status is the only proof that the START request became live
  // audio capture. It is deliberately independent of VAD/FSM activity.
  const String pcmSource = jsonObjectValue(payload, "pcm_source");
  const uint32_t validRaw24Frames = jsonUnsignedValue(pcmSource, "valid_frames",
                                                       lastValidRaw24Frames);
  if (validRaw24Frames > lastValidRaw24Frames) {
    lastValidRaw24Frames = validRaw24Frames;
    if (startAwaitingAudio && tFirstValidAudioFrame == 0) {
      tFirstValidAudioFrame = millis();
      captureTimestamp("t_first_valid_audio_frame", tFirstValidAudioFrame);
    }
  }
  if (startAwaitingAudio && tStartAck != 0 && tFirstValidAudioFrame != 0) {
    startAwaitingAudio = false;
    serverState = "OCCURRENCE_ACTIVE";
    tRecordingUi = millis();
    captureTimestamp("t_recording_ui", tRecordingUi);
    USBSerial.printf("CAPTURE_LATENCY start_ack_to_first_audio=%lu start_to_ready=%lu\n",
                     static_cast<unsigned long>(tFirstValidAudioFrame - tStartAck),
                     static_cast<unsigned long>(tRecordingUi - tStartTap));
  }
  if (stopAwaitingCore && !captureActive && sourceQuiescent &&
      (finalizationPending || serverState == "PROCESSING_PENDING")) {
    stopAwaitingCore = false;
    tLastAudioFrame = millis();
    captureTimestamp("t_last_audio_frame", tLastAudioFrame);
    tProcessingUi = millis();
    captureTimestamp("t_processing_ui", tProcessingUi);
    USBSerial.printf("CAPTURE_LATENCY stop_to_ack=%lu stop_to_last_audio=%lu\n",
                     static_cast<unsigned long>(tStopAck - tStopTap),
                     static_cast<unsigned long>(tLastAudioFrame - tStopTap));
  }

  const String hypothesis = jsonObjectValue(payload, "hypothesis");
  if (hypothesis.length()) {
    const String nextId = jsonStringValue(hypothesis, "hypothesis_id");
    const String nextLabel = jsonStringValue(hypothesis, "label");
    const String nextStatus = jsonStringValue(hypothesis, "status");
    if (nextId.length()) hypothesisId = nextId;
    if (nextLabel.length()) hypothesisLabel = nextLabel;
    if (nextStatus.length()) hypothesisStatus = nextStatus;
  } else {
    const String nextId = jsonStringValue(payload, "hypothesis_id");
    const String nextLabel = jsonStringValue(payload, "hypothesis_label");
    const String nextStatus = jsonStringValue(payload, "hypothesis_status");
    if (nextId.length()) hypothesisId = nextId;
    if (nextLabel.length()) hypothesisLabel = nextLabel;
    if (nextStatus.length()) hypothesisStatus = nextStatus;
  }
  if (serverState == "HYPOTHESIS_PROPOSED" && !hypothesisStatus.length()) {
    hypothesisStatus = "PROPOSED";
  }

  statusMessage = jsonStringValue(payload, "message");

  // A procedure can be shown only after an explicit officer confirmation.
  if (hypothesisStatus == "OFFICER_CONFIRMED") {
    parseGuidance(payload);
  } else {
    guidance.clear();
    selectedGuidance = 0;
    guidanceScrollOffset = 0;
  }
  if (visualStateFingerprint() != previousVisualState) uiDirty = true;
  if (analysisStatus != priorAnalysisStatus) uiDirty = true;
}

UiMode currentMode() {
  if (serverState == "CAPTURE_FAILED") return UiMode::CAPTURE_FAILED;
  if (startAwaitingAudio) return UiMode::STARTING_CAPTURE;
  if (stopAwaitingCore) return UiMode::SAVING_CAPTURE;
  if (concludeAwaitingCore) return UiMode::CONCLUDING_OCCURRENCE;
  // Finalization has priority over stale hypothesis/guidance fields retained
  // for audit display while the Core drains pending work.
  if (finalizationPending) return UiMode::PROCESSING_PENDING;
  // A stopped recorder keeps the occurrence operationally open even when an
  // asynchronous result arrives.  Capture controls must remain reachable.
  if (serverState == "OCCURRENCE_OPEN") {
    if (showAnalysis && (analysisStatus == "QUEUED" || analysisStatus == "PROCESSING" || analysisStatus == "FAILED")) return UiMode::PROCESSING_PENDING;
    if (showGuidance && hypothesisStatus == "OFFICER_CONFIRMED") return guidance.empty() ? UiMode::GUIDANCE_NOT_AVAILABLE : UiMode::GUIDANCE;
    if (showAnalysis && hypothesisStatus == "PROPOSED") return UiMode::HYPOTHESIS_PROPOSED;
    if (showAnalysis && (analysisStatus == "COMPLETE" || analysisStatus == "PARTIAL")) return UiMode::PROCESSING_PENDING;
    return UiMode::OCCURRENCE_OPEN;
  }
  if (serverState == "REASSESSMENT_REQUIRED") {
    return UiMode::REASSESSMENT_REQUIRED;
  }
  if (serverState == "GUIDANCE_NOT_AVAILABLE" ||
      serverState == "GUIDANCE_NOT_SUPPORTED") {
    return UiMode::GUIDANCE_NOT_AVAILABLE;
  }
  if (hypothesisStatus == "PROPOSED" ||
      serverState == "HYPOTHESIS_PROPOSED") {
    return UiMode::HYPOTHESIS_PROPOSED;
  }
  if (hypothesisStatus == "OFFICER_CONFIRMED" && !guidance.empty()) {
    return UiMode::GUIDANCE;
  }
  if (serverState == "PROCESSING_PENDING" ||
      (hypothesisStatus == "OFFICER_CONFIRMED" && guidance.empty())) {
    return UiMode::PROCESSING_PENDING;
  }
  if (captureActive || serverState == "OCCURRENCE_ACTIVE") {
    return UiMode::OCCURRENCE_ACTIVE;
  }
  if (serverState == "SAVED_RESULT") return UiMode::SAVED_RESULT;
  return UiMode::STANDBY;
}

void centeredText(const String &text, int16_t y, uint8_t size,
                  uint16_t color) {
  int16_t x1, y1;
  uint16_t width, height;
  gfx->setTextSize(size);
  gfx->getTextBounds(text.c_str(), 0, y, &x1, &y1, &width, &height);
  const int16_t x = max<int16_t>(6, (LCD_WIDTH - static_cast<int16_t>(width)) / 2);
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(text);
}

void button(int16_t x, int16_t y, int16_t width, int16_t height,
            uint16_t color, const String &label, uint8_t size = 2) {
  gfx->fillRoundRect(x, y, width, height, 12, color);
  int16_t x1, y1;
  uint16_t textWidth, textHeight;
  gfx->setTextSize(size);
  gfx->getTextBounds(label.c_str(), 0, 0, &x1, &y1, &textWidth, &textHeight);
  gfx->setTextColor(kWhite);
  gfx->setCursor(x + max<int16_t>(5, (width - static_cast<int16_t>(textWidth)) / 2),
                 y + (height - static_cast<int16_t>(textHeight)) / 2 + 1);
  gfx->print(label);
}

constexpr int16_t kProgressX = 46;
constexpr int16_t kProgressY = 330;
constexpr int16_t kProgressWidth = LCD_WIDTH - 92;

void renderProgress(uint16_t color) {
  // Only this small region changes while waiting. Clearing the complete
  // CO5300 frame caused a visible flash on every animation tick.
  gfx->fillRoundRect(kProgressX + 1, kProgressY + 1,
                     kProgressWidth - 2, 14, 7, kBlack);
  gfx->drawRoundRect(kProgressX, kProgressY, kProgressWidth, 16, 8, kMuted);
  const uint16_t phase = (millis() / kProgressUpdatePeriodMs) %
                         (kProgressWidth - 28);
  gfx->fillRoundRect(kProgressX + 2 + phase, kProgressY + 3, 26, 10, 5, color);
}

void updateProgressIndicator() {
  if (!displayReady) return;
  const UiMode mode = currentMode();
  if (mode == UiMode::STARTING_CAPTURE) {
    renderProgress(startRequestInFlight ? kGreen : kAmber);
  } else if (mode == UiMode::SAVING_CAPTURE ||
             mode == UiMode::CONCLUDING_OCCURRENCE) {
    renderProgress(kAmber);
  } else if (mode == UiMode::PROCESSING_PENDING ||
             mode == UiMode::GUIDANCE_NOT_AVAILABLE) {
    renderProgress(stopRequestInFlight ? kGreen : kAmber);
  }
}

void renderBatteryField() {
  if (!displayReady) return;
  gfx->fillRect(300, 60, LCD_WIDTH - 300, 18, kBlack);
  gfx->setTextSize(1);
  gfx->setTextColor(kMuted);
  gfx->setCursor(314, 67);
  gfx->print(batteryPercent >= 0 ? String("BAT ") + batteryPercent + "%" : "USB");
}

void renderHeader(const String &title, uint16_t accent) {
  gfx->fillScreen(kBlack);
  centeredText("SAFE-FIELD", 16, 3, kWhite);
  gfx->drawFastHLine(22, 55, LCD_WIDTH - 44, kBlue);
  gfx->setTextSize(1);
  gfx->setTextColor((transportSecurityFailed || authFailed) ? kRed :
                    (coreOnline ? kGreen : kAmber));
  gfx->setCursor(20, 67);
  gfx->print(transportSecurityFailed ? "TLS NECESSARIO" :
             (authFailed ? "AUTH NECESSARIA" :
              (coreOnline ? "CORE ONLINE" : "CORE OFFLINE")));
  renderBatteryField();
  batteryDirty = false;
  centeredText(title, 92, 2, accent);
}

// Deliberately rendered on every active-occurrence decision screen. Silence,
// a proposed hypothesis and procedure navigation never stop global capture.
void renderCaptureIndicator(int16_t y = 110) {
  gfx->fillRoundRect(74, y - 5, LCD_WIDTH - 148, 20, 9,
                     captureActive ? 0x1242 : kPanel);
  centeredText(captureActive ? "CAPTURA ATIVA - ESCUTA CONTINUA"
                             : "CAPTURA ENCERRADA",
               y, 1, captureActive ? kGreen : kMuted);
}

void renderStandby() {
  renderHeader("STANDBY", kBlue);
  centeredText("SEM OCORRENCIA", 162, 2, kMuted);
  centeredText("SEM GRAVACAO", 198, 2, kMuted);
  if (savedResultAvailable) {
    centeredText(savedSuggestionAvailable ? "RESULTADO PRONTO" : "PROCESSAMENTO CONCLUIDO",
                 252, 2, kGreen);
    button(42, 284, LCD_WIDTH - 84, 36, kBlue, "SUGESTAO", 1);
    button(42, 348, LCD_WIDTH - 84, 82, kGreen, "EM ATENDIMENTO", 2);
  } else {
    centeredText(coreOnline ? "CORE CONECTADO" : "CORE INDISPONIVEL",
                 258, 2, coreOnline ? kGreen : kAmber);
    button(42, 330, LCD_WIDTH - 84, 82, kGreen, "EM ATENDIMENTO", 2);
  }
}

void renderSavedResult() {
  renderHeader("RESULTADO PRONTO", kGreen);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  centeredText(savedSuggestionAvailable ? "SUGESTAO EXISTENTE" : "SEM SUGESTAO", 184, 2, kMuted);
  centeredText(clipped(savedResultLabel.length() ? savedResultLabel : "ANALISE PERSISTIDA", 26),
               228, 2, kWhite);
  centeredText("FATOS: " + String(savedResultFactCount), 270, 1, kMuted);
  centeredText("LEITURA SOMENTE", 308, 1, kMuted);
  button(42, 414, LCD_WIDTH - 84, 60, kBlue, "VOLTAR", 2);
}

void renderStartingCapture() {
  renderHeader(startRequestInFlight ? "TOQUE ACEITO" : "INICIANDO CAPTURA",
               startRequestInFlight ? kGreen : kAmber);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  centeredText(startRequestInFlight ? "VALIDANDO TOQUE" : "CAPTURA INICIADA",
               190, 2, kMuted);
  centeredText(startRequestInFlight ? "AGUARDE..." : "AGUARDANDO AUDIO REAL",
               238, 2, startRequestInFlight ? kGreen : kAmber);
  centeredText(startRequestInFlight ? "CONECTANDO AO CORE" :
               "NAO FALE AINDA", 292, 1, kWhite);
  renderProgress(startRequestInFlight ? kGreen : kAmber);
}

void renderOccurrence() {
  renderHeader("OCORRENCIA ATIVA", kGreen);
  gfx->fillRoundRect(25, 135, LCD_WIDTH - 50, 205, 18, kPanel);
  const uint32_t savedCaptures = captureCount > 0 ? captureCount - 1 : 0;
  centeredText(String("CAPTURA ATUAL: ") + captureCount, 158, 1, kGreen);
  centeredText(String("CAPTURAS SALVAS: ") + savedCaptures, 184, 1, kMuted);
  centeredText("FALE AGORA", 230, 3, kWhite);
  centeredText("CAPTURA CONTINUA", 282, 2, kGreen);
  centeredText("silencio nao encerra", 316, 1, kMuted);
  button(38, 418, LCD_WIDTH - 76, 61, kDarkRed, "PARAR CAPTURA", 2);
}

void renderSavingCapture() {
  renderHeader("SALVANDO CAPTURA", kAmber);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  centeredText("TOQUE RECONHECIDO", 184, 2, kGreen);
  centeredText("FECHANDO AUDIO...", 230, 2, kAmber);
  centeredText("ATENDIMENTO CONTINUA", 286, 1, kWhite);
  renderProgress(kAmber);
}

void renderOccurrenceOpen() {
  renderHeader("ATENDIMENTO ABERTO", kBlue);
  centeredText("MICROFONE PARADO", 150, 2, kMuted);
  centeredText(String("CAPTURAS SALVAS: ") + captureCount, 192, 2, kWhite);
  button(42, 250, LCD_WIDTH - 84, 75, kGreen, "NOVA CAPTURA", 2);
  button(42, 331, LCD_WIDTH - 84, 29, kBlue, "ANALISAR CAPTURAS", 1);
  button(42, 365, LCD_WIDTH - 84, 75, kDarkRed, "CONCLUIR", 2);
}

void renderConcludingOccurrence() {
  renderHeader("CONCLUINDO", kAmber);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  centeredText("TOQUE RECONHECIDO", 184, 2, kGreen);
  centeredText("PERSISTINDO FECHAMENTO", 230, 1, kAmber);
  centeredText("IA CONTINUARA EM BACKGROUND", 286, 1, kWhite);
  renderProgress(kAmber);
}

void renderHypothesis() {
  renderHeader("HIPOTESE PROPOSTA", kAmber);
  renderCaptureIndicator();
  gfx->fillRoundRect(20, 136, LCD_WIDTH - 40, 172, 18, kPanel);
  centeredText("POSSIVEL", 162, 2, kAmber);
  centeredText(clipped(hypothesisLabel.length() ? hypothesisLabel : "ANALISE EM CURSO", 25),
               208, 2, kWhite);
  centeredText("DECISAO DO POLICIAL", 265, 1, kMuted);
  button(10, 324, 126, 64, kGreen, "CONFIRMAR", 1);
  button(142, 324, 126, 64, kDarkRed, "RECUSAR", 1);
  button(274, 324, 126, 64, kBlue, "MAIS DADOS", 1);
  button(38, 422, LCD_WIDTH - 76, 55, kDarkRed, "ENCERRAR ATENDIMENTO", 2);
}

String statusLabel(const String &status) {
  if (status == "DONE") return "REALIZADO";
  if (status == "NOT_APPLICABLE") return "NAO APLICAVEL";
  return "PENDENTE";
}

void renderGuidance() {
  renderHeader(clipped(hypothesisLabel, 26), kGreen);
  renderCaptureIndicator();
  const int16_t rowHeight = 36;
  constexpr int16_t kRowsTop = 148;
  centeredText("PROCEDIMENTOS " + String(selectedGuidance + 1) + "/" +
                   String(guidance.size()),
               130, 1, kWhite);
  button(8, 112, 48, 24, kBlue, "^", 1);
  button(LCD_WIDTH - 56, 112, 48, 24, kBlue, "v", 1);
  const uint16_t lastVisible = min<uint16_t>(
      static_cast<uint16_t>(guidance.size()),
      guidanceScrollOffset + kGuidanceVisibleRows);
  for (uint16_t index = guidanceScrollOffset; index < lastVisible; ++index) {
    const int16_t y = kRowsTop +
        static_cast<int16_t>(index - guidanceScrollOffset) * rowHeight;
    const bool selected = index == selectedGuidance;
    gfx->fillRoundRect(14, y, LCD_WIDTH - 28, rowHeight - 4, 8,
                       selected ? 0x2124 : kPanel);
    gfx->setTextSize(1);
    gfx->setTextColor(selected ? kWhite : kMuted);
    gfx->setCursor(22, y + 7);
    gfx->printf("%u. %s", static_cast<unsigned>(index + 1),
                clipped(guidance[index].text, 43).c_str());
    gfx->setCursor(290, y + 21);
    gfx->setTextColor(guidance[index].status == "DONE" ? kGreen : kAmber);
    gfx->print(statusLabel(guidance[index].status));
  }
  button(7, 346, 128, 53, kGreen, "REALIZADO", 1);
  button(141, 346, 128, 53, kBlue, "PENDENTE", 1);
  button(275, 346, 128, 53, kMuted, "NAO APLICAVEL", 1);
  button(38, 429, LCD_WIDTH - 76, 51, kDarkRed, "ENCERRAR ATENDIMENTO", 2);
}

void renderReassessment() {
  renderHeader("REAVALIACAO NECESSARIA", kRed);
  renderCaptureIndicator();
  gfx->fillRoundRect(22, 140, LCD_WIDTH - 44, 185, 18, kPanel);
  centeredText("RELATE POR VOZ", 178, 2, kAmber);
  centeredText("NOVAS INFORMACOES", 219, 2, kWhite);
  centeredText("SERAO REAVALIADAS", 257, 1, kWhite);
  button(85, 342, LCD_WIDTH - 170, 65, kBlue, "ATUALIZAR", 2);
  button(38, 429, LCD_WIDTH - 76, 51, kDarkRed, "ENCERRAR ATENDIMENTO", 2);
}

void renderPending(bool unavailable) {
  if (!captureActive && serverState == "OCCURRENCE_OPEN") {
    renderHeader(analysisStatus == "FAILED" ? "ANALISE INCOMPLETA" :
        (analysisStatus == "COMPLETE" ? "ANALISE CONCLUIDA" :
         (analysisStatus == "PARTIAL" ? "ANALISE PARCIAL" : "ANALISANDO")), kAmber);
    centeredText("CAPTURAS PRESERVADAS", 158, 2, kWhite);
    centeredText(clipped(analysisMessage, 40), 202, 1, kMuted);
    button(42, 250, LCD_WIDTH - 84, 60, kGreen, "NOVA CAPTURA", 2);
    button(42, 322, LCD_WIDTH - 84, 55, kBlue, "ATUALIZAR / ANALISAR", 1);
    button(42, 391, LCD_WIDTH - 84, 60, kDarkRed, "CONCLUIR", 2);
    return;
  }
  const bool stopping = stopAwaitingCore || finalizationPending || !captureActive;
  renderHeader(stopping ? "FINALIZANDO" : "OCORRENCIA ATIVA",
               stopping ? kAmber : kGreen);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  const String title = stopRequestInFlight ? "TOQUE ACEITO" :
      (stopAwaitingCore ? "FINALIZANDO..." :
       (unavailable ? "ORIENTACAO" : "PROCESSANDO..."));
  const String status = stopRequestInFlight ? "FINALIZANDO..." :
      (stopAwaitingCore ? "AGUARDE" :
       (unavailable ? "INDISPONIVEL" : "PENDENTE"));
  const String detail = stopRequestInFlight ? "VALIDANDO COM O CORE" :
      (stopAwaitingCore ? "AGUARDANDO CONFIRMACAO DO CORE" :
       (stopping ? "CAPTURA ENCERRADA" : "CAPTURA CONTINUA"));
  centeredText(title, 185, 2, kMuted);
  centeredText(status, 230, 3, unavailable ? kAmber : kBlue);
  centeredText(detail, 295, 1, stopping ? kAmber : kGreen);
  renderProgress(stopRequestInFlight ? kGreen : kAmber);
  button(38, 418, LCD_WIDTH - 76, 61, kDarkRed,
         stopping ? "TENTAR ENCERRAR" : "ENCERRAR ATENDIMENTO", 2);
}

void renderCaptureFailed() {
  const bool needsStop = captureActive && !sourceQuiescent;
  renderHeader("FALHA NA CAPTURA", kRed);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  centeredText("INTEGRIDADE PCM", 184, 2, kRed);
  centeredText("NAO VALIDADA", 228, 3, kWhite);
  centeredText("HISTORICO NAO GERADO", 282, 1, kAmber);
  centeredText(needsStop ? "FONTE AINDA ATIVA" : "FONTE ENCERRADA",
               318, 1, needsStop ? kAmber : kMuted);
  if (needsStop) {
    button(38, 418, LCD_WIDTH - 76, 61, kDarkRed, "FINALIZAR CAPTURA", 2);
  }
}

void renderUi() {
  if (!displayReady) return;
  uiDirty = false;
  switch (currentMode()) {
    case UiMode::STANDBY: renderStandby(); break;
    case UiMode::STARTING_CAPTURE: renderStartingCapture(); break;
    case UiMode::SAVING_CAPTURE: renderSavingCapture(); break;
    case UiMode::OCCURRENCE_OPEN: renderOccurrenceOpen(); break;
    case UiMode::CONCLUDING_OCCURRENCE: renderConcludingOccurrence(); break;
    case UiMode::OCCURRENCE_ACTIVE: renderOccurrence(); break;
    case UiMode::HYPOTHESIS_PROPOSED: renderHypothesis(); break;
    case UiMode::GUIDANCE: renderGuidance(); break;
    case UiMode::REASSESSMENT_REQUIRED: renderReassessment(); break;
    case UiMode::PROCESSING_PENDING: renderPending(false); break;
    case UiMode::GUIDANCE_NOT_AVAILABLE: renderPending(true); break;
    case UiMode::CAPTURE_FAILED: renderCaptureFailed(); break;
    case UiMode::SAVED_RESULT: renderSavedResult(); break;
  }
  if (!coreOnline && statusMessage.length()) {
    gfx->fillRect(0, LCD_HEIGHT - 32, LCD_WIDTH, 18, kDarkRed);
    centeredText(clipped(statusMessage, 52), LCD_HEIGHT - 29, 1, kWhite);
  }
  if (requestPending) {
    gfx->fillRect(0, LCD_HEIGHT - 14, LCD_WIDTH, 14, kAmber);
    centeredText("ENVIANDO...", LCD_HEIGHT - 12, 1, kBlack);
  }
}

void handleUnauthorized(const char *operation) {
  authFailed = true;
  coreOnline = false;
  statusMessage = "AUTORIZACAO NEGADA";
  uiDirty = true;
  USBSerial.printf("%s status=401 auth=FAILED token=REDACTED\n", operation);
}

String nextCommandId() {
  ++commandSequence;
  char value[48];
  snprintf(value, sizeof(value), "watch_%08lx_%08lx",
           static_cast<unsigned long>(commandBootNonce),
           static_cast<unsigned long>(commandSequence));
  return String(value);
}

void beginCaptureCommand(bool newOccurrence) {
  if (requestPending || controlRequestQueued || startRequestInFlight || stopRequestInFlight || concludeRequestInFlight || reconcilePending) return;
  responseOrder.invalidate(); // invalidate an old poll at tap, not 80 ms later
  const uint32_t now = millis();
  tStartTap = now;
  tStartHttpSent = 0;
  tStartAck = 0;
  tFirstValidAudioFrame = 0;
  tRecordingUi = 0;
  lastValidRaw24Frames = 0;
  startAwaitingAudio = true;
  startRequestInFlight = true;
  startHttpNotBeforeMs = now + 80;
  stopAwaitingCore = false;
  pendingControlCommand = newOccurrence ? ControlCommand::START_OCCURRENCE
                                        : ControlCommand::START_CAPTURE;
  serverState = "STARTING_CAPTURE";
  USBSerial.println(newOccurrence ? "TOUCH_START" : "TOUCH_NEW_CAPTURE");
  uiDirty = true;
  captureTimestamp("t_start_tap", tStartTap);
  // Paint a real touch acknowledgement before initiating Wi-Fi/TLS work.
  renderUi();
}

void startOccurrence() { beginCaptureCommand(true); }

void startNextCapture() { showAnalysis = false; showGuidance = false; beginCaptureCommand(false); }

void analyzeOccurrence() {
  if (captureActive || !occurrenceId.length() || requestPending) return;
  const String body = String("{\"occurrence_id\":\"") + jsonEscape(occurrenceId) +
      "\",\"command_id\":\"" + nextCommandId() + "\"}";
  if (enqueueControlRequest(ControlCommand::ANALYZE_OCCURRENCE, kAnalyzePath, body, kHttpTimeoutMs)) {
    analysisStatus = "QUEUED"; showAnalysis = true; showGuidance = false;
    analysisMessage = "ANALISE SOLICITADA"; uiDirty = true;
  }
}

void serviceNetworkWatchdog() {
  if (requestPending && !networkWarningShown && millis() - networkQueuedAt > 10000) {
    networkWarningShown = true; coreOnline = false;
    statusMessage = "COMANDO SEM CONFIRMACAO"; uiDirty = true;
    USBSerial.println("NETWORK_WAIT_VISIBLE NO_AUTOMATIC_REPLAY");
  }
  // No fake STOP/START: keep the last capture flag, show connection uncertainty.
  if (coreOnline && lastCoreResponseMs && millis() - lastCoreResponseMs > 10000) {
    coreOnline = false; statusMessage = "ESTADO DO CORE DESATUALIZADO"; uiDirty = true;
  }
}


void decideHypothesis(const char *path, const char *decision) {
  if (!hypothesisId.length() || requestPending) return;
  const String body = String("{\"hypothesis_id\":\"") + jsonEscape(hypothesisId) +
      "\",\"decision\":\"" + decision + "\",\"command_id\":\"" + nextCommandId() + "\"}";
  if (enqueueControlRequest(ControlCommand::HYPOTHESIS_DECISION, path, body, kHttpTimeoutMs)) {
    if (strcmp(decision, "CONFIRM") == 0) showGuidance = true;
    uiDirty = true;
  }
}

void stopCapture() {
  if (requestPending || controlRequestQueued || startRequestInFlight || stopRequestInFlight || concludeRequestInFlight || reconcilePending) return;
  responseOrder.invalidate();
  tStopTap = millis();
  tStopAck = 0;
  tLastAudioFrame = 0;
  tProcessingUi = 0;
  stopAwaitingCore = true;
  stopRequestInFlight = true;
  pendingControlCommand = ControlCommand::STOP_CAPTURE;
  stopHttpNotBeforeMs = tStopTap + 80;
  serverState = "FINALIZING_CAPTURE";
  USBSerial.println("TOUCH_STOP");
  uiDirty = true;
  captureTimestamp("t_stop_tap", tStopTap);
  // Paint acknowledgement before the blocking finish request.
  renderUi();
}

void concludeOccurrence() {
  if (requestPending || controlRequestQueued || startRequestInFlight || stopRequestInFlight || concludeRequestInFlight || reconcilePending) return;
  responseOrder.invalidate();
  concludeAwaitingCore = true;
  concludeRequestInFlight = true;
  concludeHttpNotBeforeMs = millis() + 80;
  pendingControlCommand = ControlCommand::CONCLUDE_OCCURRENCE;
  serverState = "CONCLUDING_OCCURRENCE";
  USBSerial.println("TOUCH_CONCLUDE");
  uiDirty = true;
  renderUi();
}

bool enqueueControlRequest(ControlCommand command, const String &path,
                           const String &body, uint32_t timeoutMs) {
  if (!controlRequestQueue || WiFi.status() != WL_CONNECTED ||
      !apiToken.length() || !secureTransportReady()) return false;
  const bool isPoll = command == ControlCommand::POLL_STATE;
  if (isPoll ? (pollQueued || requestPending) : requestPending) return false;
  auto *request = new (std::nothrow) ControlRequest;
  if (!request) return false;
  request->command = command;
  request->url = coreBaseUrl + path;
  request->body = body;
  request->token = apiToken;
  request->ca = coreCaPem;
  request->timeoutMs = timeoutMs;
  request->epoch = responseOrder.epoch();
  request->requestId = ++networkRequestSequence;
  request->queuedAt = millis();
  if (!isPoll) request->epoch = responseOrder.beginCommand(request->requestId);
  const uint32_t requestId = request->requestId;
  if (xQueueSend(controlRequestQueue, &request, 0) != pdTRUE) {
    delete request;
    return false;
  }
  if (isPoll) pollQueued = true;
  else {
    requestPending = true;
    latestCommandRequest = requestId;
    networkQueuedAt = millis();
    networkWarningShown = false;
    uiDirty = true;
  }
  return true;
}

void controlNetworkTask(void *) {
  ControlRequest *raw = nullptr;
  for (;;) {
    if (xQueueReceive(controlRequestQueue, &raw, portMAX_DELAY) != pdTRUE) continue;
    std::unique_ptr<ControlRequest> request(raw);
    auto *reply = new (std::nothrow) ControlResponse;
    // Keep the request until a result can be delivered; allocation failure
    // must never silently execute a command and lose its outcome.
    while (!reply) { vTaskDelay(pdMS_TO_TICKS(50)); reply = new (std::nothrow) ControlResponse; }
    reply->command = request->command;
    reply->epoch = request->epoch;
    reply->requestId = request->requestId;
    const bool isPoll = request->command == ControlCommand::POLL_STATE;
    if (static_cast<uint32_t>(millis() - request->queuedAt) > 10000) {
      reply->httpStatus = -1001; // expired before sending; never replay it
    } else {
      WiFiClientSecure tlsClient;
      HTTPClient http;
      if (beginSecureHttp(http, tlsClient, request->url, request->timeoutMs, request->ca)) {
        http.addHeader("Authorization", String("Bearer ") + request->token);
        http.addHeader("Accept", "application/json");
        http.addHeader("Content-Type", "application/json");
        http.addHeader("X-Safe-Field-Client", "wearable-operational-v1");
        reply->httpStatus = isPoll ? http.GET() : http.POST(request->body);
        // Core sends Content-Length. Bound response allocation before reading.
        if (reply->httpStatus > 0 && http.getSize() >= 0 && http.getSize() <= 32768) {
          reply->payload = http.getString();
          if (reply->payload.length() != static_cast<size_t>(http.getSize())) reply->httpStatus = -1002;
        } else if (reply->httpStatus > 0) reply->httpStatus = -1003;
        if (reply->httpStatus >= 200 && reply->httpStatus < 300 && jsonOk(reply->payload))
          reply->result = PostResult::ACCEPTED;
        else if (jsonStringValue(reply->payload, "state") == "CAPTURE_FAILED" &&
                 !jsonBoolValue(reply->payload, "retryable", true))
          reply->result = PostResult::CAPTURE_FAILED;
        else if (reply->httpStatus >= 200 && reply->httpStatus < 300 &&
                 (jsonBoolValue(reply->payload, "retryable", false) ||
                  jsonBoolValue(reply->payload, "finalization_pending", false)))
          reply->result = PostResult::PROCESSING_PENDING;
      }
      http.end();
    }
    // No drawing, state mutation, NVS access or applyStatePayload in this task.
    xQueueSend(controlResponseQueue, &reply, portMAX_DELAY);
  }
}

void serviceControlResponses() {
  if (!controlResponseQueue) return;
  ControlResponse *raw = nullptr;
  while (xQueueReceive(controlResponseQueue, &raw, 0) == pdTRUE) {
    std::unique_ptr<ControlResponse> response(raw);
    const bool isPoll = response->command == ControlCommand::POLL_STATE;
    if (isPoll) pollQueued = false;
    const bool relevant = responseOrder.accept(response->epoch, response->requestId, isPoll);
    if (!relevant) { USBSerial.println("NETWORK_STALE_RESPONSE_IGNORED"); continue; }
    const bool accepted = response->result == PostResult::ACCEPTED ||
                          response->result == PostResult::PROCESSING_PENDING;
    if (!isPoll) { requestPending = false; controlRequestQueued = false; }
    if (response->httpStatus == 401) handleUnauthorized(isPoll ? "HTTP_GET" : "HTTP_POST");
    else if (accepted || response->result == PostResult::CAPTURE_FAILED) {
      const bool wasOffline = !coreOnline || authFailed || transportSecurityFailed;
      authFailed = false; transportSecurityFailed = false; coreOnline = true;
      lastCoreResponseMs = millis();
      if (wasOffline) uiDirty = true;
    } else {
      if (coreOnline) uiDirty = true;
      coreOnline = false;
      statusMessage = "SEM CONFIRMACAO DO CORE";
    }
    if (isPoll) {
      if (accepted || response->result == PostResult::CAPTURE_FAILED) {
        applyStatePayload(response->payload);
        USBSerial.printf("HTTP_GET status=%d state=%s occurrence=%s\n",
                         response->httpStatus, serverState.c_str(), occurrenceId.c_str());
      }
      continue;
    }
    if (response->command == ControlCommand::START_OCCURRENCE ||
        response->command == ControlCommand::START_CAPTURE) {
      startRequestInFlight = false;
      if (accepted) { tStartAck = millis(); captureTimestamp("t_start_ack", tStartAck); USBSerial.println("START_ACK"); }
      else { reconcilePending = true; reconcileWasStart = true; statusMessage = "CONFIRMANDO CORE"; USBSerial.println("START_ERROR_RECONCILE_CORE"); }
    } else if (response->command == ControlCommand::STOP_CAPTURE) {
      stopRequestInFlight = false;
      if (accepted) { tStopAck = millis(); captureTimestamp("t_stop_ack", tStopAck); USBSerial.println("STOP_ACK"); }
      else { reconcilePending = true; reconcileWasStart = false; USBSerial.println("STOP_ERROR_RECONCILE_CORE"); }
    } else if (response->command == ControlCommand::CONCLUDE_OCCURRENCE) {
      concludeRequestInFlight = false;
      if (accepted) USBSerial.println("CONCLUDE_ACK");
      else { reconcilePending = true; statusMessage = "PARADA NAO CONFIRMADA"; }
    } else if (response->command == ControlCommand::ANALYZE_OCCURRENCE) {
      analysisStatus = accepted ? "QUEUED" : "FAILED";
      analysisMessage = accepted ? "ANALISE EM SEGUNDO PLANO" : "FALHA: PODE TENTAR NOVAMENTE";
      showAnalysis = true;
    } else if (response->command == ControlCommand::HYPOTHESIS_DECISION) {
      // Server confirmation, not the tap, is authoritative.
      if (accepted) {
        const String confirmed = jsonStringValue(response->payload, "decision");
        if (confirmed == "CONFIRM") showGuidance = true;
      }
    }
    if (accepted || response->result == PostResult::CAPTURE_FAILED)
      applyStatePayload(response->payload);
    pendingControlCommand = ControlCommand::NONE;
    uiDirty = true;
    lastPollMs = 0; // reconcile from a fresh snapshot after every command
  }
}

void serviceDeferredRequests() {
  if (startRequestInFlight && !controlRequestQueued &&
      elapsed(millis(), startHttpNotBeforeMs)) {
    tStartHttpSent = millis();
    captureTimestamp("t_start_http_sent", tStartHttpSent);
    USBSerial.println("START_SENT");
    const String commandId = nextCommandId();
    const bool newOccurrence = pendingControlCommand == ControlCommand::START_OCCURRENCE;
    const String body = newOccurrence
        ? String("{\"client\":\"safe_field_operational_v1\",\"protocol_version\":1,\"command_id\":\"") +
              commandId + "\"}"
        : String("{\"occurrence_id\":\"") + jsonEscape(occurrenceId) +
              "\",\"command_id\":\"" + commandId + "\"}";
    if (!enqueueControlRequest(
            pendingControlCommand,
            newOccurrence ? kStartPath : kStartCapturePath,
            body,
            kHttpTimeoutMs)) {
      startRequestInFlight = false;
      reconcilePending = true;
      reconcileWasStart = true;
      statusMessage = "FILA DE REDE INDISPONIVEL";
    } else controlRequestQueued = true;
    return;
  }
  if (stopRequestInFlight && !controlRequestQueued &&
      elapsed(millis(), stopHttpNotBeforeMs)) {
    USBSerial.println("STOP_SENT");
    const String body = String("{\"occurrence_id\":\"") + jsonEscape(occurrenceId) +
        "\",\"capture_id\":\"" + jsonEscape(activeCaptureId) +
        "\",\"command_id\":\"" + nextCommandId() + "\"}";
    if (!enqueueControlRequest(ControlCommand::STOP_CAPTURE, kStopCapturePath,
                               body, kFinishHttpTimeoutMs)) {
      stopRequestInFlight = false;
      reconcilePending = true;
      reconcileWasStart = false;
      statusMessage = "FILA DE REDE INDISPONIVEL";
    } else controlRequestQueued = true;
    return;
  }
  if (concludeRequestInFlight && !controlRequestQueued &&
      elapsed(millis(), concludeHttpNotBeforeMs)) {
    USBSerial.println("CONCLUDE_SENT");
    const String body = String("{\"occurrence_id\":\"") + jsonEscape(occurrenceId) +
        "\",\"command_id\":\"" + nextCommandId() + "\"}";
    if (!enqueueControlRequest(ControlCommand::CONCLUDE_OCCURRENCE, kFinishPath,
                               body, kFinishHttpTimeoutMs)) {
      concludeRequestInFlight = false;
      statusMessage = "FILA DE REDE INDISPONIVEL";
    } else controlRequestQueued = true;
  }
}

void markAction(uint16_t index, const char *status) {
  if (hypothesisStatus != "OFFICER_CONFIRMED" || index >= guidance.size() || requestPending) return;
  const GuidanceItem &entry = guidance[index];
  const String body = String("{\"hypothesis_id\":\"") + jsonEscape(hypothesisId) +
      "\",\"action_id\":\"" + jsonEscape(entry.actionId) + "\",\"status\":\"" + status +
      "\",\"command_id\":\"" + nextCommandId() + "\"}";
  enqueueControlRequest(ControlCommand::GUIDANCE_ACTION, kActionPath, body, kHttpTimeoutMs);
}

void scrollGuidance(int8_t direction) {
  if (guidance.empty()) return;
  const int32_t candidate = static_cast<int32_t>(selectedGuidance) + direction;
  if (candidate < 0 || candidate >= static_cast<int32_t>(guidance.size())) return;
  selectedGuidance = static_cast<uint16_t>(candidate);
  ensureGuidanceSelectionVisible();
  uiDirty = true;
}

void pollCore() {
  if (startRequestInFlight || stopRequestInFlight || concludeRequestInFlight) return;
  enqueueControlRequest(ControlCommand::POLL_STATE, kStatePath, "", kHttpTimeoutMs);
}

void handleTouch(int32_t x, int32_t y) {
  const UiMode mode = currentMode();
  if (requestPending || controlRequestQueued || startRequestInFlight || stopRequestInFlight || concludeRequestInFlight) return;
  USBSerial.printf("TOUCH x=%ld y=%ld mode=%u\n", static_cast<long>(x),
                   static_cast<long>(y), static_cast<unsigned>(mode));
  // The physical FT3168 coordinate origin has varied slightly across boots.
  // This is the only actionable control in STANDBY, so use a deliberately
  if (mode == UiMode::STANDBY && savedResultAvailable && y >= 274 && y <= 330) {
    USBSerial.println("TOUCH_SUGGESTION");
    serverState = "SAVED_RESULT";
    uiDirty = true;
    return;
  }
  // Tolerant region around the visible primary button. A saved result moves
  // it down, but never changes the event's Core-owned capture semantics.
  if (mode == UiMode::STANDBY && y >= (savedResultAvailable ? 338 : 280) && y <= 480) {
    startOccurrence();
    return;
  }
  if (mode == UiMode::SAVED_RESULT && y >= 400) {
    serverState = "STANDBY";
    uiDirty = true;
    return;
  }
  if (mode == UiMode::OCCURRENCE_OPEN) {
    if (y >= 329 && y <= 361) { showAnalysis = true; analyzeOccurrence(); return; }
    if (y >= 230 && y <= 340) startNextCapture();
    else if (y >= 345) concludeOccurrence();
    return;
  }
  if (mode == UiMode::HYPOTHESIS_PROPOSED && y >= 305 && y <= 410) {
    if (x < 137) decideHypothesis(kConfirmPath, "CONFIRM");
    else if (x < 273) decideHypothesis(kRejectPath, "REJECT");
    else decideHypothesis(kDeferPath, "MORE_DATA");
    return;
  }
  if (mode == UiMode::GUIDANCE) {
    if (y >= 105 && y <= 142) {
      scrollGuidance(x < LCD_WIDTH / 2 ? -1 : 1);
      return;
    }
    if (y >= 148 && y < 148 + kGuidanceVisibleRows * 36) {
      const uint16_t index = guidanceScrollOffset +
          static_cast<uint16_t>((y - 148) / 36);
      if (index >= guidance.size()) return;
      selectedGuidance = index;
      ensureGuidanceSelectionVisible();
      uiDirty = true;
      return;
    }
    if (y >= 335 && y <= 418) {
      if (x < 137) markAction(selectedGuidance, "DONE");
      else if (x < 273) markAction(selectedGuidance, "PENDING");
      else markAction(selectedGuidance, "NOT_APPLICABLE");
      return;
    }
  }
  if ((mode == UiMode::PROCESSING_PENDING || mode == UiMode::GUIDANCE_NOT_AVAILABLE) &&
      !captureActive && serverState == "OCCURRENCE_OPEN") {
    if (y >= 250 && y <= 310) startNextCapture();
    else if (y >= 322 && y <= 377) analyzeOccurrence();
    else if (y >= 391 && y <= 451) concludeOccurrence();
    return;
  }
  if (mode == UiMode::REASSESSMENT_REQUIRED && y >= 325 && y <= 415) {
    lastPollMs = 0;
    pollCore();
    return;
  }
  if (mode == UiMode::CAPTURE_FAILED) {
    if (captureActive && !sourceQuiescent && y >= 414) stopCapture();
    return;
  }
  if (mode != UiMode::STANDBY && mode != UiMode::STARTING_CAPTURE &&
      mode != UiMode::SAVING_CAPTURE && mode != UiMode::CONCLUDING_OCCURRENCE &&
      y >= 414) {
    if (captureActive) stopCapture();
    else concludeOccurrence();
  }
}

void serviceTouch() {
  if (!touchReady) return;
  if (!elapsed(millis(), touchArmNotBeforeMs)) {
    touch->IIC_Interrupt_Flag = false;
    return;
  }
  // FT3168 sends a short active-low interrupt pulse.  Preserve the library
  // callback, but sample TP_INT too: this avoids losing a real touch if the
  // ESP32 callback is momentarily masked by Wi-Fi/display work.
  const bool pinIsHigh = digitalRead(TP_INT) == HIGH;
  const bool directFallingEdge = touchIrqWasHigh && !pinIsHigh;
  touchIrqWasHigh = pinIsHigh;
  const bool interruptSignalled = touch->IIC_Interrupt_Flag || directFallingEdge;
  if (interruptSignalled) touch->IIC_Interrupt_Flag = false;
  const int32_t fingers = touch->IIC_Read_Device_Value(
      touch->Arduino_IIC_Touch::Value_Information::TOUCH_FINGER_NUMBER);
  // A bare interrupt with zero fingers can carry old coordinates from the
  // previous screen and must never start a new occurrence.
  if (fingers <= 0) {
    touchContactActive = false;
    return;
  }
  // Only a fresh FT3168 interrupt/falling edge may create an action. The
  // controller can retain the previous coordinates briefly after redraw; a
  // time-only debounce would turn that stale position into a second START.
  if (!interruptSignalled) {
    if (fingers <= 0) touchContactActive = false;
    return;
  }
  // `IIC_Interrupt_Flag` is the controller's new-contact indication.  Some
  // FT3168 revisions retain FINGER_NUMBER=1 after release, so do not require
  // a sampled low-to-high edge before accepting the next *new IRQ*.
  // Repeated stale coordinates are already excluded by the
  // !interruptSignalled return above.
  if (millis() - lastTouchMs < kTouchDebounceMs) return;
  touchContactActive = fingers > 0;
  lastTouchMs = millis();
  const int32_t rawX = touch->IIC_Read_Device_Value(
      touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_X);
  const int32_t rawY = touch->IIC_Read_Device_Value(
      touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_Y);
  const int32_t x = rawX;
  const int32_t y = rawY;
  USBSerial.printf("TOUCH_DOWN raw_x=%ld raw_y=%ld ui_x=%ld ui_y=%ld mode=%u\n",
                   static_cast<long>(rawX), static_cast<long>(rawY),
                   static_cast<long>(x), static_cast<long>(y),
                   static_cast<unsigned>(currentMode()));
  if (x >= 0 && x < LCD_WIDTH && y >= 0 && y < LCD_HEIGHT) handleTouch(x, y);
}

void connectWifi() {
  if (!wifiSsid.length() || WiFi.status() == WL_CONNECTED) return;
  lastWifiAttemptMs = millis();
  coreOnline = false;
  WiFi.disconnect();
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  USBSerial.printf("WIFI CONNECTING ssid=%s\n", wifiSsid.c_str());
  uiDirty = true;
}

void loadConfiguration() {
  wifiSsid = preferences.getString("ssid", "");
  wifiPassword = preferences.getString("psk", "");
  configuredCoreUrl = preferences.getString("core", "");
  apiToken = preferences.getString("api_token", "");
  coreCaPem = preferences.getString("core_ca", "");
  coreBaseUrl = normalizeCoreBase(configuredCoreUrl);
  authFailed = !apiToken.length();
  transportSecurityFailed = coreBaseUrl.length() &&
      (!isValidHttpsBase(coreBaseUrl) || !isValidCaPem(coreCaPem));
}

void handleSerialLine(const String &raw) {
  String command = raw;
  command.trim();
  if ((command.startsWith("SET_") || command.startsWith("CLEAR_")) &&
      (requestPending || pollQueued || reconcilePending)) {
    USBSerial.println("ERR CONFIG_BUSY WAIT_FOR_RECONCILIATION"); return;
  }
  if (command == "START") {
    startOccurrence();
  } else if (command == "NEW_CAPTURE") {
    startNextCapture();
  } else if (command == "ANALYZE") {
    analyzeOccurrence();
  } else if (command == "CONFIRM") {
    decideHypothesis(kConfirmPath, "CONFIRM");
  } else if (command == "REJECT") {
    decideHypothesis(kRejectPath, "REJECT");
  } else if (command == "MORE_DATA") {
    decideHypothesis(kDeferPath, "MORE_DATA");
  } else if (command == "STOP") {
    if (serverState == "CAPTURE_FAILED" &&
        (!captureActive || sourceQuiescent)) {
      USBSerial.println("ERR STOP source_already_quiescent capture_failure_is_terminal");
    } else {
      stopCapture();
    }
  } else if (command == "CONCLUDE") {
    concludeOccurrence();
  } else if (command == "POLL") {
    pollCore();
  } else if (command.startsWith("ACTION ")) {
    const int separator = command.indexOf(' ', 7);
    if (separator < 0) {
      USBSerial.println("ERR ACTION format: ACTION <numero> DONE|PENDING|NOT_APPLICABLE");
      return;
    }
    const int index = command.substring(7, separator).toInt() - 1;
    const String status = command.substring(separator + 1);
    if (index < 0 || index >= static_cast<int>(guidance.size()) ||
        (status != "DONE" && status != "PENDING" && status != "NOT_APPLICABLE")) {
      USBSerial.println("ERR ACTION invalid_index_or_status");
      return;
    }
    markAction(static_cast<uint16_t>(index), status.c_str());
#if SAFE_FIELD_ENABLE_TEST_HOOKS
  } else if (command.startsWith("APPLY_JSON ")) {
    const String payload = command.substring(11);
    applyStatePayload(payload);
    USBSerial.printf("OK APPLY_JSON state=%s mode=%u\n", serverState.c_str(),
                     static_cast<unsigned>(currentMode()));
#else
  } else if (command.startsWith("APPLY_JSON")) {
    USBSerial.println("ERR APPLY_JSON disabled_in_production");
#endif
  } else if (command.startsWith("SET_WIFI ")) {
    const String value = command.substring(9);
    const int separator = value.indexOf('\t');
    if (separator <= 0 || separator >= static_cast<int>(value.length()) - 1) {
      USBSerial.println("ERR SET_WIFI format: SET_WIFI <ssid><TAB><password>");
      return;
    }
    wifiSsid = value.substring(0, separator);
    wifiPassword = value.substring(separator + 1);
    preferences.putString("ssid", wifiSsid);
    preferences.putString("psk", wifiPassword);
    USBSerial.printf("OK WIFI SAVED ssid=%s password=REDACTED\n", wifiSsid.c_str());
    connectWifi();
  } else if (command.startsWith("SET_CORE ")) {
    String candidate = command.substring(9);
    candidate.trim();
    const String candidateBase = normalizeCoreBase(candidate);
    if (!isValidHttpsBase(candidateBase)) {
      USBSerial.println("ERR SET_CORE requires https:// origin without credentials, path, query or fragment");
      return;
    }
    configuredCoreUrl = candidate;
    coreBaseUrl = candidateBase;
    preferences.putString("core", configuredCoreUrl);
    USBSerial.printf("OK CORE SAVED base=%s\n", coreBaseUrl.c_str());
    transportSecurityFailed = !isValidCaPem(coreCaPem);
    statusMessage = transportSecurityFailed ? "TLS CONFIG NECESSARIA" : "";
    lastPollMs = 0;
  } else if (command.startsWith("SET_CA_PEM ")) {
    String candidate = command.substring(11);
    candidate.replace("\\n", "\n");
    if (!isValidCaPem(candidate)) {
      USBSerial.println("ERR SET_CA_PEM requires one escaped PEM certificate (use \\n between lines, max 3900 bytes)");
      return;
    }
    if (preferences.putString("core_ca", candidate) == 0 ||
        preferences.getString("core_ca", "") != candidate) {
      preferences.remove("core_ca");
      USBSerial.println("ERR SET_CA_PEM NVS_WRITE_FAILED");
      return;
    }
    coreCaPem = candidate;
    transportSecurityFailed = !isValidHttpsBase(coreBaseUrl);
    statusMessage = transportSecurityFailed ? "TLS CONFIG NECESSARIA" : "";
    lastPollMs = 0;
    USBSerial.println("OK CORE CA SAVED ca=SET_REDACTED");
    uiDirty = true;
  } else if (command == "CLEAR_CA") {
    preferences.remove("core_ca");
    coreCaPem = "";
    transportSecurityFailed = true;
    coreOnline = false;
    statusMessage = "TLS CONFIG NECESSARIA";
    USBSerial.println("OK CORE CA CLEARED ca=REDACTED");
    uiDirty = true;
  } else if (command.startsWith("SET_TOKEN ")) {
    String candidate = command.substring(10);
    candidate.trim();
    if (!candidate.length() || candidate.indexOf(' ') >= 0 ||
        candidate.indexOf('\t') >= 0 || candidate.length() > 512) {
      USBSerial.println("ERR SET_TOKEN requires one non-empty bearer token without whitespace");
      return;
    }
    apiToken = candidate;
    preferences.putString("api_token", apiToken);
    authFailed = false;
    statusMessage = "";
    lastPollMs = 0;
    USBSerial.println("OK API TOKEN SAVED token=REDACTED");
    uiDirty = true;
  } else if (command == "CLEAR_TOKEN") {
    preferences.remove("api_token");
    apiToken = "";
    authFailed = true;
    coreOnline = false;
    statusMessage = "TOKEN NAO CONFIGURADO";
    USBSerial.println("OK API TOKEN CLEARED token=REDACTED");
    uiDirty = true;
  } else if (command == "SHOW_CONFIG") {
    USBSerial.printf("CONFIG ssid=%s password=REDACTED core=%s base=%s token=%s ca=%s tls=%s ip=%s\n",
                     wifiSsid.length() ? wifiSsid.c_str() : "NOT_SET",
                     configuredCoreUrl.length() ? configuredCoreUrl.c_str() : "NOT_SET",
                     coreBaseUrl.length() ? coreBaseUrl.c_str() : "NOT_SET",
                     apiToken.length() ? "SET_REDACTED" : "NOT_SET",
                     coreCaPem.length() ? "SET_REDACTED" : "NOT_SET",
                     (!transportSecurityFailed && isValidHttpsBase(coreBaseUrl) &&
                      isValidCaPem(coreCaPem)) ? "READY" : "BLOCKED",
                     WiFi.localIP().toString().c_str());
  } else if (command == "SHOW_STATE") {
    USBSerial.printf("STATE state=%s capture=%s source_quiescent=%s occurrence=%s hypothesis=%s status=%s guidance=%u start_wait=%s stop_wait=%s raw24_frames=%lu\n",
                     serverState.c_str(), captureActive ? "true" : "false",
                     sourceQuiescent ? "true" : "false",
                     occurrenceId.c_str(), hypothesisId.c_str(),
                     hypothesisStatus.c_str(), static_cast<unsigned>(guidance.size()),
                     startAwaitingAudio ? "true" : "false",
                     stopAwaitingCore ? "true" : "false",
                     static_cast<unsigned long>(lastValidRaw24Frames));
  } else {
#if SAFE_FIELD_ENABLE_TEST_HOOKS
    USBSerial.println("ERR commands: START NEW_CAPTURE STOP CONCLUDE CONFIRM REJECT MORE_DATA ACTION POLL APPLY_JSON SET_WIFI SET_CORE SET_CA_PEM CLEAR_CA SET_TOKEN CLEAR_TOKEN SHOW_CONFIG SHOW_STATE");
#else
    USBSerial.println("ERR commands: START NEW_CAPTURE STOP CONCLUDE CONFIRM REJECT MORE_DATA ACTION POLL SET_WIFI SET_CORE SET_CA_PEM CLEAR_CA SET_TOKEN CLEAR_TOKEN SHOW_CONFIG SHOW_STATE");
#endif
  }
}

void serviceSerial() {
  while (USBSerial.available()) {
    const char c = static_cast<char>(USBSerial.read());
    if (c == '\n') {
      handleSerialLine(serialLine);
      serialLine = "";
    } else if (c != '\r' && serialLine.length() < kMaxCommandLength) {
      serialLine += c;
    }
  }
}

void updateBattery() {
  if (!pmuReady) return;
  const int next = power.isBatteryConnect() ? power.getBatteryPercent() : -1;
  if (next != batteryPercent) {
    batteryPercent = next;
    batteryDirty = true;
  }
}

}  // namespace

void setup() {
  USBSerial.begin(kSerialBaud);
  delay(250);
  USBSerial.println("SAFE_FIELD_OPERATIONAL_V1_BOOT protocol=1 build=gate2e-p0-20261002");
  commandBootNonce = esp_random();
  controlRequestQueue = xQueueCreate(2, sizeof(ControlRequest *));
  controlResponseQueue = xQueueCreate(2, sizeof(ControlResponse *));
  if (controlRequestQueue != nullptr && controlResponseQueue != nullptr) {
    xTaskCreatePinnedToCore(controlNetworkTask, "safe-field-net", 12288, nullptr,
                            1, nullptr, 0);
  } else {
    USBSerial.println("FAIL CONTROL NETWORK QUEUE");
  }

  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);
  displayReady = gfx->begin();
  USBSerial.println(displayReady ? "PASS DISPLAY INIT" : "FAIL DISPLAY INIT");
  if (displayReady) gfx->fillScreen(kBlack);

  Wire.begin(IIC_SDA, IIC_SCL);
  pmuReady = power.begin(Wire, AXP2101_SLAVE_ADDRESS, IIC_SDA, IIC_SCL);
  if (pmuReady) {
    power.enableBattDetection();
    power.enableBattVoltageMeasure();
  }
  USBSerial.println(pmuReady ? "PASS AXP2101 INIT" : "WARN AXP2101 NOT DETECTED");

  // The official Waveshare examples retry FT3168 discovery because the touch
  // controller can become ready slightly after the ESP32-S3 boot.  A bounded
  // retry preserves an operational boot even if the controller is absent,
  // while avoiding the permanent no-touch state caused by a single early I2C
  // probe.
  for (uint8_t attempt = 1; attempt <= 10 && !touchReady; ++attempt) {
    touchReady = initializeTouchController(false);
    if (!touchReady) {
      USBSerial.printf("FT3168 retry %u/10\n", static_cast<unsigned>(attempt));
      delay(200);
    }
  }
  USBSerial.println(touchReady ? "PASS FT3168 INIT" : "WARN FT3168 NOT DETECTED SERIAL_FALLBACK_ACTIVE");

  preferences.begin("safe-field", false);
  loadConfiguration();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false); // demo runtime: do not add radio power-save latency
  updateBattery();
  connectWifi();
  renderUi();
  USBSerial.printf("SAFE_FIELD_OPERATIONAL_V1_READY core=%s password=REDACTED token=%s ca=%s tls=%s\n",
                   coreBaseUrl.length() ? coreBaseUrl.c_str() : "NOT_SET",
                   apiToken.length() ? "SET_REDACTED" : "NOT_SET",
                   coreCaPem.length() ? "SET_REDACTED" : "NOT_SET",
                   (!transportSecurityFailed && isValidHttpsBase(coreBaseUrl) &&
                    isValidCaPem(coreCaPem)) ? "READY" : "BLOCKED");
}

void loop() {
  const uint32_t now = millis();
  serviceSerial();
  // A touch controller that booted late must recover without requiring the
  // wearer to reset the device or reconnect USB.
  if (!touchReady && elapsed(now, lastTouchProbeMs + 2000)) {
    lastTouchProbeMs = now;
    touchReady = initializeTouchController(true);
  }
  serviceTouch();
  serviceControlResponses();
  serviceNetworkWatchdog();

  // Flush touch acknowledgement before any potentially slow HTTPS operation.
  if (uiDirty) renderUi();
  serviceDeferredRequests();

  if (WiFi.status() != WL_CONNECTED && wifiSsid.length() &&
      elapsed(now, lastWifiAttemptMs + kWifiRetryMs)) {
    connectWifi();
  }
  if (elapsed(now, lastPollMs + kPollPeriodMs)) {
    lastPollMs = now;
    pollCore();
  }
  if ((startAwaitingAudio || stopAwaitingCore || concludeAwaitingCore ||
       finalizationPending) &&
      elapsed(now, lastUiAnimationMs + kProgressUpdatePeriodMs)) {
    lastUiAnimationMs = now;
    updateProgressIndicator();
  }
  if (elapsed(now, lastBatteryReadMs + 10000)) {
    lastBatteryReadMs = now;
    updateBattery();
  }
  if (uiDirty) renderUi();
  else if (batteryDirty) {
    renderBatteryField();
    batteryDirty = false;
  }
  delay(10);
}
