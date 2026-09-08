#include <Arduino.h>
#include <Arduino_DriveBus_Library.h>
#include <Arduino_GFX_Library.h>
#include <ESP_I2S.h>
#include <HWCDC.h>
#include <Wire.h>
#include <math.h>

#include "pin_config.h"
#include <XPowersLib.h>

namespace {

constexpr uint32_t kSampleRate = 16000;
constexpr uint32_t kCaptureSeconds = 8;
constexpr size_t kFrameBytes = 4;  // stereo signed PCM16
constexpr size_t kChunkBytes = 4096;

HWCDC USBSerial;
I2SClass i2s;
XPowersPMU power;

Arduino_DataBus *bus = new Arduino_ESP32QSPI(
    LCD_CS, LCD_SCLK, LCD_SDIO0, LCD_SDIO1, LCD_SDIO2, LCD_SDIO3);
Arduino_GFX *gfx = new Arduino_CO5300(bus, LCD_RESET, 0, LCD_WIDTH, LCD_HEIGHT,
                                      22, 0, 0, 0);
bool displayReady = false;
bool audioReady = false;
String commandLine;

bool es7210Write(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(ES7210_I2C_ADDRESS);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool es7210Read(uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(ES7210_I2C_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ES7210_I2C_ADDRESS, 1) != 1) return false;
  value = Wire.read();
  return true;
}

bool es7210Update(uint8_t reg, uint8_t mask, uint8_t value) {
  uint8_t current = 0;
  return es7210Read(reg, current) &&
         es7210Write(reg, (current & ~mask) | (value & mask));
}

// Minimal capture-only sequence mirrored from Espressif esp_codec_dev ES7210.
// ESP32 is I2S master; ES7210 is slave, 16-bit Philips I2S, MIC1+MIC2.
bool initEs7210() {
  bool ok = true;
  ok &= es7210Write(0x00, 0xff);
  ok &= es7210Write(0x00, 0x41);
  ok &= es7210Write(0x01, 0x3f);
  ok &= es7210Write(0x09, 0x30);
  ok &= es7210Write(0x0a, 0x30);
  ok &= es7210Write(0x23, 0x2a);
  ok &= es7210Write(0x22, 0x0a);
  ok &= es7210Write(0x20, 0x0a);
  ok &= es7210Write(0x21, 0x2a);
  ok &= es7210Update(0x08, 0x01, 0x00);  // slave mode
  ok &= es7210Write(0x40, 0x43);
  ok &= es7210Write(0x41, 0x70);
  ok &= es7210Write(0x42, 0x70);
  ok &= es7210Write(0x07, 0x20);
  ok &= es7210Write(0x02, 0xc1);

  // Select and power MIC1/MIC2, then use the driver's 30 dB PGA value.
  ok &= es7210Write(0x4b, 0xff);
  ok &= es7210Write(0x4c, 0xff);
  ok &= es7210Update(0x01, 0x0b, 0x00);
  ok &= es7210Write(0x4b, 0x00);
  ok &= es7210Update(0x43, 0x10, 0x10);
  ok &= es7210Update(0x44, 0x10, 0x10);
  ok &= es7210Update(0x43, 0x0f, 0x0a);
  ok &= es7210Update(0x44, 0x0f, 0x0a);

  ok &= es7210Update(0x11, 0xe3, 0x60);  // 16-bit, Philips I2S
  ok &= es7210Write(0x12, 0x02);
  ok &= es7210Write(0x01, 0x34);
  ok &= es7210Write(0x06, 0x00);
  ok &= es7210Write(0x40, 0x43);
  ok &= es7210Write(0x47, 0x08);
  ok &= es7210Write(0x48, 0x08);
  ok &= es7210Write(0x49, 0x08);
  ok &= es7210Write(0x4a, 0x08);
  ok &= es7210Write(0x4b, 0x00);
  ok &= es7210Write(0x4c, 0xff);
  ok &= es7210Update(0x15, 0x03, 0x00);  // unmute ADC1/2
  ok &= es7210Write(0x00, 0x71);
  ok &= es7210Write(0x00, 0x41);

  uint8_t reg00 = 0, reg01 = 0, reg11 = 0;
  const bool readback = es7210Read(0x00, reg00) && es7210Read(0x01, reg01) &&
                        es7210Read(0x11, reg11);
  USBSerial.printf("ES7210 init=%s addr=0x%02X reg00=0x%02X reg01=0x%02X reg11=0x%02X\n",
                   (ok && readback) ? "PASS" : "FAIL", ES7210_I2C_ADDRESS,
                   reg00, reg01, reg11);
  return ok && readback;
}

void centered(const char *text, int16_t y, uint8_t size, uint16_t color) {
  if (!displayReady) return;
  int16_t x1, y1;
  uint16_t width, height;
  gfx->setTextSize(size);
  gfx->getTextBounds(text, 0, y, &x1, &y1, &width, &height);
  gfx->setTextColor(color);
  gfx->setCursor(max<int16_t>(8, (LCD_WIDTH - width) / 2), y);
  gfx->print(text);
}

void show(const char *line1, const char *line2, uint16_t color) {
  if (!displayReady) return;
  gfx->fillScreen(0x0000);
  centered("SAFE-FIELD", 35, 4, 0xFFFF);
  gfx->drawFastHLine(30, 90, LCD_WIDTH - 60, 0x05FF);
  centered(line1, 190, 3, color);
  centered(line2, 255, 3, color);
}

void pulseMotor(uint32_t milliseconds) {
  digitalWrite(MOTOR_PIN, HIGH);
  delay(milliseconds);
  digitalWrite(MOTOR_PIN, LOW);
}

bool captureAndSend() {
  const size_t totalBytes = kSampleRate * kCaptureSeconds * kFrameBytes;
  uint8_t *pcm = static_cast<uint8_t *>(ps_malloc(totalBytes));
  if (!pcm) {
    USBSerial.println("ERR PSRAM_ALLOC");
    show("ERRO", "PSRAM", 0xF800);
    return false;
  }

  // Discard stale DMA contents before the visible countdown.
  uint8_t discard[kChunkBytes];
  i2s.readBytes(reinterpret_cast<char *>(discard), sizeof(discard));
  for (int count = 3; count > 0; --count) {
    char value[12];
    snprintf(value, sizeof(value), "%d", count);
    show("CAPTURA EM", value, 0xFD20);
    delay(1000);
  }

  show("FALE AGORA", "8 SEGUNDOS", 0xF800);
  pulseMotor(120);
  const uint32_t started = millis();
  size_t received = 0;
  while (received < totalBytes) {
    const size_t wanted = min(kChunkBytes, totalBytes - received);
    const size_t got = i2s.readBytes(reinterpret_cast<char *>(pcm + received), wanted);
    if (!got) break;
    received += got;
  }
  const uint32_t elapsedMs = millis() - started;
  pulseMotor(120);
  show("CAPTURA", received == totalBytes ? "CONCLUIDA" : "INCOMPLETA",
       received == totalBytes ? 0x07E0 : 0xF800);

  const int16_t *samples = reinterpret_cast<const int16_t *>(pcm);
  const size_t frames = received / kFrameBytes;
  long double sumLeft = 0.0L, sumRight = 0.0L;
  long double squareLeft = 0.0L, squareRight = 0.0L;
  for (size_t i = 0; i < frames; ++i) {
    const long double left = samples[2 * i];
    const long double right = samples[2 * i + 1];
    sumLeft += left;
    sumRight += right;
    squareLeft += left * left;
    squareRight += right * right;
  }
  const double meanLeft = frames ? static_cast<double>(sumLeft / frames) : 0.0;
  const double meanRight = frames ? static_cast<double>(sumRight / frames) : 0.0;
  const double rmsLeft = frames ? sqrt(static_cast<double>(squareLeft / frames) - meanLeft * meanLeft) : 0.0;
  const double rmsRight = frames ? sqrt(static_cast<double>(squareRight / frames) - meanRight * meanRight) : 0.0;

  USBSerial.printf("PCM_BEGIN %lu 2 %lu %lu %.3f %.3f\n",
                   static_cast<unsigned long>(kSampleRate),
                   static_cast<unsigned long>(received),
                   static_cast<unsigned long>(elapsedMs), rmsLeft, rmsRight);
  size_t sent = 0;
  while (sent < received) {
    const size_t count = min(kChunkBytes, received - sent);
    sent += USBSerial.write(pcm + sent, count);
    delay(1);
  }
  USBSerial.println();
  USBSerial.printf("PCM_END %lu\n", static_cast<unsigned long>(sent));
  USBSerial.flush();
  free(pcm);
  return received == totalBytes && sent == received;
}

void processCommand(const String &raw) {
  String command = raw;
  command.trim();
  if (command == "CAPTURE") {
    if (!audioReady) USBSerial.println("ERR AUDIO_NOT_READY");
    else captureAndSend();
  } else if (command == "STATUS") {
    USBSerial.printf("STATUS audio=%s psram=%u\n", audioReady ? "READY" : "FAIL",
                     static_cast<unsigned>(ESP.getPsramSize()));
  }
}

}  // namespace

void setup() {
  USBSerial.begin(921600);
  delay(300);
  displayReady = gfx->begin();
  show("MIC TEST", "INICIANDO", 0xFD20);

  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);
  pinMode(AUDIO_PA_ENABLE, OUTPUT);
  digitalWrite(AUDIO_PA_ENABLE, LOW);  // Capture only: no acoustic feedback.

  Wire.begin(IIC_SDA, IIC_SCL);
  const bool pmuReady = power.begin(Wire, AXP2101_SLAVE_ADDRESS,
                                    IIC_SDA, IIC_SCL);
  if (pmuReady) {
    power.setBLDO2Voltage(3300);
    power.enableBLDO2();  // Official board comment: MIC VDD 3.3 V.
    delay(100);
  }

  i2s.setPins(AUDIO_BCLK, AUDIO_LRCK, AUDIO_DOUT, AUDIO_DIN, AUDIO_MCLK);
  const bool i2sReady = i2s.begin(I2S_MODE_STD, kSampleRate,
      I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);
  delay(100);  // ES7210 requires stable MCLK before its control sequence.
  const bool codecReady = i2sReady && initEs7210();
  audioReady = pmuReady && i2sReady && codecReady;

  USBSerial.printf("WATCH_MIC_BOOT audio=%s pmu=%s codec=ES7210 rate=%lu pins=%d/%d/%d/%d/%d psram=%u\n",
                   audioReady ? "READY" : "FAIL",
                   pmuReady ? "READY" : "FAIL",
                   static_cast<unsigned long>(kSampleRate), AUDIO_MCLK,
                   AUDIO_BCLK, AUDIO_LRCK, AUDIO_DOUT, AUDIO_DIN,
                   static_cast<unsigned>(ESP.getPsramSize()));
  show("MIC TEST", audioReady ? "PRONTO" : "FALHOU",
       audioReady ? 0x07E0 : 0xF800);
}

void loop() {
  while (USBSerial.available()) {
    const char value = USBSerial.read();
    if (value == '\n') {
      processCommand(commandLine);
      commandLine = "";
    } else if (value != '\r' && commandLine.length() < 64) {
      commandLine += value;
    }
  }
  delay(2);
}
