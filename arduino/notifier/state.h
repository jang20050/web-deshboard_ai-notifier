// state.h — 장치 상태 (README의 상태 정의와 동일)
#pragma once
#include <Arduino.h>

enum State : uint8_t { ST_IDLE, ST_WORK, ST_INPUT, ST_DONE, ST_ERROR, ST_SEEN };

inline bool isAlert(State s) { return s == ST_INPUT || s == ST_DONE || s == ST_ERROR; }

// "WORK" 같은 문자열 → State. 모르는 값이면 false
inline bool parseState(const char* s, State& out) {
  if (!strcmp(s, "IDLE"))  { out = ST_IDLE;  return true; }
  if (!strcmp(s, "WORK"))  { out = ST_WORK;  return true; }
  if (!strcmp(s, "INPUT")) { out = ST_INPUT; return true; }
  if (!strcmp(s, "DONE"))  { out = ST_DONE;  return true; }
  if (!strcmp(s, "ERROR")) { out = ST_ERROR; return true; }
  if (!strcmp(s, "SEEN"))  { out = ST_SEEN;  return true; }
  return false;
}

inline const char* stateName(State s) {
  switch (s) {
    case ST_IDLE:  return "IDLE";
    case ST_WORK:  return "WORK";
    case ST_INPUT: return "INPUT";
    case ST_DONE:  return "DONE";
    case ST_ERROR: return "ERROR";
    case ST_SEEN:  return "SEEN";
  }
  return "?";
}
