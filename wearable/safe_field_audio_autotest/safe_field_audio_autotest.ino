#include <Arduino.h>
#include <Arduino_DriveBus_Library.h>
#include <Arduino_GFX_Library.h>
#include <ESP_I2S.h>
#include <HTTPClient.h>
#include <HWCDC.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <Wire.h>
#include <math.h>
#include <memory>

#include "pin_config.h"
#include <XPowersLib.h>
#include "es8311.h"
#include "safe_field_speech_pcm.h"

namespace {

constexpr uint32_t kSerialBaud = 115200;
constexpr uint32_t kPollPeriodMs = 500;
constexpr uint32_t kWifiRetryMs = 10000;
constexpr uint32_t kHttpTimeoutMs = 1200;
constexpr uint32_t kSampleRate = 16000;
constexpr size_t kPcmChunkFrames = 256;

constexpr uint16_t kBlack = 0x0000;
constexpr uint16_t kWhite = 0xFFFF;
constexpr uint16_t kMuted = 0x8410;
constexpr uint16_t kBlue = 0x05FF;
constexpr uint16_t kGreen = 0x07E0;
constexpr uint16_t kRed = 0xF800;
constexpr uint16_t kAmber = 0xFD20;
constexpr uint16_t kPanel = 0x1082;

enum SelfTestPhase : uint8_t {
  SELFTEST_IDLE,
  SELFTEST_PRE_SILENCE,
  SELFTEST_PLAYING,
  SELFTEST_POST_SILENCE,
  SELFTEST_COMPLETE,
  SELFTEST_FAILED,
};

HWCDC USBSerial;
Preferences preferences;
XPowersPMU power;
I2SClass i2s;
es8311_handle_t codec = nullptr;
WebServer server(80);

Arduino_DataBus *bus = new Arduino_ESP32QSPI(
    LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
Arduino_GFX *gfx = new Arduino_CO5300(bus, LCD_RESET, 0, LCD_WIDTH, LCD_HEIGHT,
                                      22, 0, 0, 0);

std::shared_ptr<Arduino_IIC_DriveBus> touchBus =
    std::make_shared<Arduino_HWIIC>(IIC_SDA, IIC_SCL, &Wire);
void touchInterrupt();
std::unique_ptr<Arduino_IIC> touch(new Arduino_FT3x68(
    touchBus, FT3168_DEVICE_ADDRESS, DRIVEBUS_DEFAULT_VALUE, TP_INT,
    touchInterrupt));

String wifiSsid;
String wifiPassword;
String coreUrl;
String wearableState = "SYSTEM_READY";
String serialLine;

bool displayReady = false;
bool pmuReady = false;
bool touchReady = false;
bool audioReady = false;
bool coreOnline = false;
bool httpStarted = false;
int batteryPercent = -1;
uint32_t lastPollMs = 0;
uint32_t lastWifiAttemptMs = 0;
uint32_t lastBatteryReadMs = 0;
uint32_t lastTouchMs = 0;

volatile SelfTestPhase selfTestPhase = SELFTEST_IDLE;
volatile bool selfTestRunning = false;
volatile bool uiDirty = true;
volatile uint32_t selfTestId = 0;
volatile uint32_t selfTestStartedMs = 0;
volatile uint32_t selfTestBytesExpected = 0;
volatile uint32_t selfTestBytesWritten = 0;
uint8_t requestedVolume = 70;
String requestedProfile = "speech";

void touchInterrupt() { touch->IIC_Interrupt_Flag = true; }

bool elapsed(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

void centeredText(const String &text, int16_t y, uint8_t size,
                  uint16_t color) {
  int16_t x1, y1;
  uint16_t width, height;
  gfx->setTextSize(size);
  gfx->getTextBounds(text.c_str(), 0, y, &x1, &y1, &width, &height);
  const int16_t centered = (LCD_WIDTH - static_cast<int16_t>(width)) / 2;
  gfx->setTextColor(color);
  gfx->setCursor(centered > 8 ? centered : 8, y);
  gfx->print(text);
}

void statusRow(int16_t y, const char *label, const String &value,
               uint16_t valueColor) {
  gfx->setTextSize(2);
  gfx->setTextColor(kMuted);
  gfx->setCursor(28, y);
  gfx->print(label);
  gfx->setTextColor(valueColor);
  gfx->setCursor(200, y);
  gfx->print(value);
}

String phaseLabel() {
  switch (selfTestPhase) {
    case SELFTEST_PRE_SILENCE: return "SILENCIO 2s";
    case SELFTEST_PLAYING: return "REPRODUZINDO";
    case SELFTEST_POST_SILENCE: return "SILENCIO FINAL";
    case SELFTEST_COMPLETE: return "TESTE ENVIADO";
    case SELFTEST_FAILED: return "FALHA AUDIO";
    default: return "";
  }
}

void renderUi() {
  if (!displayReady) return;
  uiDirty = false;
  const bool wifiOnline = WiFi.status() == WL_CONNECTED;
  const bool active = wearableState == "AUDIO_ACTIVE";
  const uint16_t accent = selfTestRunning ? kAmber : (active ? kRed : kGreen);
  gfx->fillScreen(kBlack);
  centeredText("SAFE-FIELD", 22, 4, kWhite);
  gfx->drawFastHLine(28, 70, LCD_WIDTH - 56, kBlue);
  statusRow(92, "WiFi", wifiOnline ? "ONLINE" : "CONNECTING",
            wifiOnline ? kGreen : kAmber);
  statusRow(120, "Raspberry", coreOnline ? "ONLINE" : "---",
            coreOnline ? kGreen : kMuted);
  statusRow(148, "FPGA", coreOnline ? "LINKED" : "---",
            coreOnline ? kGreen : kMuted);
  statusRow(176, "Speaker", audioReady ? "READY" : "FAIL",
            audioReady ? kGreen : kRed);

  gfx->fillRoundRect(20, 212, LCD_WIDTH - 40, 178, 20, kPanel);
  gfx->drawRoundRect(20, 212, LCD_WIDTH - 40, 178, 20, accent);
  if (selfTestRunning || selfTestPhase == SELFTEST_COMPLETE ||
      selfTestPhase == SELFTEST_FAILED) {
    centeredText("DIAGNOSTICO AUDIO", 246, 2, kWhite);
    centeredText(phaseLabel(), 292, 3, accent);
    centeredText("AUTONOMO", 344, 2, kMuted);
  } else {
    centeredText("MONITORANDO", 242, 3, kBlue);
    centeredText("VOZ", 295, 2, kMuted);
    centeredText(active ? "DETECTADA" : "NAO DETECTADA", 330, 3, accent);
  }

  gfx->fillRoundRect(28, 416, LCD_WIDTH - 56, 58, 14, kBlue);
  centeredText("DIAGNOSTICO: TESTAR AUDIO", 434, 1, kWhite);
  gfx->setTextSize(1);
  gfx->setTextColor(kMuted);
  gfx->setCursor(28, 486);
  gfx->printf("IP %s  BAT %s", wifiOnline ? WiFi.localIP().toString().c_str() : "---",
              batteryPercent >= 0 ? (String(batteryPercent) + "%").c_str() : "USB");
}

String jsonStringValue(const String &json, const char *key) {
  const String marker = String('"') + key + '"';
  int index = json.indexOf(marker);
  if (index < 0 || (index = json.indexOf(':', index + marker.length())) < 0 ||
      (index = json.indexOf('"', index + 1)) < 0) return "";
  const int end = json.indexOf('"', index + 1);
  return end < 0 ? "" : json.substring(index + 1, end);
}

bool knownState(const String &state) {
  return state == "SYSTEM_READY" || state == "OCCURRENCE_ACTIVE" ||
         state == "AUDIO_QUIET" || state == "AUDIO_ACTIVE" ||
         state == "ATTENTION" || state == "CAMERA_NOT_CONNECTED" ||
         state == "PHOTO_CAPTURED";
}

void writeSilence(uint32_t durationMs) {
  static int16_t zero[kPcmChunkFrames * 2] = {};
  uint32_t frames = durationMs * kSampleRate / 1000;
  while (frames) {
    const uint32_t count = frames > kPcmChunkFrames ? kPcmChunkFrames : frames;
    const size_t bytes = count * 4;
    selfTestBytesExpected += bytes;
    selfTestBytesWritten += i2s.write(reinterpret_cast<uint8_t *>(zero), bytes);
    frames -= count;
  }
}

void writeTone(float frequency, uint32_t durationMs, int16_t amplitude) {
  static int16_t pcm[kPcmChunkFrames * 2];
  const uint32_t total = durationMs * kSampleRate / 1000;
  uint32_t produced = 0;
  while (produced < total) {
    const uint32_t count = min<uint32_t>(kPcmChunkFrames, total - produced);
    for (uint32_t i = 0; i < count; ++i) {
      const float phase = 2.0f * PI * frequency * (produced + i) / kSampleRate;
      const int16_t sample = static_cast<int16_t>(sinf(phase) * amplitude);
      pcm[i * 2] = sample;
      pcm[i * 2 + 1] = sample;
    }
    const size_t bytes = count * 4;
    selfTestBytesExpected += bytes;
    selfTestBytesWritten += i2s.write(reinterpret_cast<uint8_t *>(pcm), bytes);
    produced += count;
  }
}

void writeSpeech() {
  uint32_t offset = 0;
  while (offset < kSafeFieldSpeechPcmLength) {
    const uint32_t count = min<uint32_t>(2048, kSafeFieldSpeechPcmLength - offset);
    selfTestBytesExpected += count;
    selfTestBytesWritten += i2s.write(kSafeFieldSpeechPcm + offset, count);
    offset += count;
  }
}

void selfTestTask(void *) {
  selfTestPhase = SELFTEST_PRE_SILENCE;
  uiDirty = true;
  writeSilence(2000);
  selfTestPhase = SELFTEST_PLAYING;
  uiDirty = true;
  if (requestedProfile == "tone") {
    writeTone(1000.0f, 4000, 15000);
  } else if (requestedProfile == "speechlike") {
    for (int i = 0; i < 8; ++i) {
      writeTone(350.0f + i * 75.0f, 350, 13000);
      writeSilence(100);
    }
  } else {
    writeSpeech();
  }
  selfTestPhase = SELFTEST_POST_SILENCE;
  uiDirty = true;
  writeSilence(2000);
  selfTestPhase = selfTestBytesWritten == selfTestBytesExpected ?
      SELFTEST_COMPLETE : SELFTEST_FAILED;
  selfTestRunning = false;
  uiDirty = true;
  USBSerial.printf("AUDIO_SELFTEST_COMPLETE id=%lu profile=%s volume=%u bytes=%lu/%lu ms=%lu\n",
                   static_cast<unsigned long>(selfTestId), requestedProfile.c_str(),
                   requestedVolume, static_cast<unsigned long>(selfTestBytesWritten),
                   static_cast<unsigned long>(selfTestBytesExpected),
                   static_cast<unsigned long>(millis()));
  vTaskDelete(nullptr);
}

bool audio_selftest_play(const String &profile, uint8_t volume) {
  if (!audioReady || selfTestRunning) return false;
  if (profile != "speech" && profile != "tone" && profile != "speechlike") return false;
  requestedProfile = profile;
  requestedVolume = constrain(volume, 10, 90);
  if (!codec || es8311_voice_volume_set(codec, requestedVolume, nullptr) != ESP_OK ||
      es8311_voice_mute(codec, false) != ESP_OK) return false;
  selfTestId++;
  selfTestStartedMs = millis();
  selfTestBytesExpected = 0;
  selfTestBytesWritten = 0;
  selfTestRunning = true;
  selfTestPhase = SELFTEST_PRE_SILENCE;
  uiDirty = true;
  return xTaskCreatePinnedToCore(selfTestTask, "audio_selftest", 4096, nullptr,
                                 2, nullptr, 0) == pdPASS;
}

void startHttpServer() {
  if (httpStarted) return;
  MDNS.begin("safe-field-watch");
  MDNS.addService("http", "tcp", 80);
  server.on("/api/v1/selftest/status", HTTP_GET, []() {
    const String body = String("{\"ok\":true,\"audio_ready\":") +
        (audioReady ? "true" : "false") + ",\"running\":" +
        (selfTestRunning ? "true" : "false") + ",\"id\":" + selfTestId +
        ",\"phase\":\"" + phaseLabel() + "\",\"profile\":\"" +
        requestedProfile + "\",\"volume\":" + requestedVolume +
        ",\"bytes_written\":" + selfTestBytesWritten +
        ",\"bytes_expected\":" + selfTestBytesExpected +
        ",\"ip\":\"" + WiFi.localIP().toString() + "\"}";
    server.send(200, "application/json", body);
  });
  server.on("/api/v1/selftest/play", HTTP_POST, []() {
    const String profile = server.hasArg("profile") ? server.arg("profile") : "speech";
    const uint8_t volume = server.hasArg("volume") ? server.arg("volume").toInt() : 70;
    const bool started = audio_selftest_play(profile, volume);
    server.send(started ? 202 : 409, "application/json",
                String("{\"ok\":") + (started ? "true" : "false") +
                ",\"id\":" + selfTestId + "}");
  });
  server.onNotFound([]() { server.send(404, "application/json", "{\"ok\":false}"); });
  server.begin();
  httpStarted = true;
  USBSerial.printf("SELFTEST_HTTP_READY http://%s/api/v1/selftest/status\n",
                   WiFi.localIP().toString().c_str());
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
  uiDirty = true;
}

void pollCore() {
  if (WiFi.status() != WL_CONNECTED || !coreUrl.length()) return;
  HTTPClient http;
  http.setConnectTimeout(kHttpTimeoutMs);
  http.setTimeout(kHttpTimeoutMs);
  if (!http.begin(coreUrl)) return;
  const int status = http.GET();
  if (status == HTTP_CODE_OK) {
    const String next = jsonStringValue(http.getString(), "wearable_state");
    coreOnline = true;
    if (knownState(next) && next != wearableState) {
      wearableState = next;
      uiDirty = true;
    }
  } else if (coreOnline) {
    coreOnline = false;
    uiDirty = true;
  }
  http.end();
}

void serviceTouch() {
  if (!touchReady || !touch->IIC_Interrupt_Flag || millis() - lastTouchMs < 500) return;
  touch->IIC_Interrupt_Flag = false;
  lastTouchMs = millis();
  const int32_t y = touch->IIC_Read_Device_Value(
      touch->Arduino_IIC_Touch::Value_Information::TOUCH_COORDINATE_Y);
  if (y >= 400) audio_selftest_play("speech", 70);
}

void handleSerialLine(const String &raw) {
  String line = raw;
  line.trim();
  if (line == "AUDIO_TEST") {
    USBSerial.println(audio_selftest_play("speech", 70) ? "OK AUDIO_TEST" : "ERR AUDIO_TEST");
  } else if (line == "SHOW_CONFIG") {
    USBSerial.printf("CONFIG ssid=%s password=REDACTED core=%s ip=%s\n",
                     wifiSsid.c_str(), coreUrl.c_str(), WiFi.localIP().toString().c_str());
  }
}

void serviceSerial() {
  while (USBSerial.available()) {
    const char c = USBSerial.read();
    if (c == '\n') {
      handleSerialLine(serialLine);
      serialLine = "";
    } else if (c != '\r' && serialLine.length() < 128) serialLine += c;
  }
}

}  // namespace

void setup() {
  USBSerial.begin(kSerialBaud);
  delay(250);
  USBSerial.println("SAFE_FIELD_AUDIO_AUTOTEST_BOOT version=1");

  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);
  displayReady = gfx->begin();
  if (displayReady) gfx->fillScreen(kBlack);

  Wire.begin(IIC_SDA, IIC_SCL);
  pmuReady = power.begin(Wire, AXP2101_SLAVE_ADDRESS, IIC_SDA, IIC_SCL);
  if (pmuReady) {
    power.enableBattDetection();
    power.enableBattVoltageMeasure();
  }
  touchReady = touch->begin();

  pinMode(AUDIO_PA_ENABLE, OUTPUT);
  digitalWrite(AUDIO_PA_ENABLE, HIGH);
  i2s.setPins(AUDIO_MCLK, AUDIO_BCLK, AUDIO_LRCK, AUDIO_DOUT, AUDIO_DIN);
  const bool i2sReady = i2s.begin(I2S_MODE_STD, kSampleRate, I2S_DATA_BIT_WIDTH_16BIT,
                                  I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);
  codec = es8311_create(0, ES8311_ADDRESS_0);
  const es8311_clock_config_t codecClock = {
      .mclk_inverted = false,
      .sclk_inverted = false,
      .mclk_from_mclk_pin = true,
      .mclk_frequency = static_cast<int>(kSampleRate * 256),
      .sample_frequency = static_cast<int>(kSampleRate),
  };
  audioReady = i2sReady && codec &&
      es8311_init(codec, &codecClock, ES8311_RESOLUTION_16, ES8311_RESOLUTION_16) == ESP_OK &&
      es8311_microphone_config(codec, false) == ESP_OK &&
      es8311_voice_volume_set(codec, 70, nullptr) == ESP_OK &&
      es8311_voice_mute(codec, false) == ESP_OK;
  USBSerial.printf("%s ES8311_PLAYBACK pins=%d/%d/%d/%d/%d pa=%d\n",
                   audioReady ? "PASS" : "FAIL", AUDIO_MCLK, AUDIO_BCLK,
                   AUDIO_LRCK, AUDIO_DOUT, AUDIO_DIN, AUDIO_PA_ENABLE);

  preferences.begin("safe-field", false);
  loadConfiguration();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  connectWifi();
  renderUi();
}

void loop() {
  const uint32_t now = millis();
  serviceSerial();
  serviceTouch();
  server.handleClient();

  if (WiFi.status() == WL_CONNECTED) startHttpServer();
  else if (wifiSsid.length() && elapsed(now, lastWifiAttemptMs + kWifiRetryMs)) connectWifi();

  if (elapsed(now, lastPollMs + kPollPeriodMs)) {
    lastPollMs = now;
    pollCore();
  }
  if (pmuReady && elapsed(now, lastBatteryReadMs + 10000)) {
    lastBatteryReadMs = now;
    batteryPercent = power.isBatteryConnect() ? power.getBatteryPercent() : -1;
    uiDirty = true;
  }
  if (uiDirty) renderUi();
  delay(5);
}
