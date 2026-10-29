// light.cpp
#include "light.h"
#include "pins.h"

namespace {
  State state = ST_IDLE;
  State seenFrom = ST_DONE;
  uint8_t progressPct = 0;
  unsigned long stateSince = 0;

  const float MAX_BRIGHT = 0.7f;   // 눈부심 방지

  void out(uint8_t r, uint8_t g, uint8_t b, bool soundActive) {
    r = (uint8_t)(r * MAX_BRIGHT);
    g = (uint8_t)(g * MAX_BRIGHT);
    b = (uint8_t)(b * MAX_BRIGHT);
    // D11(파랑)은 tone()과 같은 Timer2를 씁니다. 소리가 나는 동안 analogWrite(11, 1~254)를 하면
    // 부저 음높이가 깨지므로, 이때는 파란색을 0 또는 255(=digitalWrite)로만 출력합니다.
    // 소리가 나는 상태(답변 대기·완료·오류)의 색은 파란색이 0이라 눈에 보이는 차이는 없습니다.
    if (soundActive) b = (b >= 128) ? 255 : 0;
    if (RGB_COMMON_ANODE) { r = 255 - r; g = 255 - g; b = 255 - b; }
    analogWrite(PIN_RED, r);
    analogWrite(PIN_GREEN, g);
    analogWrite(PIN_BLUE, b);
  }

  // 진행도 0→50→100 : 파랑 → 청록 → 초록
  void workColor(uint8_t pct, uint8_t& r, uint8_t& g, uint8_t& b) {
    r = 0;
    if (pct <= 50) { g = (uint16_t)pct * 255 / 50; b = 255; }
    else           { g = 255; b = (uint16_t)(100 - pct) * 255 / 50; }
  }

  void alertColor(State s, uint8_t& r, uint8_t& g, uint8_t& b) {
    switch (s) {
      case ST_INPUT: r = 255; g = 90;  b = 0; break;   // 주황
      case ST_DONE:  r = 0;   g = 255; b = 0; break;   // 초록
      case ST_ERROR: r = 255; g = 0;   b = 0; break;   // 빨강
      default:       r = 255; g = 255; b = 255; break;
    }
  }
}

namespace Light {

void begin() {
  pinMode(PIN_RED, OUTPUT); pinMode(PIN_GREEN, OUTPUT); pinMode(PIN_BLUE, OUTPUT);
  out(0, 0, 0, false);
}

void setState(State s, uint8_t pct, State from) {
  state = s; progressPct = pct; seenFrom = from;
  stateSince = millis();
}

void setProgress(uint8_t pct) { progressPct = pct; }

void update(bool soundActive) {
  unsigned long t = millis() - stateSince;
  uint8_t r = 0, g = 0, b = 0;

  switch (state) {
    case ST_IDLE:
      r = g = b = 35;                                  // 흰색 아주 약하게
      break;

    case ST_WORK: {                                    // 2.5초 주기 숨쉬기 (밝기 25%~100%)
      workColor(progressPct, r, g, b);
      float phase = (millis() % 2500) / 2500.0f;
      float level = 0.25f + 0.75f * (0.5f - 0.5f * cos(2 * PI * phase));
      r *= level; g *= level; b *= level;
      break;
    }

    case ST_INPUT:                                     // 주황 깜빡임 2.5Hz (WCAG 2.3.1: 초당 3회 미만)
      alertColor(ST_INPUT, r, g, b);
      if ((t / 200) % 2) r = g = b = 0;
      break;

    case ST_DONE:                                      // 초록 계속 켜짐
      alertColor(ST_DONE, r, g, b);
      break;

    case ST_ERROR:                                     // 빨강 2번 깜빡인 뒤 계속 켜짐
      alertColor(ST_ERROR, r, g, b);
      if (t < 800 && (t / 200) % 2) r = g = b = 0;
      break;

    case ST_SEEN:                                      // 확인됨: 직전 알림 색을 깜빡임 없이 약하게
      alertColor(seenFrom, r, g, b);
      r /= 3; g /= 3; b /= 3;
      break;
  }
  out(r, g, b, soundActive);
}

}  // namespace Light
