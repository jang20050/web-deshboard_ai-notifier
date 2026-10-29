// display.h — LCD1602 (PCF8574 I2C 백팩)를 소프트웨어 I2C로 구동
#pragma once
#include <Arduino.h>

namespace Display {
  // LCD를 찾아 초기화. 찾은 주소(예: 0x27)를 돌려주고, 못 찾으면 0
  uint8_t begin();
  bool ok();
  // 한 줄(0 또는 1)을 16자로 맞춰 출력. 바뀐 글자만 다시 씀
  void line(uint8_t row, const char* text);
  // 2번째 줄에 진행 막대 + 퍼센트 (예: ██████------ 52%)
  void progress(uint8_t row, uint8_t pct);
}
