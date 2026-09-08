#pragma once

#define XPOWERS_CHIP_AXP2101

#define LCD_SDIO0 4
#define LCD_SDIO1 5
#define LCD_SDIO2 6
#define LCD_SDIO3 7
#define LCD_SCLK 11
#define LCD_CS 12
#define LCD_RESET 8
#define LCD_WIDTH 410
#define LCD_HEIGHT 502

#define IIC_SDA 15
#define IIC_SCL 14
#define TP_INT 38
#define TP_RESET 9

#define MOTOR_PIN 18

// First-party Waveshare BSP v2.0.0 pinout. ES7210 is the microphone ADC;
// ES8311 is the playback codec. Keep these semantic names in setPins order.
#define AUDIO_MCLK 16
#define AUDIO_BCLK 41
#define AUDIO_LRCK 45
#define AUDIO_DOUT 40
#define AUDIO_DIN 42
#define AUDIO_PA_ENABLE 46
#define ES8311_I2C_ADDRESS 0x18
#define ES7210_I2C_ADDRESS 0x40  // 7-bit form of the vendor driver's 0x80.
