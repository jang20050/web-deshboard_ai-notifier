// light.h — RGB LED 색·숨쉬기·깜빡임
#pragma once
#include <Arduino.h>
#include "state.h"

namespace Light {
  void begin();
  // 상태가 바뀔 때 호출 (깜빡임 타이머 초기화)
  void setState(State s, uint8_t pct, State seenFrom);
  void setProgress(uint8_t pct);
  // loop()에서 계속 호출. soundActive=true면 파란색을 켜짐/꺼짐으로만 출력(Timer2 충돌 방지)
  void update(bool soundActive);
}
