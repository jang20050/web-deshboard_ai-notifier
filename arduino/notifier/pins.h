// pins.h — 핀 번호와 하드웨어 설정 (실제 배선 기준)
#pragma once
#include <Arduino.h>

// LCD1602 I2C 모듈: 하드웨어 I2C 핀(A4/A5)이 아니므로 소프트웨어 I2C로 구동
const uint8_t PIN_LCD_SDA = A0;
const uint8_t PIN_LCD_SCL = A1;

// RGB LED (채널마다 220Ω)
const uint8_t PIN_RED   = 9;   // Timer1 PWM
const uint8_t PIN_GREEN = 10;  // Timer1 PWM
const uint8_t PIN_BLUE  = 11;  // Timer2 PWM — tone()과 같은 타이머! light.cpp에서 처리

// 공통 +(애노드) RGB면 true, 공통 −(캐소드)면 false
const bool RGB_COMMON_ANODE = false;

// 수동 부저
const uint8_t PIN_BUZZER = 7;

// 확인 버튼: D2 ↔ GND, INPUT_PULLUP (누르면 LOW)
const uint8_t PIN_BUTTON = 2;

const unsigned long SERIAL_BAUD = 115200;
