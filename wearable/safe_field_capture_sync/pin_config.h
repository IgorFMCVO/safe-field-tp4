#pragma once

// Waveshare ESP32-S3-Touch-AMOLED-2.06, schematic/example pinout V1.0.
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

// Confirmed by the official schematic: net MOTOR is driven by GPIO18.
#define MOTOR_PIN 18
