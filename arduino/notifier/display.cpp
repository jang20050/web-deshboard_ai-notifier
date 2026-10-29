// display.cpp — 소프트웨어 I2C + HD44780(4비트) 드라이버
// 라이브러리 설치가 필요 없도록 직접 구현했습니다.
// I2C 신호는 "오픈 드레인" 방식: LOW는 직접 끌어내리고, HIGH는 손을 떼서 풀업이 올리게 합니다.
#include "display.h"
#include "pins.h"

namespace {
  // PCF8574 비트 배치 (대부분의 LCD1602 I2C 백팩 공통)
  const uint8_t BIT_RS = 0x01;
  const uint8_t BIT_EN = 0x04;
  const uint8_t BIT_BL = 0x08;   // 백라이트

  uint8_t addr = 0;
  char cache[2][17];             // 지금 화면에 있는 글자 (바뀐 글자만 다시 쓰기 위해)

  // ---- 소프트웨어 I2C ----
  inline void sdaLow()     { digitalWrite(PIN_LCD_SDA, LOW); pinMode(PIN_LCD_SDA, OUTPUT); }
  inline void sdaRelease() { pinMode(PIN_LCD_SDA, INPUT_PULLUP); }
  inline void sclLow()     { digitalWrite(PIN_LCD_SCL, LOW); pinMode(PIN_LCD_SCL, OUTPUT); }
  inline void sclRelease() { pinMode(PIN_LCD_SCL, INPUT_PULLUP); }
  inline void wait()       { delayMicroseconds(4); }

  void i2cStart() { sdaRelease(); sclRelease(); wait(); sdaLow(); wait(); sclLow(); }
  void i2cStop()  { sdaLow(); wait(); sclRelease(); wait(); sdaRelease(); wait(); }

  // 1바이트 보내고 ACK(받는 쪽이 SDA를 LOW로) 여부를 돌려줌
  bool i2cWrite(uint8_t b) {
    for (uint8_t i = 0; i < 8; i++) {
      if (b & 0x80) sdaRelease(); else sdaLow();
      b <<= 1;
      wait(); sclRelease(); wait(); sclLow();
    }
    sdaRelease(); wait(); sclRelease(); wait();
    bool ack = digitalRead(PIN_LCD_SDA) == LOW;
    sclLow();
    return ack;
  }

  bool probe(uint8_t a) {
    i2cStart();
    bool ack = i2cWrite(a << 1);
    i2cStop();
    return ack;
  }

  // ---- PCF8574 → HD44780 ----
  void expanderWrite(uint8_t d) {
    i2cStart(); i2cWrite(addr << 1); i2cWrite(d | BIT_BL); i2cStop();
  }
  void write4(uint8_t nibbleWithFlags) {
    expanderWrite(nibbleWithFlags | BIT_EN);   // EN HIGH
    expanderWrite(nibbleWithFlags);            // EN LOW → LCD가 값을 읽음
    delayMicroseconds(40);
  }
  void send(uint8_t value, uint8_t flags) {
    write4((value & 0xF0) | flags);
    write4(((value << 4) & 0xF0) | flags);
  }
  void command(uint8_t c) { send(c, 0); }
  void data(uint8_t c)    { send(c, BIT_RS); }
  void setCursor(uint8_t col, uint8_t row) { command(0x80 | (col + row * 0x40)); }

  // 빈 칸 막대용 사용자 정의 문자 (밑줄)
  const uint8_t CHAR_EMPTY[8] = {0, 0, 0, 0, 0, 0, 0, 0x1F};
}

namespace Display {

uint8_t begin() {
  sdaRelease(); sclRelease();
  delay(50);

  // 흔한 주소부터 확인: 0x27, 0x3F, 그 외 PCF8574/PCF8574A 범위
  const uint8_t candidates[] = {0x27, 0x3F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
                                0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E};
  addr = 0;
  for (uint8_t a : candidates) {
    if (probe(a)) { addr = a; break; }
  }
  if (!addr) return 0;

  // HD44780 4비트 초기화 순서 (데이터시트)
  expanderWrite(0);
  delay(50);
  write4(0x30); delayMicroseconds(4500);
  write4(0x30); delayMicroseconds(4500);
  write4(0x30); delayMicroseconds(150);
  write4(0x20);                       // 4비트 모드
  command(0x28);                      // 2줄, 5x8 글꼴
  command(0x0C);                      // 화면 켜기, 커서 끄기
  command(0x01); delay(2);            // 지우기
  command(0x06);                      // 글자 쓰면 오른쪽으로

  command(0x40);                      // CGRAM 0번에 빈 칸 문자 저장
  for (uint8_t i = 0; i < 8; i++) data(CHAR_EMPTY[i]);
  setCursor(0, 0);

  for (uint8_t r = 0; r < 2; r++) { memset(cache[r], ' ', 16); cache[r][16] = 0; }
  return addr;
}

bool ok() { return addr != 0; }

void line(uint8_t row, const char* text) {
  if (!addr || row > 1) return;
  char buf[16];
  bool ended = false;
  for (uint8_t i = 0; i < 16; i++) {
    char c = ended ? ' ' : text[i];
    if (c == 0) { ended = true; c = ' '; }
    buf[i] = c;
  }
  int8_t cursorAt = -1;                 // 커서가 이미 올바른 위치면 이동 명령 생략
  for (uint8_t i = 0; i < 16; i++) {
    if (cache[row][i] == buf[i]) continue;
    if (cursorAt != (int8_t)i) setCursor(i, row);
    data((uint8_t)buf[i]);
    cache[row][i] = buf[i];
    cursorAt = i + 1;
  }
}

void progress(uint8_t row, uint8_t pct) {
  if (pct > 100) pct = 100;
  char buf[17];
  const uint8_t cells = 12;
  uint8_t filled = (uint16_t)pct * cells / 100;
  for (uint8_t i = 0; i < cells; i++) buf[i] = (i < filled) ? (char)0xFF : (char)0x08; // 0xFF=꽉 찬 칸, 0x08=CGRAM 0번(빈 칸)
  snprintf(buf + cells, 5, "%3u%%", pct);
  line(row, buf);
}

}  // namespace Display
