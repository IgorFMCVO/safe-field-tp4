#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <HTTPClient.h>
#include <HWCDC.h>
#include <Preferences.h>
#include <WiFi.h>
#include <Wire.h>

#include "pin_config.h"
#include <XPowersLib.h>

namespace {

constexpr uint32_t kSerialBaud = 115200;
constexpr uint32_t kPollPeriodMs = 700;
constexpr uint32_t kWifiRetryMs = 10000;
constexpr uint32_t kHttpTimeoutMs = 1200;
constexpr uint32_t kMotorPulseMs = 140;
constexpr size_t kMaxCommandLength = 256;

constexpr uint16_t kBlack = 0x0000;
constexpr uint16_t kWhite = 0xFFFF;
constexpr uint16_t kMuted = 0x8410;
constexpr uint16_t kBlue = 0x05FF;
constexpr uint16_t kGreen = 0x07E0;
constexpr uint16_t kRed = 0xF800;
constexpr uint16_t kAmber = 0xFD20;
constexpr uint16_t kPanel = 0x1082;

HWCDC USBSerial;
Preferences preferences;
XPowersPMU power;

Arduino_DataBus *bus = new Arduino_ESP32QSPI(
    LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
Arduino_GFX *gfx = new Arduino_CO5300(bus, LCD_RESET, 0, LCD_WIDTH, LCD_HEIGHT,
                                      22, 0, 0, 0);

String wifiSsid;
String wifiPassword;
String coreUrl;
String wearableState = "SYSTEM_READY";
String previousWearableState;
String serialLine;

bool displayReady = false;
bool pmuReady = false;
bool coreOnline = false;
bool motorActive = false;
int batteryPercent = -1;
uint32_t lastPollMs = 0;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastBatteryReadMs = 0;
uint32_t motorOffAtMs = 0;

bool elapsed(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

void centeredText(const String &text, int16_t y, uint8_t size,
                  uint16_t color) {
  int16_t x1;
  int16_t y1;
  uint16_t width;
  uint16_t height;
  gfx->setTextSize(size);
  gfx->getTextBounds(text.c_str(), 0, y, &x1, &y1, &width, &height);
  const int16_t centered = (LCD_WIDTH - static_cast<int16_t>(width)) / 2;
  const int16_t x = centered > 10 ? centered : 10;
  gfx->setTextColor(color);
  gfx->setCursor(x, y);
  gfx->print(text);
}

void statusRow(int16_t y, const char *label, const String &value,
               uint16_t valueColor) {
  gfx->setTextSize(2);
  gfx->setTextColor(kMuted);
  gfx->setCursor(30, y);
  gfx->print(label);
  gfx->setTextColor(valueColor);
  gfx->setCursor(205, y);
  gfx->print(value);
}

String audioLabelFor(const String &state) {
  return state == "AUDIO_ACTIVE" ? "ACTIVE" : "QUIET";
}

String headlineFor(const String &state) {
  if (state == "AUDIO_ACTIVE") return "VOZ DETECTADA";
  if (state == "AUDIO_QUIET") return "ESCUTANDO";
  if (state == "OCCURRENCE_ACTIVE") return "OCORRENCIA ATIVA";
  if (state == "ATTENTION") return "ATENCAO";
  if (state == "CAMERA_NOT_CONNECTED") return "CAMERA OFFLINE";
  if (state == "PHOTO_CAPTURED") return "FOTO CAPTURADA";
  return "SYSTEM READY";
}

uint16_t accentFor(const String &state) {
  if (state == "AUDIO_ACTIVE") return kRed;
  if (state == "AUDIO_QUIET") return kGreen;
  if (state == "ATTENTION" || state == "CAMERA_NOT_CONNECTED") return kAmber;
  return kBlue;
}

void renderUi() {
  if (!displayReady) return;

  const bool wifiOnline = WiFi.status() == WL_CONNECTED;
  const uint16_t accent = accentFor(wearableState);
  gfx->fillScreen(kBlack);

  centeredText("SAFE-FIELD", 26, 4, kWhite);
  gfx->drawFastHLine(28, 76, LCD_WIDTH - 56, kBlue);

  statusRow(100, "WiFi", wifiOnline ? "ONLINE" :
            (wifiSsid.length() ? "CONNECTING" : "CONFIG"),
            wifiOnline ? kGreen : kAmber);
  statusRow(128, "Raspberry", coreOnline ? "ONLINE" : "---",
            coreOnline ? kGreen : kMuted);
  statusRow(156, "FPGA", coreOnline ? "LINKED" : "---",
            coreOnline ? kGreen : kMuted);

  if (batteryPercent >= 0) {
    statusRow(184, "Battery", String(batteryPercent) + "%", kWhite);
  } else {
    statusRow(184, "Power", "USB", kWhite);
  }

  gfx->fillRoundRect(22, 225, LCD_WIDTH - 44, 222, 22, kPanel);
  gfx->drawRoundRect(22, 225, LCD_WIDTH - 44, 222, 22, accent);
  gfx->fillCircle(55, 267, 9, accent);
  gfx->setTextSize(2);
  gfx->setTextColor(kWhite);
  gfx->setCursor(78, 257);
  gfx->print(wearableState == "SYSTEM_READY" ? "SISTEMA PRONTO" :
             "OCORRENCIA ATIVA");

  centeredText(headlineFor(wearableState), 315, 3, accent);
  centeredText("Audio", 372, 2, kMuted);
  centeredText(audioLabelFor(wearableState), 402, 4, accent);

  gfx->setTextSize(1);
  gfx->setTextColor(kMuted);
  gfx->setCursor(28, 474);
  gfx->print(coreOnline ? "HTTP /api/v1/wearable/state" :
             "USB serial: SHOW_CONFIG");
}

bool knownWearableState(const String &state) {
  static const char *const states[] = {
      "SYSTEM_READY", "OCCURRENCE_ACTIVE", "AUDIO_QUIET", "AUDIO_ACTIVE",
      "ATTENTION", "CAMERA_NOT_CONNECTED", "PHOTO_CAPTURED",
      "CAPTURE_PHOTO"};
  for (const char *candidate : states) {
    if (state == candidate) return true;
  }
  return false;
}

String jsonStringValue(const String &json, const char *key) {
  const String marker = String('"') + key + '"';
  int index = json.indexOf(marker);
  if (index < 0) return "";
  index = json.indexOf(':', index + marker.length());
  if (index < 0) return "";
  index = json.indexOf('"', index + 1);
  if (index < 0) return "";
  const int end = json.indexOf('"', index + 1);
  if (end < 0) return "";
  return json.substring(index + 1, end);
}

void startMotorPulse() {
  digitalWrite(MOTOR_PIN, HIGH);
  motorActive = true;
  motorOffAtMs = millis() + kMotorPulseMs;
  USBSerial.println("EVENT VIBRATION QUIET_TO_ACTIVE");
}

void setWearableState(const String &nextState) {
  if (!knownWearableState(nextState) || nextState == wearableState) return;
  previousWearableState = wearableState;
  wearableState = nextState;
  if (previousWearableState == "AUDIO_QUIET" &&
      wearableState == "AUDIO_ACTIVE") {
    startMotorPulse();
  }
  USBSerial.printf("STATE %s\n", wearableState.c_str());
  renderUi();
}

void loadConfiguration() {
  wifiSsid = preferences.getString("ssid", "");
  wifiPassword = preferences.getString("psk", "");
  coreUrl = preferences.getString("core", "");
}

void connectWifi() {
  if (!wifiSsid.length() || WiFi.status() == WL_CONNECTED) return;
  lastWifiAttemptMs = millis();
  coreOnline = false;
  WiFi.disconnect();
  WiFi.begin(wifiSsid.c_str(), wifiPassword.c_str());
  USBSerial.printf("WIFI CONNECTING ssid=%s\n", wifiSsid.c_str());
  renderUi();
}

void handleCommand(const String &raw) {
  String command = raw;
  command.trim();
  if (command.startsWith("SET_WIFI ")) {
    const String value = command.substring(9);
    const int separator = value.indexOf('\t');
    if (separator <= 0 || separator >= value.length() - 1) {
      USBSerial.println("ERR SET_WIFI format: SET_WIFI <ssid><TAB><password>");
      return;
    }
    wifiSsid = value.substring(0, separator);
    wifiPassword = value.substring(separator + 1);
    preferences.putString("ssid", wifiSsid);
    preferences.putString("psk", wifiPassword);
    USBSerial.printf("OK WIFI SAVED ssid=%s password=REDACTED\n",
                     wifiSsid.c_str());
    connectWifi();
    return;
  }
  if (command.startsWith("SET_CORE ")) {
    String value = command.substring(9);
    value.trim();
    if (!value.startsWith("http://") || value.indexOf(' ') >= 0) {
      USBSerial.println("ERR SET_CORE requires an http:// URL without spaces");
      return;
    }
    coreUrl = value;
    preferences.putString("core", coreUrl);
    USBSerial.printf("OK CORE SAVED url=%s\n", coreUrl.c_str());
    lastPollMs = 0;
    return;
  }
  if (command == "SHOW_CONFIG") {
    USBSerial.printf("CONFIG ssid=%s password=REDACTED core=%s\n",
                     wifiSsid.length() ? wifiSsid.c_str() : "NOT_SET",
                     coreUrl.length() ? coreUrl.c_str() : "NOT_SET");
    return;
  }
  if (command == "CLEAR_CONFIG") {
    preferences.clear();
    wifiSsid = "";
    wifiPassword = "";
    coreUrl = "";
    WiFi.disconnect(true);
    coreOnline = false;
    USBSerial.println("OK CONFIG CLEARED");
    renderUi();
    return;
  }
  USBSerial.println("ERR commands: SET_WIFI, SET_CORE, SHOW_CONFIG, CLEAR_CONFIG");
}

void serviceSerial() {
  while (USBSerial.available()) {
    const char c = static_cast<char>(USBSerial.read());
    if (c == '\n') {
      handleCommand(serialLine);
      serialLine = "";
    } else if (c != '\r' && serialLine.length() < kMaxCommandLength) {
      serialLine += c;
    }
  }
}

void pollCore() {
  if (WiFi.status() != WL_CONNECTED || !coreUrl.length()) return;
  HTTPClient http;
  http.setConnectTimeout(kHttpTimeoutMs);
  http.setTimeout(kHttpTimeoutMs);
  if (!http.begin(coreUrl)) {
    coreOnline = false;
    return;
  }
  const int status = http.GET();
  if (status == HTTP_CODE_OK) {
    const String payload = http.getString();
    const String nextState = jsonStringValue(payload, "wearable_state");
    const bool wasOnline = coreOnline;
    coreOnline = true;
    if (knownWearableState(nextState)) {
      setWearableState(nextState);
    } else if (!wasOnline) {
      renderUi();
    }
    USBSerial.printf("HTTP %d state=%s ms=%lu\n", status,
                     nextState.c_str(), static_cast<unsigned long>(millis()));
  } else {
    if (coreOnline) {
      coreOnline = false;
      renderUi();
    }
    USBSerial.printf("HTTP %d core=OFFLINE ms=%lu\n", status,
                     static_cast<unsigned long>(millis()));
  }
  http.end();
}

void updateBattery() {
  if (!pmuReady) return;
  const int next = power.isBatteryConnect() ? power.getBatteryPercent() : -1;
  if (next != batteryPercent) {
    batteryPercent = next;
    renderUi();
  }
}

}  // namespace

void setup() {
  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);

  USBSerial.begin(kSerialBaud);
  delay(250);
  USBSerial.println("SAFE_FIELD_WEARABLE_BOOT version=1");

  if (gfx->begin()) {
    displayReady = true;
    gfx->fillScreen(kBlack);
  } else {
    USBSerial.println("FAIL DISPLAY INIT");
  }

  Wire.begin(IIC_SDA, IIC_SCL);
  pmuReady = power.begin(Wire, AXP2101_SLAVE_ADDRESS, IIC_SDA, IIC_SCL);
  if (pmuReady) {
    power.enableBattDetection();
    power.enableBattVoltageMeasure();
    USBSerial.println("PASS AXP2101 INIT");
  } else {
    USBSerial.println("WARN AXP2101 NOT DETECTED");
  }

  preferences.begin("safe-field", false);
  loadConfiguration();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  renderUi();
  updateBattery();
  connectWifi();
  USBSerial.println("SAFE_FIELD_WEARABLE_READY");
}

void loop() {
  const uint32_t now = millis();
  serviceSerial();

  if (motorActive && elapsed(now, motorOffAtMs)) {
    digitalWrite(MOTOR_PIN, LOW);
    motorActive = false;
  }

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

  delay(10);
}
