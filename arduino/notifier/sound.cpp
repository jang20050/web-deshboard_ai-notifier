// sound.cpp
#include "sound.h"
#include "pins.h"

namespace {
  struct Note { uint16_t freq; uint16_t ms; };   // freq 0 = 쉼표

  // 완료: 도-미-솔 상승 3음 (여유 있는 느낌)
  const Note DONE_NOTES[]  = {{523, 150}, {659, 150}, {784, 350}};
  // 답변 대기: 띵-동 (높은음 → 낮은음, 더 급한 느낌)
  const Note INPUT_NOTES[] = {{880, 180}, {0, 60}, {659, 300}};
  // 오류: 낮은 단음
  const Note ERROR_NOTES[] = {{220, 600}};

  const uint8_t REPEATS_ALERT = 10;    // 완료·답변 대기: 10회 후 소리 끄기 (불빛은 유지)
  const uint16_t GAP_DONE_MS  = 1500;
  const uint16_t GAP_INPUT_MS = 900;

  const Note* notes = nullptr;
  uint8_t count = 0, idx = 0, repeatsLeft = 0;
  uint16_t gapMs = 0;
  unsigned long nextAt = 0;
  bool playing = false;
  bool resting = false;   // 반복 사이 쉬는 중

  void startNote() {
    if (notes[idx].freq) tone(PIN_BUZZER, notes[idx].freq);
    else noTone(PIN_BUZZER);
    nextAt = millis() + notes[idx].ms;
  }
}

namespace Sound {

void begin() { pinMode(PIN_BUZZER, OUTPUT); digitalWrite(PIN_BUZZER, LOW); }

void play(Pattern p) {
  switch (p) {
    case DONE_CHIME:     notes = DONE_NOTES;  count = 3; repeatsLeft = REPEATS_ALERT; gapMs = GAP_DONE_MS;  break;
    case INPUT_DINGDONG: notes = INPUT_NOTES; count = 3; repeatsLeft = REPEATS_ALERT; gapMs = GAP_INPUT_MS; break;
    case ERROR_LOW:      notes = ERROR_NOTES; count = 1; repeatsLeft = 1;             gapMs = 0;            break;
  }
  idx = 0;
  playing = true;
  resting = false;
  startNote();
}

void stop() {
  playing = false;
  noTone(PIN_BUZZER);   // Timer2를 PWM 모드로 되돌림 → 파란색 PWM 다시 사용 가능
}

void update() {
  if (!playing || (long)(millis() - nextAt) < 0) return;

  if (resting) {                       // 반복 사이 쉬는 시간이 끝남 → 처음 음부터
    resting = false;
    idx = 0;
    startNote();
    return;
  }

  idx++;
  if (idx < count) { startNote(); return; }

  // 한 번 재생 끝
  noTone(PIN_BUZZER);
  repeatsLeft--;
  if (repeatsLeft == 0) { playing = false; return; }
  resting = true;
  nextAt = millis() + gapMs;
}

bool active() { return playing; }

}  // namespace Sound
