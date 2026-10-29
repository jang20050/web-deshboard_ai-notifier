// notifier.ino — AI 작업 알림 장치 (Arduino UNO)
//
// UNO는 표시만 합니다. 무엇을 보여줄지는 PC(bridge)가 시리얼로 보냅니다.
// 시리얼 115200, 한 줄 = 명령 하나 (줄 끝 \n)
//
//   PC → UNO
//     S,<상태>,<진행도>,<문구>   예) S,WORK,55,BUILDING   S,DONE,100,TOOK 12M
//                                 상태: IDLE WORK INPUT DONE ERROR SEEN
//     ACK                        사용자 확인(제스처 등) → 부저 정지, SEEN
//     PING                       연결 확인
//   UNO → PC
//     READY / LCD,0x27 또는 ERR,LCD_NOT_FOUND   부팅 시
//     OK  PONG  ERR,<이유>  BTN
//
// 시리얼 모니터로 직접 시험할 때는 오른쪽 아래 줄 끝 설정을 "새 줄(Newline)", 속도를 115200으로.

#include "pins.h"
#include "state.h"
#include "display.h"
#include "light.h"
#include "sound.h"

// ---------- 현재 상태 ----------
State state = ST_IDLE;
State seenFrom = ST_DONE;          // SEEN이 어떤 알림을 확인한 것인지
uint8_t pct = 0;
char text[17] = "";
unsigned long stateSince = 0;
bool screenDirty = true;
unsigned long lastClockDraw = 0;

// ---------- 시리얼 입력 ----------
char rx[64];
uint8_t rxLen = 0;

// ---------- 버튼 ----------
bool btnStable = HIGH, btnLast = HIGH;
unsigned long btnChangedAt = 0;
const unsigned long DEBOUNCE_MS = 30;

// =====================================================================

void enterState(State s, uint8_t p, const char* t) {
  if (s == ST_SEEN && isAlert(state)) seenFrom = state;
  state = s;
  pct = p > 100 ? 100 : p;
  strncpy(text, t ? t : "", 16); text[16] = 0;
  stateSince = millis();
  screenDirty = true;

  Sound::stop();
  if (s == ST_DONE)  Sound::play(Sound::DONE_CHIME);
  if (s == ST_INPUT) Sound::play(Sound::INPUT_DINGDONG);
  if (s == ST_ERROR) Sound::play(Sound::ERROR_LOW);

  Light::setState(s, pct, seenFrom);
}

// 알림 상태에서만 의미 있음. 확인되면 true
bool acknowledge() {
  if (!isAlert(state)) return false;
  enterState(ST_SEEN, pct, text);
  return true;
}

// ---------- LCD ----------
void drawScreen() {
  char l0[17], l1[17];
  unsigned long sec = (millis() - stateSince) / 1000;

  switch (state) {
    case ST_IDLE:
      Display::line(0, "READY");
      Display::line(1, text);
      break;
    case ST_WORK:
      Display::line(0, text[0] ? text : "WORKING");
      Display::progress(1, pct);
      break;
    case ST_INPUT:
      Display::line(0, "NEED YOUR INPUT");
      snprintf(l1, sizeof l1, "WAITING %02lu:%02lu", (sec / 60) % 100, sec % 60);
      Display::line(1, l1);
      break;
    case ST_DONE:
      Display::line(0, "DONE!");
      Display::line(1, text[0] ? text : "BTN/GESTURE=OK");
      break;
    case ST_ERROR:
      Display::line(0, "ERROR");
      Display::line(1, text);
      break;
    case ST_SEEN:
      snprintf(l0, sizeof l0, "SEEN - %s", stateName(seenFrom));
      Display::line(0, l0);
      Display::line(1, text);
      break;
  }
  screenDirty = false;
}

// ---------- 명령 처리 ----------
void handleLine(char* line) {
  // 줄 끝 \r 제거 (Windows 줄바꿈 대비)
  size_t n = strlen(line);
  while (n && (line[n - 1] == '\r' || line[n - 1] == ' ')) line[--n] = 0;
  if (!n) return;

  if (!strcmp(line, "PING")) { Serial.println(F("PONG")); return; }
  if (!strcmp(line, "ACK"))  { acknowledge(); Serial.println(F("OK")); return; }

  if (line[0] == 'S' && line[1] == ',') {
    // S,<상태>,<진행도>,<문구>  (문구는 쉼표 포함 가능 → 3번째 쉼표 뒤 전부)
    char* p = line + 2;
    char* c1 = strchr(p, ',');
    if (!c1) { Serial.println(F("ERR,FORMAT")); return; }
    *c1 = 0;
    char* pctStr = c1 + 1;
    char* c2 = strchr(pctStr, ',');
    const char* msg = "";
    if (c2) { *c2 = 0; msg = c2 + 1; }

    State s;
    if (!parseState(p, s)) { Serial.println(F("ERR,STATE")); return; }
    int v = atoi(pctStr);
    if (v < 0) v = 0;

    if (s == state && s == ST_WORK) {        // 작업 중 진행도만 바뀌면 불빛 타이머는 유지
      pct = v > 100 ? 100 : v;
      strncpy(text, msg, 16); text[16] = 0;
      Light::setProgress(pct);
      screenDirty = true;
    } else {
      enterState(s, (uint8_t)v, msg);
    }
    Serial.println(F("OK"));
    return;
  }
  Serial.println(F("ERR,UNKNOWN"));
}

void readSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      rx[rxLen] = 0;
      handleLine(rx);
      rxLen = 0;
    } else if (rxLen < sizeof(rx) - 1) {
      rx[rxLen++] = c;
    } else {
      rxLen = 0;                              // 너무 긴 줄은 버림
      Serial.println(F("ERR,TOO_LONG"));
    }
  }
}

// ---------- 버튼 ----------
void readButton() {
  bool now = digitalRead(PIN_BUTTON);
  if (now != btnLast) { btnLast = now; btnChangedAt = millis(); }
  if (millis() - btnChangedAt > DEBOUNCE_MS && now != btnStable) {
    btnStable = now;
    if (btnStable == LOW) {                   // 눌린 순간 한 번
      acknowledge();                          // PC 연결과 상관없이 부저를 바로 끔
      Serial.println(F("BTN"));
    }
  }
}

// =====================================================================

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  Sound::begin();
  Light::begin();

  uint8_t a = Display::begin();
  if (a) { Serial.print(F("LCD,0x")); Serial.println(a, HEX); }
  else   { Serial.println(F("ERR,LCD_NOT_FOUND")); }

  enterState(ST_IDLE, 0, "");
  Serial.println(F("READY"));
}

void loop() {
  readSerial();
  readButton();
  Sound::update();
  Light::update(Sound::active());

  // 답변 대기 중에는 경과 시간을 1초마다 갱신
  if (state == ST_INPUT && millis() - lastClockDraw >= 1000) {
    lastClockDraw = millis();
    screenDirty = true;
  }
  if (screenDirty) drawScreen();
}
