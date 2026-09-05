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

#include "pin_config.h"
#include <XPowersLib.h>

#ifndef SAFE_FIELD_ENABLE_TEST_HOOKS
#define SAFE_FIELD_ENABLE_TEST_HOOKS 0
#endif

namespace {

constexpr uint32_t kSerialBaud = 115200;
constexpr uint32_t kPollPeriodMs = 700;
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
constexpr uint8_t kMaxGuidanceItems = 5;

constexpr char kStatePath[] = "/api/v1/operational/wearable/state";
constexpr char kStartPath[] = "/api/v1/occurrences/start";
constexpr char kConfirmPath[] = "/api/v1/hypotheses/confirm";
constexpr char kRejectPath[] = "/api/v1/hypotheses/reject";
constexpr char kDeferPath[] = "/api/v1/hypotheses/defer";
constexpr char kActionPath[] = "/api/v1/guidance/action";
constexpr char kFinishPath[] = "/api/v1/occurrences/finish";

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
  OCCURRENCE_ACTIVE,
  HYPOTHESIS_PROPOSED,
  GUIDANCE,
  REASSESSMENT_REQUIRED,
  PROCESSING_PENDING,
  GUIDANCE_NOT_AVAILABLE,
  CAPTURE_FAILED,
};

enum class PostResult : uint8_t {
  ERROR,
  ACCEPTED,
  PROCESSING_PENDING,
  CAPTURE_FAILED,
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
String hypothesisId;
String hypothesisLabel;
String hypothesisStatus;
String statusMessage;
String apiVersion;
GuidanceItem guidance[kMaxGuidanceItems];
uint8_t guidanceCount = 0;
uint8_t selectedGuidance = 0;

bool displayReady = false;
bool touchReady = false;
bool pmuReady = false;
bool coreOnline = false;
bool authFailed = false;
bool transportSecurityFailed = false;
bool captureActive = false;
bool sourceQuiescent = true;
bool finalizationPending = false;
bool requestPending = false;
bool uiDirty = true;
int batteryPercent = -1;
uint32_t lastPollMs = 0;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastBatteryReadMs = 0;
uint32_t lastTouchMs = 0;

void touchInterrupt() { touch->IIC_Interrupt_Flag = true; }

bool elapsed(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
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
                     const String &url, uint32_t timeoutMs) {
  if (!secureTransportReady()) return false;
  tlsClient.setCACert(coreCaPem.c_str());
  tlsClient.setHandshakeTimeout(max<uint32_t>(1, (timeoutMs + 999) / 1000));
  http.setConnectTimeout(timeoutMs);
  http.setTimeout(timeoutMs);
  http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
  if (!http.begin(tlsClient, url)) {
    failTransportSecurity("TLS_BEGIN_FAILED");
    return false;
  }
  return true;
}

void clearOperationalDetails() {
  occurrenceId = "";
  hypothesisId = "";
  hypothesisLabel = "";
  hypothesisStatus = "";
  statusMessage = "";
  guidanceCount = 0;
  selectedGuidance = 0;
  finalizationPending = false;
}

void parseGuidance(const String &payload) {
  guidanceCount = 0;
  selectedGuidance = 0;
  const String guidanceObject = jsonObjectValue(payload, "guidance");
  String items = jsonArrayValue(guidanceObject.length() ? guidanceObject : payload,
                                "items");
  if (!items.length()) return;

  int cursor = 1;
  while (cursor < static_cast<int>(items.length()) &&
         guidanceCount < kMaxGuidanceItems) {
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
    GuidanceItem &entry = guidance[guidanceCount];
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
    if (entry.actionId.length() && entry.text.length()) ++guidanceCount;
    cursor = objectEnd + 1;
  }
}

void applyStatePayload(const String &payload) {
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
  if (nextState.length()) serverState = nextState;

  String nextOccurrence = jsonStringValue(payload, "occurrence_id");
  if (!nextOccurrence.length()) {
    const String occurrence = jsonObjectValue(payload, "occurrence");
    nextOccurrence = jsonStringValue(occurrence, "occurrence_id");
  }
  if (nextOccurrence.length()) occurrenceId = nextOccurrence;

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
    captureActive = false;
    sourceQuiescent = true;
    clearOperationalDetails();
  } else if (serverState == "CAPTURE_FAILED") {
    // The Core can detect corruption while its reader still has in-flight
    // delivery. Preserve its explicit capture flag until source_quiescent.
    if (sourceQuiescentPresent && sourceQuiescent) captureActive = false;
    finalizationPending = false;
  } else if (!captureFlagPresent && occurrenceId.length() && !finalizationPending) {
    captureActive = true;
    sourceQuiescent = false;
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
    guidanceCount = 0;
    selectedGuidance = 0;
  }
  uiDirty = true;
}

UiMode currentMode() {
  if (serverState == "CAPTURE_FAILED") return UiMode::CAPTURE_FAILED;
  // Finalization has priority over stale hypothesis/guidance fields retained
  // for audit display while the Core drains pending work.
  if (finalizationPending) return UiMode::PROCESSING_PENDING;
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
  if (hypothesisStatus == "OFFICER_CONFIRMED" && guidanceCount > 0) {
    return UiMode::GUIDANCE;
  }
  if (serverState == "PROCESSING_PENDING" ||
      (hypothesisStatus == "OFFICER_CONFIRMED" && guidanceCount == 0)) {
    return UiMode::PROCESSING_PENDING;
  }
  if (captureActive || serverState == "OCCURRENCE_ACTIVE") {
    return UiMode::OCCURRENCE_ACTIVE;
  }
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
  gfx->setTextColor(kMuted);
  gfx->setCursor(314, 67);
  gfx->print(batteryPercent >= 0 ? String("BAT ") + batteryPercent + "%" : "USB");
  centeredText(title, 92, 2, accent);
}

void renderStandby() {
  renderHeader("STANDBY", kBlue);
  centeredText("SEM OCORRENCIA", 162, 2, kMuted);
  centeredText("SEM GRAVACAO", 198, 2, kMuted);
  button(42, 330, LCD_WIDTH - 84, 82, kGreen, "INICIAR OCORRENCIA", 2);
}

void renderOccurrence() {
  renderHeader("OCORRENCIA ATIVA", kGreen);
  gfx->fillRoundRect(25, 135, LCD_WIDTH - 50, 205, 18, kPanel);
  centeredText("CAPTURA CONTINUA", 174, 2, kGreen);
  centeredText("AUDIO", 228, 2, kMuted);
  centeredText("MONITORANDO", 265, 3, kWhite);
  centeredText("silencio nao encerra", 311, 1, kMuted);
  button(38, 418, LCD_WIDTH - 76, 61, kDarkRed, "FINALIZAR OCORRENCIA", 2);
}

void renderHypothesis() {
  renderHeader("HIPOTESE PROPOSTA", kAmber);
  gfx->fillRoundRect(20, 124, LCD_WIDTH - 40, 172, 18, kPanel);
  centeredText("POSSIVEL", 150, 2, kAmber);
  centeredText(clipped(hypothesisLabel.length() ? hypothesisLabel : "ANALISE EM CURSO", 25),
               196, 2, kWhite);
  centeredText("DECISAO DO POLICIAL", 253, 1, kMuted);
  button(10, 324, 126, 64, kGreen, "CONFIRMAR", 1);
  button(142, 324, 126, 64, kDarkRed, "DESCARTAR", 1);
  button(274, 324, 126, 64, kBlue, "MAIS DADOS", 1);
  button(38, 422, LCD_WIDTH - 76, 55, kDarkRed, "FINALIZAR OCORRENCIA", 2);
}

String statusLabel(const String &status) {
  if (status == "DONE") return "REALIZADO";
  if (status == "NOT_APPLICABLE") return "NAO APLICAVEL";
  return "PENDENTE";
}

void renderGuidance() {
  renderHeader(clipped(hypothesisLabel, 26), kGreen);
  centeredText("PRIORIDADES", 112, 2, kWhite);
  const int16_t rowHeight = 38;
  for (uint8_t index = 0; index < guidanceCount; ++index) {
    const int16_t y = 145 + index * rowHeight;
    const bool selected = index == selectedGuidance;
    gfx->fillRoundRect(14, y, LCD_WIDTH - 28, rowHeight - 4, 8,
                       selected ? 0x2124 : kPanel);
    gfx->setTextSize(1);
    gfx->setTextColor(selected ? kWhite : kMuted);
    gfx->setCursor(22, y + 7);
    gfx->printf("%u. %s", index + 1, clipped(guidance[index].text, 43).c_str());
    gfx->setCursor(290, y + 21);
    gfx->setTextColor(guidance[index].status == "DONE" ? kGreen : kAmber);
    gfx->print(statusLabel(guidance[index].status));
  }
  button(7, 351, 128, 53, kGreen, "REALIZADO", 1);
  button(141, 351, 128, 53, kBlue, "PENDENTE", 1);
  button(275, 351, 128, 53, kMuted, "NAO APLICAVEL", 1);
  button(38, 429, LCD_WIDTH - 76, 51, kDarkRed, "FINALIZAR OCORRENCIA", 2);
}

void renderReassessment() {
  renderHeader("REAVALIACAO NECESSARIA", kRed);
  gfx->fillRoundRect(22, 132, LCD_WIDTH - 44, 185, 18, kPanel);
  centeredText("NOVAS INFORMACOES", 170, 2, kAmber);
  centeredText("PODEM ALTERAR", 211, 2, kWhite);
  centeredText("A HIPOTESE", 249, 2, kWhite);
  button(85, 342, LCD_WIDTH - 170, 65, kBlue, "VER", 2);
  button(38, 429, LCD_WIDTH - 76, 51, kDarkRed, "FINALIZAR OCORRENCIA", 2);
}

void renderPending(bool unavailable) {
  const bool stopping = finalizationPending || !captureActive;
  renderHeader(stopping ? "FINALIZANDO" : "OCORRENCIA ATIVA",
               stopping ? kAmber : kGreen);
  gfx->fillRoundRect(22, 145, LCD_WIDTH - 44, 190, 18, kPanel);
  centeredText(unavailable ? "ORIENTACAO" : "PROCESSAMENTO", 185, 2, kMuted);
  centeredText(unavailable ? "INDISPONIVEL" : "PENDENTE", 230, 3,
               unavailable ? kAmber : kBlue);
  centeredText(stopping ? "CAPTURA ENCERRADA" : "CAPTURA CONTINUA", 295, 1,
               stopping ? kAmber : kGreen);
  button(38, 418, LCD_WIDTH - 76, 61, kDarkRed,
         stopping ? "TENTAR FINALIZAR" : "FINALIZAR OCORRENCIA", 2);
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
    case UiMode::OCCURRENCE_ACTIVE: renderOccurrence(); break;
    case UiMode::HYPOTHESIS_PROPOSED: renderHypothesis(); break;
    case UiMode::GUIDANCE: renderGuidance(); break;
    case UiMode::REASSESSMENT_REQUIRED: renderReassessment(); break;
    case UiMode::PROCESSING_PENDING: renderPending(false); break;
    case UiMode::GUIDANCE_NOT_AVAILABLE: renderPending(true); break;
    case UiMode::CAPTURE_FAILED: renderCaptureFailed(); break;
  }
  if (requestPending) {
    gfx->fillRect(0, LCD_HEIGHT - 14, LCD_WIDTH, 14, kAmber);
    centeredText("ENVIANDO...", LCD_HEIGHT - 12, 1, kBlack);
  }
}

bool addAuthorization(HTTPClient &http) {
  if (!apiToken.length()) {
    authFailed = true;
    coreOnline = false;
    statusMessage = "TOKEN NAO CONFIGURADO";
    uiDirty = true;
    return false;
  }
  http.addHeader("Authorization", String("Bearer ") + apiToken);
  return true;
}

void handleUnauthorized(const char *operation) {
  authFailed = true;
  coreOnline = false;
  statusMessage = "AUTORIZACAO NEGADA";
  uiDirty = true;
  USBSerial.printf("%s status=401 auth=FAILED token=REDACTED\n", operation);
}

PostResult postJson(const char *path, const String &body,
                    uint32_t timeoutMs = kHttpTimeoutMs) {
  if (WiFi.status() != WL_CONNECTED || !coreBaseUrl.length() ||
      !apiToken.length() || requestPending) {
    if (!apiToken.length()) {
      authFailed = true;
      statusMessage = "TOKEN NAO CONFIGURADO";
    }
    USBSerial.printf("ERR HTTP_POST path=%s core_offline_busy_or_unauthorized\n", path);
    uiDirty = true;
    return PostResult::ERROR;
  }
  requestPending = true;
  uiDirty = true;
  WiFiClientSecure tlsClient;
  HTTPClient http;
  const String url = coreBaseUrl + path;
  if (!beginSecureHttp(http, tlsClient, url, timeoutMs)) {
    requestPending = false;
    return PostResult::ERROR;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Accept", "application/json");
  http.addHeader("X-Safe-Field-Client", "wearable-operational-v1");
  if (!addAuthorization(http)) {
    http.end();
    requestPending = false;
    return PostResult::ERROR;
  }
  const int status = http.POST(body);
  const String payload = status > 0 ? http.getString() : "";
  const bool accepted = status >= 200 && status < 300 && jsonOk(payload);
  const String responseState = jsonStringValue(payload, "state");
  const bool captureFailed = responseState == "CAPTURE_FAILED" &&
      !jsonBoolValue(payload, "retryable", true);
  const bool pending = status >= 200 && status < 300 && !jsonOk(payload) &&
      (responseState == "STOPPING" || responseState == "PROCESSING_PENDING" ||
       responseState == "FINALIZATION_PENDING" ||
       jsonBoolValue(payload, "finalization_pending", false) ||
       jsonBoolValue(payload, "retryable", false));
  if (status == 401) {
    handleUnauthorized("HTTP_POST");
  } else if (captureFailed) {
    authFailed = false;
    transportSecurityFailed = false;
    coreOnline = true;
    applyStatePayload(payload);
  } else if (accepted || pending) {
    authFailed = false;
    transportSecurityFailed = false;
    coreOnline = true;
    statusMessage = "";
    applyStatePayload(payload);
  } else {
    coreOnline = status > 0;
  }
  requestPending = false;
  uiDirty = true;
  if (status != 401) {
    USBSerial.printf("HTTP_POST status=%d path=%s result=%s\n", status, path,
                     accepted ? "ACCEPTED" :
                     (pending ? "PROCESSING_PENDING" :
                      (captureFailed ? "CAPTURE_FAILED" : "ERROR")));
  }
  http.end();
  lastPollMs = 0;
  if (accepted) return PostResult::ACCEPTED;
  if (pending) return PostResult::PROCESSING_PENDING;
  if (captureFailed) return PostResult::CAPTURE_FAILED;
  return PostResult::ERROR;
}

void startOccurrence() {
  if (postJson(kStartPath,
               "{\"client\":\"safe_field_operational_v1\",\"protocol_version\":1}") ==
      PostResult::ACCEPTED) {
    captureActive = true;
    sourceQuiescent = false;
    finalizationPending = false;
    serverState = "OCCURRENCE_ACTIVE";
    uiDirty = true;
  }
}

void decideHypothesis(const char *path, const char *decision) {
  if (!hypothesisId.length()) {
    USBSerial.println("ERR DECISION hypothesis_id_missing");
    return;
  }
  if (postJson(path, String("{\"hypothesis_id\":\"") + jsonEscape(hypothesisId) +
                         "\",\"decision\":\"" + decision + "\"}") ==
      PostResult::ACCEPTED) {
    if (strcmp(decision, "CONFIRM") == 0) {
      hypothesisStatus = "OFFICER_CONFIRMED";
      serverState = "PROCESSING_PENDING";
    } else {
      hypothesisId = "";
      hypothesisLabel = "";
      hypothesisStatus = "";
      guidanceCount = 0;
      serverState = "OCCURRENCE_ACTIVE";
    }
    uiDirty = true;
  }
}

void finishOccurrence() {
  const PostResult result = postJson(
      kFinishPath,
      String("{\"occurrence_id\":\"") + jsonEscape(occurrenceId) +
          "\",\"processing_timeout\":" +
          String(kFinishProcessingTimeoutSeconds, 1) + "}",
      kFinishHttpTimeoutMs);
  if (result == PostResult::ACCEPTED) {
    captureActive = false;
    sourceQuiescent = true;
    serverState = "STANDBY";
    clearOperationalDetails();
    uiDirty = true;
  } else if (result == PostResult::PROCESSING_PENDING) {
    captureActive = false;
    finalizationPending = true;
    serverState = "PROCESSING_PENDING";
    uiDirty = true;
  } else if (result == PostResult::CAPTURE_FAILED) {
    finalizationPending = false;
    serverState = "CAPTURE_FAILED";
    uiDirty = true;
  }
}

void markAction(uint8_t index, const char *status) {
  if (hypothesisStatus != "OFFICER_CONFIRMED" || index >= guidanceCount) {
    USBSerial.println("ERR ACTION guidance_not_confirmed_or_index_invalid");
    return;
  }
  const GuidanceItem &entry = guidance[index];
  if (postJson(kActionPath,
               String("{\"hypothesis_id\":\"") + jsonEscape(hypothesisId) +
                   "\",\"action_id\":\"" + jsonEscape(entry.actionId) +
                   "\",\"status\":\"" + status + "\"}") ==
      PostResult::ACCEPTED) {
    guidance[index].status = status;
    uiDirty = true;
  }
}

void pollCore() {
  if (WiFi.status() != WL_CONNECTED || !coreBaseUrl.length() ||
      !apiToken.length() || requestPending) {
    if (!apiToken.length()) {
      authFailed = true;
      coreOnline = false;
      statusMessage = "TOKEN NAO CONFIGURADO";
      uiDirty = true;
    }
    return;
  }
  WiFiClientSecure tlsClient;
  HTTPClient http;
  if (!beginSecureHttp(http, tlsClient, coreBaseUrl + kStatePath,
                       kHttpTimeoutMs)) return;
  http.addHeader("Accept", "application/json");
  http.addHeader("X-Safe-Field-Client", "wearable-operational-v1");
  if (!addAuthorization(http)) {
    http.end();
    return;
  }
  const int status = http.GET();
  if (status == HTTP_CODE_OK) {
    const String payload = http.getString();
    const bool captureFailed = jsonStringValue(payload, "state") ==
        "CAPTURE_FAILED" && !jsonBoolValue(payload, "retryable", true);
    if (jsonOk(payload) || captureFailed) applyStatePayload(payload);
    authFailed = false;
    transportSecurityFailed = false;
    coreOnline = true;
    statusMessage = "";
    USBSerial.printf("HTTP_GET status=%d state=%s occurrence=%s\n", status,
                     serverState.c_str(), occurrenceId.c_str());
  } else if (status == 401) {
    handleUnauthorized("HTTP_GET");
  } else {
    coreOnline = false;
    uiDirty = true;
    USBSerial.printf("HTTP_GET status=%d core=OFFLINE\n", status);
  }
  http.end();
}

void handleTouch(int32_t x, int32_t y) {
  const UiMode mode = currentMode();
  USBSerial.printf("TOUCH x=%ld y=%ld mode=%u\n", static_cast<long>(x),
                   static_cast<long>(y), static_cast<unsigned>(mode));
  if (mode == UiMode::STANDBY && y >= 315 && y <= 430) {
    startOccurrence();
    return;
  }
  if (mode == UiMode::HYPOTHESIS_PROPOSED && y >= 305 && y <= 410) {
    if (x < 137) decideHypothesis(kConfirmPath, "CONFIRM");
    else if (x < 273) decideHypothesis(kRejectPath, "REJECT");
    else decideHypothesis(kDeferPath, "MORE_DATA");
    return;
  }
  if (mode == UiMode::GUIDANCE) {
    if (y >= 140 && y < 140 + guidanceCount * 38) {
      selectedGuidance = min<uint8_t>(guidanceCount - 1, (y - 140) / 38);
      uiDirty = true;
      return;
    }
    if (y >= 340 && y <= 418) {
      if (x < 137) markAction(selectedGuidance, "DONE");
      else if (x < 273) markAction(selectedGuidance, "PENDING");
      else markAction(selectedGuidance, "NOT_APPLICABLE");
      return;
    }
  }
  if (mode == UiMode::REASSESSMENT_REQUIRED && y >= 325 && y <= 415) {
    lastPollMs = 0;
    pollCore();
    return;
  }
  if (mode == UiMode::CAPTURE_FAILED) {
    if (captureActive && !sourceQuiescent && y >= 414) finishOccurrence();
    return;
  }
  if (mode != UiMode::STANDBY && y >= 414) finishOccurrence();
}

void serviceTouch() {
  if (!touchReady || !touch->IIC_Interrupt_Flag ||
      millis() - lastTouchMs < kTouchDebounceMs) return;
  touch->IIC_Interrupt_Flag = false;
  lastTouchMs = millis();
  const int32_t x = touch->IIC_Read_Device_Value(
      touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_X);
  const int32_t y = touch->IIC_Read_Device_Value(
      touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_Y);
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
  if (command == "START") {
    startOccurrence();
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
      finishOccurrence();
    }
  } else if (command == "POLL") {
    pollCore();
  } else if (command.startsWith("ACTION ")) {
    const int separator = command.indexOf(' ', 7);
    if (separator < 0) {
      USBSerial.println("ERR ACTION format: ACTION <1-5> DONE|PENDING|NOT_APPLICABLE");
      return;
    }
    const int index = command.substring(7, separator).toInt() - 1;
    const String status = command.substring(separator + 1);
    if (index < 0 || index >= guidanceCount ||
        (status != "DONE" && status != "PENDING" && status != "NOT_APPLICABLE")) {
      USBSerial.println("ERR ACTION invalid_index_or_status");
      return;
    }
    markAction(index, status.c_str());
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
    USBSerial.printf("STATE state=%s capture=%s source_quiescent=%s occurrence=%s hypothesis=%s status=%s guidance=%u\n",
                     serverState.c_str(), captureActive ? "true" : "false",
                     sourceQuiescent ? "true" : "false",
                     occurrenceId.c_str(), hypothesisId.c_str(),
                     hypothesisStatus.c_str(), guidanceCount);
  } else {
#if SAFE_FIELD_ENABLE_TEST_HOOKS
    USBSerial.println("ERR commands: START CONFIRM REJECT MORE_DATA ACTION STOP POLL APPLY_JSON SET_WIFI SET_CORE SET_CA_PEM CLEAR_CA SET_TOKEN CLEAR_TOKEN SHOW_CONFIG SHOW_STATE");
#else
    USBSerial.println("ERR commands: START CONFIRM REJECT MORE_DATA ACTION STOP POLL SET_WIFI SET_CORE SET_CA_PEM CLEAR_CA SET_TOKEN CLEAR_TOKEN SHOW_CONFIG SHOW_STATE");
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
    uiDirty = true;
  }
}

}  // namespace

void setup() {
  USBSerial.begin(kSerialBaud);
  delay(250);
  USBSerial.println("SAFE_FIELD_OPERATIONAL_V1_BOOT protocol=1");

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

  touchReady = touch->begin();
  USBSerial.println(touchReady ? "PASS FT3168 INIT" : "WARN FT3168 NOT DETECTED SERIAL_FALLBACK_ACTIVE");

  preferences.begin("safe-field", false);
  loadConfiguration();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
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
  serviceTouch();

  if (WiFi.status() != WL_CONNECTED && wifiSsid.length() &&
      elapsed(now, lastWifiAttemptMs + kWifiRetryMs)) {
    connectWifi();
  }
  if (elapsed(now, lastPollMs + kPollPeriodMs)) {
    lastPollMs = now;
    pollCore();
  }
  if (elapsed(now, lastBatteryReadMs + 10000)) {
    lastBatteryReadMs = now;
    updateBattery();
  }
  if (uiDirty) renderUi();
  delay(10);
}
