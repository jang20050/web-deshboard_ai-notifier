// secrets.example.h → 같은 폴더에 secrets.h 로 복사한 뒤 값을 채우세요.
// secrets.h 는 Git에 올라가지 않습니다 (.gitignore).
#pragma once

// ── 집/교실 Wi-Fi (2.4GHz만 지원. 5GHz 전용 Wi-Fi에는 연결되지 않음) ──
#define WIFI_SSID "와이파이이름"
#define WIFI_PASS "와이파이비밀번호"

// ── PC의 bridge ──
// 비워 두면("") 같은 Wi-Fi에서 bridge가 보내는 신호를 듣고 자동으로 찾습니다(권장).
// 자동으로 못 찾으면 PC의 IP를 직접 적으세요. 예: "192.168.0.10"
#define BRIDGE_HOST ""
#define BRIDGE_PORT 8000
// bridge 창 첫 줄의 "같은 Wi-Fi 접속 토큰" (또는 web_deshboard/data/access_token.txt)
#define BRIDGE_TOKEN "여기에_토큰_16자리"

// ── 이 장치 이름: 휴대폰에서 http://ai-notifier.local 로 접속 ──
#define DEVICE_NAME "ai-notifier"

// ── (선택) 잠금 화면 알림: ntfy 앱 ──
// 휴대폰에 ntfy 앱을 설치하고 아래와 같은 주제(topic)를 구독하세요.
// 주제 이름이 곧 비밀번호 역할을 하므로 남이 추측하기 어렵게 지으세요. 비워 두면 사용 안 함.
// ESP32-S3가 인터넷에 연결되어 있어야 합니다 (알림 내용: 상태와 소요 시간만, 작업 내용 없음).
#define NTFY_TOPIC ""
#define NTFY_SERVER "https://ntfy.sh"
