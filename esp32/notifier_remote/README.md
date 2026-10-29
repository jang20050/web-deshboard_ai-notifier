# esp32/notifier_remote — XIAO ESP32S3 휴대폰 중계기 (PlatformIO)

같은 Wi-Fi에서 **휴대폰으로 AI 작업 완료를 확인하고, 부저를 원격으로 끄는** 장치입니다.

```
Claude Code ─ hooks ─▶ PC bridge ──USB──▶ UNO (LCD·RGB·부저)
                         ▲   │ 2초마다 "여기 있어요" (UDP 47800)
            1초마다 동기화 │   ▼
                     XIAO ESP32S3 ◀── 휴대폰 브라우저  http://ai-notifier.local
                         │                 [부저 끄기]
                         └─(선택, 인터넷)─▶ ntfy ─▶ 휴대폰 잠금 화면 알림 [부저 끄기]
```

## 할 수 있는 것
| 기능 | 방법 |
|---|---|
| 상태·진행도 보기 | 휴대폰에서 `http://ai-notifier.local` (안 되면 시리얼 모니터에 찍힌 IP) |
| 부저 끄기 | 휴대폰 페이지의 **[부저 끄기]**, 보드의 **BOOT 버튼**, ntfy 알림의 **[부저 끄기]** |
| 휴대폰 소리·진동 | 페이지에서 "소리·진동 켜기"를 한 번 누르면, 페이지가 열려 있는 동안 새 알림마다 울림 |
| 잠금 화면 알림 | (선택) ntfy 앱 — 아래 참고 |
| 보드 LED | 답변 대기: 빠르게 깜빡 · 완료: 천천히 깜빡 · 작업 중: 3초마다 짧게 · PC 못 찾음: 두 번씩 깜빡 · Wi-Fi 없음: 1초 깜빡 |

카메라·마이크(Sense 확장판)는 쓰지 않습니다. 끼워 둔 채로 사용해도 됩니다.

## 준비 (처음 한 번)

1. **VS Code + PlatformIO 확장** 설치
2. VS Code에서 **이 폴더(`notifier_remote`)를 열기** (web_deshboard 전체가 아니라 이 폴더)
3. `include/secrets.example.h` 를 복사해 **`include/secrets.h`** 로 저장하고 값 채우기
   | 항목 | 값 |
   |---|---|
   | `WIFI_SSID`, `WIFI_PASS` | PC와 **같은** Wi-Fi (2.4GHz) |
   | `BRIDGE_TOKEN` | bridge 창 첫 줄의 "같은 Wi-Fi 접속 토큰" (= `web_deshboard/data/access_token.txt`) |
   | `BRIDGE_HOST` | 비워 두기 (자동 찾기). 못 찾으면 PC IP |
   | `NTFY_TOPIC` | (선택) 잠금 화면 알림용 |
4. XIAO를 USB-C로 연결 → PlatformIO 아래 막대의 **→ (Upload)** → **🔌 (Serial Monitor)**
   - 업로드가 안 되면: BOOT 버튼을 누른 채 RESET을 눌렀다 떼고, BOOT를 뗀 뒤 다시 Upload

시리얼 모니터에 이렇게 나오면 성공입니다:
```
연결됨: 192.168.0.50  (신호 -55 dBm)
휴대폰에서 접속: http://ai-notifier.local  또는  http://192.168.0.50/
bridge 자동 찾음: 192.168.0.10:8000 (DESK-05)
bridge 연결됨
```
PC 대시보드의 ESP32-S3 카드도 **연결됨**으로 바뀝니다.

## PC 쪽 확인
- bridge 처음 실행 때 **Windows 방화벽** 창이 뜨면 **개인 네트워크 허용** (공용은 체크 안 해도 됨)
- Windows 설정 → 네트워크 → 사용 중인 Wi-Fi의 프로필이 **개인**이어야 합니다 (공용이면 막힘)

## (선택) 잠금 화면 알림 — ntfy
웹 페이지만으로는 잠긴 휴대폰에 알림을 보낼 수 없어서, 무료 알림 앱 ntfy를 씁니다.
1. 휴대폰에 **ntfy** 앱 설치 → **+** → 주제(topic) 이름 입력 (예: `ai-wj-7f3k2` — 남이 추측하기 어렵게)
2. `secrets.h` 의 `NTFY_TOPIC` 에 같은 이름 → 다시 Upload
3. 완료·답변 대기 때 알림이 오고, 알림의 **[부저 끄기]** 를 누르면 꺼집니다 (휴대폰이 같은 Wi-Fi에 있을 때)

- ESP32-S3가 인터넷에 나갈 수 있어야 합니다 (집 공유기는 보통 가능, 학교망은 막혀 있을 수 있음)
- 보내는 내용: "AI 작업 완료 · 걸린 시간 · 프로젝트 폴더 이름"뿐, 작업 내용은 보내지 않습니다
- ntfy.sh 공용 서버를 쓰므로 주제 이름을 아는 사람은 알림을 볼 수 있습니다

## 문제 해결 (시리얼 모니터 메시지 기준)
| 메시지 | 조치 |
|---|---|
| `Wi-Fi 연결 실패` | SSID·비밀번호, 2.4GHz인지 확인 (5GHz 전용 불가) |
| `bridge 신호를 기다리는 중…`이 계속 | PC bridge 실행·방화벽 확인. 공유기가 방송을 막으면 `BRIDGE_HOST`에 PC IP 직접 입력 |
| 휴대폰 페이지에 "토큰이 맞지 않습니다" | `BRIDGE_TOKEN`을 bridge 창의 토큰으로 다시 적고 Upload |
| `ai-notifier.local` 이 안 열림 | 일부 안드로이드는 .local 미지원 → 시리얼 모니터에 찍힌 IP로 접속 |

## 파일
| 파일 | 내용 |
|---|---|
| `platformio.ini` | 보드(seeed_xiao_esp32s3), Arduino-ESP32 2.0.17, ArduinoJson 7.2.1 |
| `src/main.cpp` | Wi-Fi, bridge 자동 찾기·동기화(코어 0), 휴대폰 웹 서버, ntfy, LED, BOOT 버튼 |
| `src/phone_page.h` | 휴대폰 페이지 (HTML·CSS·JS 한 파일, 인터넷 불필요) |
| `include/secrets.example.h` | 설정 견본 → `secrets.h` 로 복사 (Git 제외) |

## 통신 규칙 (bridge API)
| 요청 | 내용 |
|---|---|
| `POST /api/esp32/heartbeat` + 헤더 `X-Notifier-Token` | ESP32 상태(칩 온도·RSSI·IP…)를 보내고, 응답으로 AI 상태(state, percent, phase, alert_seq …)를 받음 |
| `POST /api/ack` `{"method":"phone"|"esp32"}` | 부저 끄기 → UNO에 SEEN 전송 |
| UDP 47800 방송 `{"svc":"ai-notifier","port":8000}` | bridge 자동 찾기 (토큰은 포함하지 않음) |

`alert_seq`는 알림이 새로 날 때마다 1씩 커집니다. ESP32는 이 값이 바뀔 때만 ntfy를 보내서 같은 알림을 두 번 보내지 않습니다.
