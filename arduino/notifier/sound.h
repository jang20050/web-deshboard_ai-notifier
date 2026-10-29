// sound.h — 수동 부저 멜로디 (멈추지 않고 loop 안에서 진행)
#pragma once
#include <Arduino.h>

namespace Sound {
  enum Pattern : uint8_t { DONE_CHIME, INPUT_DINGDONG, ERROR_LOW };
  void begin();
  void play(Pattern p);   // 패턴 시작 (정해진 횟수만 반복)
  void stop();            // 즉시 정지
  void update();          // loop()에서 계속 호출
  bool active();          // 지금 소리를 내는 중인지 (반복 사이 쉬는 시간 포함)
}
