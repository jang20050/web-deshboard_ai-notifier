// XIAO ESP32S3 (Sense) — AI 작업 알림 원격 중계기
//
// 하는 일
//   1. 같은 Wi-Fi의 PC bridge와 1초마다 동기화: 내 상태(칩 온도·Wi-Fi 신호)를 보내고 AI 작업 상태를 받음
//   2. 휴대폰 페이지 제공: http://ai-notifier.local (또는 시리얼 모니터에 표시된 IP)
//      → 상태·진행도 확인, [부저 끄기] 버튼
//   3. (선택) 새 알림이 나면 ntfy로 휴대폰 잠금 화면 알림 + [부저 끄기] 버튼
//   4. 보드의 BOOT 버튼을 눌러도 부저 끄기, 보드 LED로 상태 표시
//
// bridge 찾기: secrets.h 의 BRIDGE_HOST 가 비어 있으면 bridge가 2초마다 보내는 UDP 신호(포트 47800)로 자동 설정
// 카메라·마이크(Sense 확장판)는 사용하지 않습니다.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiUdp.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "include/secrets.example.h 를 include/secrets.h 로 복사하고 Wi-Fi·토큰을 적어 주세요."
#endif
#include "phone_page.h"

// ───────────────────────────────────────── 설정
static const char FW_VERSION[] = "0.1.0";
static const int PIN_LED = LED_BUILTIN;   // XIAO ESP32S3 사용자 LED (GPIO21, LOW = 켜짐)
static const int PIN_BOOT = 0;            // BOOT 버튼 (누르면 LOW)
static const uint16_t BEACON_PORT = 47800;
static const uint32_t SYNC_MS = 1000;
static const uint32_t BRIDGE_TIMEOUT_MS = 1500;
static const uint32_t BRIDGE_LOST_MS = 5000;   // 이 시간 동안 응답이 없으면 '연결 안 됨'

// ───────────────────────────────────────── 공유 상태 (동기화 작업 ↔ 웹 서버)
struct AiState {
  String state = "IDLE", phase, alert, inputReason, project, lastAck;
  int percent = 0;
  long elapsed = -1, duration = -1, alertElapsed = -1, alertSeq = -1;
};

static SemaphoreHandle_t lock;
static AiState ai;
static IPAddress bridgeIp;
static uint16_t bridgePort = BRIDGE_PORT;
static bool haveBridge = false;
static String foundBy = "none";            // beacon / config / none
static uint32_t lastOkMs = 0;
static String bridgeErr = "PC의 bridge를 찾는 중";
static long pushedSeq = -1;                // ntfy로 알린 마지막 알림 번호
static int pushOk = -1;                    // -1 없음, 0 실패, 1 성공
static uint32_t pushAtMs = 0;

static WebServer server(80);
static WiFiUDP udp;

static bool bridgeOk() { return lastOkMs && millis() - lastOkMs < BRIDGE_LOST_MS; }

static String bridgeUrl(const char* path) {
  return String("http://") + bridgeIp.toString() + ":" + bridgePort + path;
}

static String phoneUrl() { return String("http://") + WiFi.localIP().toString() + "/"; }

// ───────────────────────────────────────── Wi-Fi
static void connectWiFi() {
  WiFi.setHostname(DEVICE_NAME);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("Wi-Fi '%s' 연결 중", WIFI_SSID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    digitalWrite(PIN_LED, !digitalRead(PIN_LED));
    delay(250);
    Serial.print('.');
  }
  digitalWrite(PIN_LED, HIGH);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n연결됨: %s  (신호 %d dBm)\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("\nWi-Fi 연결 실패. SSID·비밀번호, 2.4GHz 여부를 확인하세요. 계속 재시도합니다.");
  }
}

// ───────────────────────────────────────── bridge 찾기
static void useConfiguredBridge() {
  if (strlen(BRIDGE_HOST) == 0) return;
  IPAddress ip;
  if (ip.fromString(BRIDGE_HOST) || WiFi.hostByName(BRIDGE_HOST, ip)) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bridgeIp = ip;
    haveBridge = true;
    foundBy = "config";
    xSemaphoreGive(lock);
    Serial.printf("bridge 주소(설정값): %s:%u\n", ip.toString().c_str(), bridgePort);
  }
}

static void listenBeacon() {
  int n = udp.parsePacket();
  if (n <= 0) return;
  char buf[160];
  int len = udp.read(buf, sizeof(buf) - 1);
  buf[len > 0 ? len : 0] = 0;
  if (strlen(BRIDGE_HOST) > 0) return;  // 설정값이 있으면 그것을 우선

  JsonDocument doc;
  if (deserializeJson(doc, buf) || strcmp(doc["svc"] | "", "ai-notifier") != 0) return;
  IPAddress ip = udp.remoteIP();
  uint16_t port = doc["port"] | BRIDGE_PORT;
  xSemaphoreTake(lock, portMAX_DELAY);
  bool changed = !haveBridge || ip != bridgeIp || port != bridgePort;
  bridgeIp = ip;
  bridgePort = port;
  haveBridge = true;
  foundBy = "beacon";
  xSemaphoreGive(lock);
  if (changed) Serial.printf("bridge 자동 찾음: %s:%u (%s)\n", ip.toString().c_str(), port, doc["name"] | "?");
}

// ───────────────────────────────────────── ntfy (선택)
static String fmtDur(long s) {
  if (s < 0) return "";
  char b[24];
  if (s < 60) snprintf(b, sizeof(b), "%ld초", s);
  else snprintf(b, sizeof(b), "%ld분 %02ld초", s / 60, s % 60);
  return b;
}

static void pushNtfy(const AiState& a) {
  if (strlen(NTFY_TOPIC) == 0) return;
  JsonDocument doc;
  doc["topic"] = NTFY_TOPIC;
  bool done = a.state == "DONE";
  doc["title"] = done ? "AI 작업 완료" : (a.state == "INPUT" ? "AI가 답을 기다립니다" : "AI 작업 오류");
  String msg = done ? ("걸린 시간 " + fmtDur(a.duration)) : (a.state == "INPUT" ? "Claude Code 창에서 답해 주세요" : "Claude Code 창을 확인하세요");
  if (a.project.length()) msg += " · " + a.project;
  doc["message"] = msg;
  doc["priority"] = done ? 3 : 4;
  doc["tags"].add(done ? "white_check_mark" : "bell");
  JsonObject act = doc["actions"].add<JsonObject>();
  act["action"] = "http";
  act["label"] = "부저 끄기";
  act["url"] = phoneUrl() + "api/ack";
  act["method"] = "POST";
  act["headers"]["Content-Type"] = "application/json";
  act["body"] = "{\"method\":\"phone\"}";
  act["clear"] = true;
  JsonObject view = doc["actions"].add<JsonObject>();
  view["action"] = "view";
  view["label"] = "상태 보기";
  view["url"] = phoneUrl();
  String body;
  serializeJson(doc, body);

  WiFiClientSecure tls;
  tls.setInsecure();  // 인증서 검증 생략 (알림 내용에 비밀 정보 없음)
  HTTPClient https;
  https.setTimeout(5000);
  int code = -1;
  if (https.begin(tls, String(NTFY_SERVER) + "/")) {
    https.addHeader("Content-Type", "application/json");
    code = https.POST(body);
    https.end();
  }
  pushOk = (code >= 200 && code < 300) ? 1 : 0;
  pushAtMs = millis();
  Serial.printf("ntfy 알림 %s (%d)\n", pushOk ? "보냄" : "실패", code);
}

// ───────────────────────────────────────── bridge 동기화 (코어 0에서 실행)
static void syncOnce() {
  xSemaphoreTake(lock, portMAX_DELAY);
  bool have = haveBridge;
  String url = have ? bridgeUrl("/api/esp32/heartbeat") : "";
  String found = foundBy;
  int pOk = pushOk;
  uint32_t pAt = pushAtMs;
  xSemaphoreGive(lock);
  if (!have || WiFi.status() != WL_CONNECTED) return;

  JsonDocument hb;
  hb["chip_temp_c"] = roundf(temperatureRead() * 10) / 10.0;
  hb["rssi_dbm"] = WiFi.RSSI();
  hb["ip"] = WiFi.localIP().toString();
  hb["uptime_s"] = millis() / 1000;
  hb["fw"] = FW_VERSION;
  hb["free_heap"] = ESP.getFreeHeap();
  hb["phone_url"] = phoneUrl();
  hb["ntfy"] = strlen(NTFY_TOPIC) > 0;
  if (pOk >= 0) {
    hb["push_ok"] = pOk == 1;
    hb["push_age_s"] = (millis() - pAt) / 1000;
  }
  hb["found_by"] = found;
  String body;
  serializeJson(hb, body);

  HTTPClient http;
  http.setConnectTimeout(BRIDGE_TIMEOUT_MS);
  http.setTimeout(BRIDGE_TIMEOUT_MS);
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Notifier-Token", BRIDGE_TOKEN);
  int code = http.POST(body);
  String resp = code > 0 ? http.getString() : "";
  http.end();

  if (code != 200) {
    xSemaphoreTake(lock, portMAX_DELAY);
    bridgeErr = code == 401 ? "토큰이 맞지 않습니다 (secrets.h의 BRIDGE_TOKEN 확인)"
              : code < 0   ? "PC에 연결할 수 없습니다 (bridge 실행·방화벽 확인)"
                           : "PC 응답 오류 " + String(code);
    xSemaphoreGive(lock);
    return;
  }

  JsonDocument doc;
  if (deserializeJson(doc, resp)) return;
  AiState a;
  a.state = doc["state"] | "IDLE";
  a.percent = doc["percent"] | 0;
  a.phase = doc["phase"] | "";
  a.elapsed = doc["elapsed"].isNull() ? -1 : doc["elapsed"].as<long>();
  a.duration = doc["duration"].isNull() ? -1 : doc["duration"].as<long>();
  a.alert = doc["alert"] | "";
  a.alertElapsed = doc["alert_elapsed"].isNull() ? -1 : doc["alert_elapsed"].as<long>();
  a.alertSeq = doc["alert_seq"] | 0;
  a.inputReason = doc["input_reason"] | "";
  a.project = doc["project"] | "";
  a.lastAck = doc["last_ack"] | "";

  bool firstSync = false, needPush = false;
  xSemaphoreTake(lock, portMAX_DELAY);
  ai = a;
  lastOkMs = millis();
  bridgeErr = "";
  if (pushedSeq < 0) {           // 켜진 직후: 이전 알림은 다시 보내지 않음
    pushedSeq = a.alertSeq;
    firstSync = true;
  } else if (a.alertSeq != pushedSeq) {
    pushedSeq = a.alertSeq;
    needPush = a.state == "DONE" || a.state == "INPUT" || a.state == "ERROR";
  }
  xSemaphoreGive(lock);
  if (firstSync) Serial.println("bridge 연결됨");
  if (needPush) pushNtfy(a);
}

static void syncTask(void*) {
  for (;;) {
    uint32_t t0 = millis();
    syncOnce();
    uint32_t used = millis() - t0;
    vTaskDelay(pdMS_TO_TICKS(used < SYNC_MS ? SYNC_MS - used : 50));
  }
}

// ───────────────────────────────────────── 부저 끄기 요청 → bridge
static String sendAck(const char* method, bool& acked) {
  acked = false;
  xSemaphoreTake(lock, portMAX_DELAY);
  bool have = haveBridge;
  String url = have ? bridgeUrl("/api/ack") : "";
  xSemaphoreGive(lock);
  if (!have) return "PC의 bridge를 아직 찾지 못했습니다";

  HTTPClient http;
  http.setConnectTimeout(BRIDGE_TIMEOUT_MS);
  http.setTimeout(2000);
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Notifier-Token", BRIDGE_TOKEN);
  int code = http.POST(String("{\"method\":\"") + method + "\"}");
  String resp = code > 0 ? http.getString() : "";
  http.end();
  if (code != 200) return code == 401 ? "토큰이 맞지 않습니다" : "PC에 연결할 수 없습니다";
  JsonDocument doc;
  if (!deserializeJson(doc, resp)) acked = doc["acked"] | false;
  return "";
}

// ───────────────────────────────────────── 휴대폰 웹 페이지
static void handleRoot() { server.send_P(200, "text/html; charset=utf-8", PHONE_PAGE); }

static void handleState() {
  JsonDocument doc;
  xSemaphoreTake(lock, portMAX_DELAY);
  JsonObject a = doc["ai"].to<JsonObject>();
  a["state"] = ai.state;
  a["percent"] = ai.percent;
  a["phase"] = ai.phase;
  if (ai.elapsed >= 0) a["elapsed"] = ai.elapsed; else a["elapsed"] = nullptr;
  if (ai.duration >= 0) a["duration"] = ai.duration; else a["duration"] = nullptr;
  a["alert"] = ai.alert;
  a["alert_elapsed"] = ai.alertElapsed;
  a["alert_seq"] = ai.alertSeq;
  a["input_reason"] = ai.inputReason;
  a["project"] = ai.project;
  a["last_ack"] = ai.lastAck;
  JsonObject e = doc["esp"].to<JsonObject>();
  e["ip"] = WiFi.localIP().toString();
  e["rssi"] = WiFi.RSSI();
  e["temp"] = roundf(temperatureRead() * 10) / 10.0;
  e["fw"] = FW_VERSION;
  e["bridge"] = haveBridge ? bridgeIp.toString() + ":" + bridgePort : "";
  e["found_by"] = foundBy;
  e["bridge_ok"] = bridgeOk();
  e["bridge_err"] = bridgeErr;
  e["ntfy"] = strlen(NTFY_TOPIC) > 0;
  if (pushOk >= 0) e["push_ok"] = pushOk == 1;
  xSemaphoreGive(lock);
  String out;
  serializeJson(doc, out);
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "application/json", out);
}

static void handleAck() {
  // 휴대폰 페이지 버튼 또는 ntfy 알림의 [부저 끄기] 버튼
  bool acked;
  String err = sendAck("phone", acked);
  JsonDocument doc;
  doc["ok"] = err.isEmpty();
  doc["acked"] = acked;
  if (!err.isEmpty()) doc["error"] = err;
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
  Serial.printf("휴대폰에서 부저 끄기 → %s\n", err.isEmpty() ? (acked ? "꺼짐" : "알림 없음") : err.c_str());
}

// ───────────────────────────────────────── LED·버튼
static void updateLed() {
  xSemaphoreTake(lock, portMAX_DELAY);
  String s = ai.state;
  bool ok = bridgeOk();
  xSemaphoreGive(lock);
  uint32_t t = millis();
  bool on;
  if (WiFi.status() != WL_CONNECTED) on = (t / 1000) % 2;                  // Wi-Fi 없음: 1초 깜빡임
  else if (!ok) on = (t % 2000) < 120 || ((t % 2000) > 240 && (t % 2000) < 360);  // PC 없음: 두 번 깜빡
  else if (s == "INPUT") on = (t / 200) % 2;                                // 답변 대기: 빠르게
  else if (s == "DONE" || s == "ERROR") on = (t / 700) % 2;                 // 완료: 천천히
  else if (s == "WORK") on = (t % 3000) < 80;                               // 작업 중: 3초마다 짧게
  else on = false;
  digitalWrite(PIN_LED, on ? LOW : HIGH);
}

static void checkBootButton() {
  static bool last = HIGH, stable = HIGH;
  static uint32_t changed = 0;
  bool now = digitalRead(PIN_BOOT);
  if (now != last) { last = now; changed = millis(); }
  if (millis() - changed > 40 && now != stable) {
    stable = now;
    if (stable == LOW) {
      bool acked;
      String err = sendAck("esp32", acked);
      Serial.printf("BOOT 버튼 → %s\n", err.isEmpty() ? (acked ? "부저 꺼짐" : "알림 없음") : err.c_str());
    }
  }
}

// ───────────────────────────────────────── 시작
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, HIGH);
  pinMode(PIN_BOOT, INPUT_PULLUP);
  delay(300);
  Serial.printf("\nAI 작업 알림 원격 중계기 %s (XIAO ESP32S3)\n", FW_VERSION);

  lock = xSemaphoreCreateMutex();
  connectWiFi();

  if (MDNS.begin(DEVICE_NAME)) {
    MDNS.addService("http", "tcp", 80);
    Serial.printf("휴대폰에서 접속: http://%s.local  또는  %s\n", DEVICE_NAME, phoneUrl().c_str());
  }
  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/state", HTTP_GET, handleState);
  server.on("/api/ack", HTTP_POST, handleAck);
  server.onNotFound([] { server.send(404, "text/plain; charset=utf-8", "없는 주소입니다"); });
  server.begin();

  udp.begin(BEACON_PORT);
  useConfiguredBridge();
  if (!haveBridge) Serial.println("bridge 신호를 기다리는 중… (PC에서 start_bridge.bat 실행)");

  xTaskCreatePinnedToCore(syncTask, "sync", 12288, nullptr, 1, nullptr, 0);
}

void loop() {
  server.handleClient();
  listenBeacon();
  checkBootButton();
  updateLed();

  static uint32_t lastWifiLog = 0;
  if (WiFi.status() != WL_CONNECTED && millis() - lastWifiLog > 10000) {
    lastWifiLog = millis();
    Serial.println("Wi-Fi 다시 연결 중…");
    WiFi.reconnect();
  }
  delay(2);
}
