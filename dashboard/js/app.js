// 대시보드 화면 갱신. 모든 외부 문자열은 textContent로 넣습니다(HTML 해석 안 함).
import { connect, getJSON } from "./socket.js";
import { LineChart } from "./charts.js";
import { refreshHistory } from "./history.js";
import { $, fmtDur, mmss, rel, hhmmss, setLevel, LEVEL_TEXT } from "./util.js";

const STATE_TEXT = { IDLE: "대기 중", WORK: "작업 중", INPUT: "답변 기다리는 중", DONE: "작업 완료", ERROR: "오류", SEEN: "확인함" };
const STATE_ICON = { IDLE: "i-idle", WORK: "i-work", INPUT: "i-input", DONE: "i-done", ERROR: "i-error", SEEN: "i-seen" };
const PHASE_KO = { read: "파악", plan: "정리", build: "만드는 중", review: "최종 검토" };
const PHASES = ["read", "plan", "build", "review", "done"];
const ACK_KO = { gesture: "ok 제스처", button: "빵판 버튼", answered: "Claude에서 바로 답함", new_task: "새 작업 시작",
  phone: "휴대폰(ESP32-S3)", esp32: "ESP32-S3 버튼", dashboard: "대시보드 버튼" };
const REASON_KO = { permission: "권한 요청", AskUserQuestion: "질문", ExitPlanMode: "계획 승인 요청" };
const TOOL_KO = {
  Read: "파일 읽기", Grep: "내용 검색", Glob: "파일 찾기", LS: "폴더 보기", WebFetch: "웹 페이지 읽기", WebSearch: "웹 검색",
  Edit: "파일 수정", MultiEdit: "파일 여러 곳 수정", Write: "파일 작성", NotebookEdit: "노트북 수정", Bash: "명령 실행",
  PowerShell: "명령 실행", TodoWrite: "할 일 정리", TaskCreate: "할 일 만들기", TaskUpdate: "할 일 갱신",
  AskUserQuestion: "나에게 질문", ExitPlanMode: "계획 승인 요청", Agent: "보조 에이전트", Task: "보조 에이전트",
};

let paused = false;
let pending = null;     // 일시정지 중 받은 최신 상태
let last = null;        // 마지막으로 그린 상태
let sysHistory = [];
let lastSysTs = 0;
let camTimer = null;
let historyKey = "";
let access = { local: true, lan_enabled: false };

const cpuChart = new LineChart($("#chart-cpu"), {
  name: "CPU 사용량", unit: "%", color: "var(--series-1)", yMin: 0, yMax: 100,
  refs: [{ value: 75, label: "주의 75%" }, { value: 90, label: "높음 90%" }],
});
const tempChart = new LineChart($("#chart-temp"), {
  name: "CPU 온도", unit: "°C", color: "var(--series-2)", yMin: 20, yMax: 100,
  refs: [{ value: 80, label: "주의 80°C" }, { value: 90, label: "높음 90°C" }],
});

// ───────────────────────────────────────────── 연결 (접속 정보를 먼저 받은 뒤 실시간 연결)
const startLive = () => connect({
  token: access.ws_token,
  onMessage: (s) => {
    collectSystem(s.system);
    if (paused) { pending = s; return; }
    render(s);
  },
  onStatus: (st) => {
    const c = $("#conn");
    c.dataset.state = st;
    c.querySelector("use").setAttribute("href", st === "open" ? "#i-good" : "#i-critical");
    $("#conn-text").textContent = st === "open" ? "실시간 연결됨" : st === "connecting" ? "bridge 연결 중…" : "bridge 연결 끊김 · 다시 연결 중";
  },
});

getJSON("/api/system/history").then((rows) => {
  sysHistory = rows.map((r) => ({ t: r.ts, cpu: r.cpu, temp: r.temp }));
  lastSysTs = rows.length ? rows[rows.length - 1].ts : 0;
  drawCharts(last?.system);
}).catch(() => {});
getJSON("/api/access").then((a) => { access = a; renderAccess(); }).catch(() => {}).finally(startLive);
refreshHistory();
setInterval(() => { if (!paused) refreshHistory(); }, 60000);

// ───────────────────────────────────────────── 일시정지·테마
function setPaused(v) {
  paused = v;
  const b = $("#pause-btn");
  b.setAttribute("aria-pressed", String(v));
  b.querySelector("span").textContent = v ? "자동 갱신 다시 시작" : "자동 갱신 일시정지";
  b.querySelector("use").setAttribute("href", v ? "#i-play" : "#i-pause");
  $("#paused-banner").hidden = !v;
  document.body.toggleAttribute("data-paused", v);
  if (!v && pending) { render(pending); pending = null; drawCharts(last?.system); refreshHistory(); }
  if (v) stopCam();
}
$("#pause-btn").addEventListener("click", () => setPaused(!paused));
$("#resume-link").addEventListener("click", () => { setPaused(false); $("#pause-btn").focus(); });

const THEMES = ["system", "light", "dark"];
const THEME_KO = { system: "시스템", light: "밝게", dark: "어둡게" };
function applyTheme(t) {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  $("#theme-text").textContent = THEME_KO[t];
  $("#theme-btn").setAttribute("aria-label", `화면 테마: ${THEME_KO[t]}. 눌러서 바꾸기`);
  try { t === "system" ? localStorage.removeItem("theme") : localStorage.setItem("theme", t); } catch (e) {}
  drawCharts(last?.system);
}
let theme = document.documentElement.dataset.theme || "system";
applyTheme(theme);
$("#theme-btn").addEventListener("click", () => { theme = THEMES[(THEMES.indexOf(theme) + 1) % 3]; applyTheme(theme); });

// ───────────────────────────────────────────── 전체 그리기
function render(s) {
  const prev = last;
  last = s;
  $("#updated").textContent = hhmmss(s.server_time);
  renderAI(s, prev);
  renderSystem(s.system);
  renderUno(s);
  renderCam(s.gesture);
  renderEsp(s.esp32);
  drawCharts(s.system);

  const key = `${s.task_id}|${s.state}`;
  if (key !== historyKey) { historyKey = key; refreshHistory(); }
}

function announce(text) {
  const a = $("#announcer");
  a.textContent = "";
  setTimeout(() => { a.textContent = text; }, 50);
}

// ───────────────────────────────────────────── AI 작업
function renderAI(s, prev) {
  const st = s.state;
  const card = $("#ai-card");
  card.dataset.state = st;
  $("#todo-card").dataset.state = st;
  $("#ai-icon").setAttribute("href", `#${STATE_ICON[st] || "i-idle"}`);
  $("#ai-state-text").textContent = STATE_TEXT[st] || st;

  const phaseKo = s.phase ? PHASE_KO[s.phase] : null;
  let meta = "작업 없음";
  if (st === "WORK") meta = `${phaseKo} 단계 · LCD 표시 ${s.phase_label}`;
  else if (st === "INPUT") meta = `${REASON_KO[s.input_reason] || "답변 필요"} · ${mmss(s.alert_elapsed_sec)} 경과`;
  else if (st === "DONE") meta = (s.lcd_text || "").replace("TOOK", "소요");
  else if (st === "SEEN") meta = `${s.alert === "INPUT" ? "답변 대기" : s.alert === "DONE" ? "완료" : "알림"} 알림을 확인함`;
  else if (st === "IDLE" && s.lcd_text) meta = `마지막 작업: ${s.lcd_text.replace("LAST OK", "짧게 끝남")}`;
  $("#ai-meta").textContent = meta;

  const showPct = st !== "IDLE";
  const pct = st === "DONE" || (st === "SEEN" && s.alert === "DONE") ? 100 : (s.percent ?? 0);
  $("#ai-pct").textContent = showPct ? pct : "—";
  $("#ai-phase").textContent = st === "WORK" || st === "INPUT" ? `${phaseKo || "—"} 단계` : st === "IDLE" ? "작업 없음" : "완료";
  $("#ai-bar-fill").style.width = `${showPct ? pct : 0}%`;
  const bar = $("#ai-bar");
  bar.setAttribute("aria-valuenow", String(showPct ? pct : 0));
  bar.setAttribute("aria-valuetext", showPct ? `${pct}%, ${STATE_TEXT[st]}${phaseKo ? `, ${phaseKo} 단계` : ""}` : "작업 없음");

  // 단계 표시
  const done = st === "DONE" || (st === "SEEN" && s.alert === "DONE");
  const curIdx = done ? 4 : s.phase ? PHASES.indexOf(s.phase) : -1;
  $("#ai-steps").querySelectorAll("li").forEach((li, i) => {
    li.toggleAttribute("data-done", curIdx > i || (done && i === 4));
    if (i === curIdx && st !== "IDLE") li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });

  const finished = s.elapsed_sec == null && s.last_duration_sec != null && st !== "IDLE";
  $("#ai-elapsed-label").textContent = finished ? "걸린 시간" : "경과 시간";
  $("#ai-elapsed").textContent = s.elapsed_sec != null ? fmtDur(s.elapsed_sec) : finished ? fmtDur(s.last_duration_sec) : "—";
  $("#ai-project").textContent = s.project || "—";
  $("#ai-last-ack").textContent = s.last_ack
    ? `${ACK_KO[s.last_ack.method] || s.last_ack.method} · ${s.last_ack.delay_sec}초 만에 (${rel(s.last_ack.at, s.server_time)})`
    : "—";

  // 지금 할 일
  const rules = s.rules || {};
  let main = "Claude Code에 작업을 요청하면 진행도가 표시됩니다.";
  let sub = `${rules.min_alert_sec ?? 20}초 이상 걸린 작업만 끝날 때 부저가 울립니다.`;
  if (st === "WORK") {
    main = "AI가 작업 중입니다. 자리를 비워도 됩니다.";
    sub = s.input_pending
      ? `권한 요청이 왔습니다. ${rules.input_delay_sec ?? 10}초 안에 답하지 않으면 장치가 알립니다.`
      : "끝나거나 내 답이 필요하면 LCD·불빛·부저로 알려 줍니다.";
  } else if (st === "INPUT") {
    main = `Claude가 내 답을 기다립니다 (${mmss(s.alert_elapsed_sec)} 경과).`;
    sub = "Claude Code 창에서 답하세요. 소리만 끄려면 ok 제스처 1초, 빵판 버튼, 또는 아래 [부저 끄기].";
  } else if (st === "DONE") {
    main = "작업이 끝났습니다. 결과를 확인하세요.";
    sub = "알림 끄기: ok 제스처 1초, 빵판 버튼, 휴대폰, 또는 아래 [부저 끄기].";
  } else if (st === "SEEN") {
    main = "알림을 확인했습니다.";
    sub = s.alert === "INPUT" ? "Claude Code에서 답하면 작업이 이어집니다." : "새 작업을 요청하면 다시 진행도가 표시됩니다.";
  } else if (st === "ERROR") {
    main = "오류가 났습니다. Claude Code 창을 확인하세요.";
  }
  $("#todo-main").textContent = main;
  $("#todo-sub").textContent = sub;
  const alerting = st === "INPUT" || st === "DONE" || st === "ERROR";
  $("#ack-btn").hidden = !alerting;
  if (!alerting && prev && prev.state !== st) $("#ack-msg").textContent = "";

  renderTimeline(s);

  if (!prev || prev.state !== st) {
    const extra = st === "INPUT" ? " Claude가 답을 기다립니다." : st === "DONE" ? " 결과를 확인하세요." : "";
    if (prev) announce(`AI 상태: ${STATE_TEXT[st]}.${extra}`);
  }
}

function describe(e) {
  switch (e.kind) {
    case "UserPromptSubmit": return "작업 요청 받음";
    case "PreToolUse": return TOOL_KO[e.detail] || e.detail || "도구 사용";
    case "Notification": return "권한 요청";
    case "RESUME": return "답변 받음 · 작업 재개";
    case "ALERT": return e.detail === "INPUT" ? "알림: 답변 대기" : e.detail === "DONE" ? "알림: 작업 완료" : "알림";
    case "ACK": return `확인: ${ACK_KO[e.detail] || e.detail}`;
    case "Stop": return "응답 끝";
    case "SessionEnd": return "세션 종료";
    default: return e.kind;
  }
}

function renderTimeline(s) {
  const list = $("#timeline");
  const items = (s.timeline || []).slice().reverse();
  $("#timeline-empty").hidden = items.length > 0;
  list.replaceChildren(...items.map((e) => {
    const li = document.createElement("li");
    li.dataset.kind = e.kind;
    const t = document.createElement("time");
    t.dateTime = new Date(e.at * 1000).toISOString();
    t.textContent = hhmmss(e.at);
    const ev = document.createElement("span");
    ev.className = "ev";
    ev.textContent = describe(e);
    const ph = document.createElement("span");
    ph.className = "ph";
    ph.textContent = e.phase ? `${PHASE_KO[{ READING: "read", PLANNING: "plan", BUILDING: "build", REVIEWING: "review" }[e.phase]] || e.phase} ${e.pct ?? ""}%` : "";
    li.append(t, ev, ph);
    return li;
  }));
}

// ───────────────────────────────────────────── 컴퓨터
function collectSystem(sys) {
  if (!sys || !sys.available || !sys.ts || sys.ts <= lastSysTs) return;
  lastSysTs = sys.ts;
  sysHistory.push({ t: sys.ts, cpu: sys.cpu_percent, temp: sys.temp?.value ?? null });
  const cutoff = sys.ts - 600;
  while (sysHistory.length && sysHistory[0].t < cutoff) sysHistory.shift();
}

function drawCharts(sys) {
  cpuChart.setData(sysHistory.map((p) => ({ t: p.t, v: p.cpu })));
  if (sys && sys.temp && sys.temp.value == null) {
    tempChart.setEmptyMessage(`CPU 온도를 읽을 수 없어 그래프가 없습니다. ${sys.temp.note || ""}`);
  }
  tempChart.setData(sysHistory.map((p) => ({ t: p.t, v: p.temp })));
}

function tile(id, { value, unit, meterPct, level, levelText, note }) {
  const t = $(id);
  t.querySelector("[data-v]").textContent = value;
  const u = t.querySelector(".tile__unit");
  u.hidden = value === "—";
  if (unit !== undefined) u.textContent = unit;
  const m = t.querySelector("[data-meter]");
  m.style.width = `${Math.max(0, Math.min(100, meterPct || 0))}%`;
  m.dataset.level = level;
  setLevel(t.querySelector("[data-lvl]"), level, levelText);
  t.querySelector("[data-note]").textContent = note || "";
}

function renderSystem(sys) {
  const pill = $("#pc-overall");
  if (!sys || !sys.available) {
    setLevel(pill, "unknown", sys?.note || "확인 중");
    return;
  }
  const L = sys.levels;
  setLevel(pill, sys.overall, { good: "부하 정상", warning: "부하 주의", critical: "과부하", unknown: "확인 중" }[sys.overall]);
  const th = sys.thresholds;

  tile("#tile-cpu", {
    value: Math.round(sys.cpu_percent), meterPct: sys.cpu_percent, level: L.cpu,
    levelText: LEVEL_TEXT[L.cpu],
    note: `코어 ${sys.cpu_count}개 · 주의 ${th.cpu[0]}% · 높음 ${th.cpu[1]}%` +
      (sys.cpu_high_sec ? ` · ${th.cpu[1]}% 이상 ${sys.cpu_high_sec}초째` : ""),
  });
  const tv = sys.temp?.value;
  tile("#tile-temp", {
    value: tv == null ? "—" : tv.toFixed(0), meterPct: tv == null ? 0 : tv, level: L.temp,
    levelText: tv == null ? "측정 불가" : LEVEL_TEXT[L.temp],
    note: tv == null ? sys.temp?.note : `${sys.temp.source} · 주의 ${th.temp[0]}°C · 높음 ${th.temp[1]}°C`,
  });
  tile("#tile-mem", {
    value: Math.round(sys.mem_percent), meterPct: sys.mem_percent, level: L.mem, levelText: LEVEL_TEXT[L.mem],
    note: `${sys.mem_used_gb} / ${sys.mem_total_gb} GB 사용`,
  });
  const b = sys.battery;
  if (!b) {
    tile("#tile-batt", { value: "—", meterPct: 0, level: "unknown", levelText: "배터리 없음",
      note: "전원에 연결해 쓰는 PC이거나 배터리 정보를 읽을 수 없습니다." });
  } else {
    const lvl = b.plugged ? "good" : L.battery;
    tile("#tile-batt", {
      value: b.percent, meterPct: b.percent, level: lvl,
      levelText: b.plugged ? "충전기 연결됨" : { good: "정상", warning: "낮음", critical: "부족" }[lvl],
      note: b.plugged ? "전원 연결됨" : `배터리 사용 중${b.secs_left ? ` · 약 ${fmtDur(b.secs_left)} 남음` : ""}`,
    });
  }
}

// ───────────────────────────────────────────── UNO
function lcdLines(cmd, s) {
  if (!cmd || !cmd.startsWith("S,")) return ["", ""];
  const [, st, pctStr, ...rest] = cmd.split(",");
  const text = rest.join(",");
  const pct = Math.max(0, Math.min(100, parseInt(pctStr, 10) || 0));
  switch (st) {
    case "IDLE": return ["READY", text];
    case "WORK": {
      const filled = Math.floor((pct * 12) / 100);
      return [text || "WORKING", "█".repeat(filled) + "_".repeat(12 - filled) + `${String(pct).padStart(3)}%`];
    }
    case "INPUT": return ["NEED YOUR INPUT", `WAITING ${mmss(s.alert_elapsed_sec)}`];
    case "DONE": return ["DONE!", text || "BTN/GESTURE=OK"];
    case "ERROR": return ["ERROR", text];
    case "SEEN": return [`SEEN - ${s.alert || "DONE"}`, text];
    default: return ["", ""];
  }
}

function renderUno(s) {
  const d = s.device || {};
  const card = $("#dev-uno");
  const pill = card.querySelector("[data-pill]");
  if (d.fake) setLevel(pill, "warning", "시험 모드 (UNO 없음)");
  else if (d.connected && d.ready) setLevel(pill, "good", "연결됨");
  else if (d.connected) setLevel(pill, "warning", "부팅 기다리는 중");
  else setLevel(pill, "critical", "연결 안 됨");

  const [l0, l1] = lcdLines(s.uno_command, s).map((l) => (l || "").slice(0, 16).padEnd(16, " "));
  $("#lcd-0").textContent = l0;
  $("#lcd-1").textContent = l1;
  const lcd = $("#uno-lcd");
  const on = d.connected || d.fake;
  lcd.toggleAttribute("data-off", !on);
  lcd.setAttribute("aria-label", on ? `LCD 화면 재현: 첫째 줄 ${l0.trim() || "빈 줄"}, 둘째 줄 ${l1.trim() || "빈 줄"}` : "LCD: 장치 연결 안 됨");

  const f = (k) => card.querySelector(`[data-f="${k}"]`);
  f("port").textContent = d.error && !d.connected ? `${d.port} · ${d.error}` : d.port || "—";
  f("lcd").textContent = d.fake ? "—" : d.lcd?.startsWith("LCD,") ? `찾음 (주소 ${d.lcd.slice(4)})`
    : d.lcd === "ERR,LCD_NOT_FOUND" ? "찾지 못함 — 배선(SCL A1, SDA A0) 확인" : "—";
  f("sent").textContent = d.last_sent_at ? `${rel(d.last_sent_at, s.server_time)} · ${d.last_sent}` : "—";
  f("btn").textContent = d.last_btn_at ? rel(d.last_btn_at, s.server_time) : "아직 없음";
  f("since").textContent = d.connected_since ? fmtDur(s.server_time - d.connected_since) : "—";
}

// ───────────────────────────────────────────── 웹캠
function renderCam(g) {
  const card = $("#dev-cam");
  const pill = card.querySelector("[data-pill]");
  const map = {
    loading: ["unknown", "모델 불러오는 중"],
    idle: ["good", "대기 · 카메라 꺼짐"],
    watching: ["good", "ok 제스처 찾는 중"],
    preview: ["good", `미리보기 ${g.preview_left_sec || 0}초 남음`],
    disabled: ["critical", "제스처 기능 꺼짐"],
    camera_error: ["critical", "카메라 오류"],
    off: ["unknown", "제스처 기능 꺼짐 (--no-gesture)"],
  };
  let [lvl, txt] = map[g.status] || ["unknown", g.status];
  if (!access.local) { lvl = "unknown"; txt = "PC에서만 볼 수 있음"; }
  setLevel(pill, lvl, txt);
  $("#cam-preview-btn").hidden = !access.local;

  const off = $("#cam-off");
  if (g.camera_on && !paused && access.local) { startCam(); }
  else {
    stopCam();
    off.replaceChildren();
    const strong = document.createTextNode(g.status === "disabled" || g.status === "camera_error" ? txt : "카메라 꺼짐");
    const br = document.createElement("br");
    const small = document.createElement("span");
    small.className = "small";
    small.textContent = !access.local ? "개인정보 보호를 위해 웹캠 화면은 PC에서만 보입니다"
      : g.detail || (paused ? "자동 갱신을 멈춰 화면을 숨겼습니다" : "알림이 울릴 때만 켜집니다");
    off.append(strong, br, small);
  }

  const l = g.last;
  $("#cam-result").textContent = l ? `${l.name === g.target ? `${l.name} (확인 제스처)` : l.name} · ${Math.round(l.prob * 100)}%` : "—";
  const hold = g.hold_sec || 1;
  const held = l ? Math.min(l.held, hold) : 0;
  $("#cam-hold-fill").style.width = `${(held / hold) * 100}%`;
  const hb = $("#cam-hold");
  hb.setAttribute("aria-valuemax", String(hold));
  hb.setAttribute("aria-valuenow", held.toFixed(1));
  hb.setAttribute("aria-valuetext", `${held.toFixed(1)}초 / ${hold}초`);
  $("#cam-hold-text").textContent = `${held.toFixed(1)} / ${hold.toFixed(1)}초`;
  $("#cam-last").textContent = g.last_confirm_at ? rel(g.last_confirm_at, last.server_time) : "아직 없음";

  const btn = $("#cam-preview-btn");
  btn.disabled = ["loading", "disabled", "off"].includes(g.status);
  btn.textContent = g.status === "preview" ? "미리보기 끄기" : "카메라 미리보기 30초";
  btn.dataset.mode = g.status === "preview" ? "stop" : "start";
}

function startCam() {
  if (camTimer) return;
  const img = $("#cam-img");
  const tick = async () => {
    try {
      const res = await fetch(`/api/camera.jpg?t=${Date.now()}`, { cache: "no-store" });
      if (res.status === 200) {
        const url = URL.createObjectURL(await res.blob());
        const old = img.src;
        img.src = url;
        img.alt = "웹캠 화면 (거울 모드, 저장하지 않음)";
        img.hidden = false;
        $("#cam-off").hidden = true;
        if (old.startsWith("blob:")) URL.revokeObjectURL(old);
      }
    } catch (e) { /* 다음 차례에 다시 */ }
  };
  tick();
  camTimer = setInterval(tick, 250);
}

function stopCam() {
  clearInterval(camTimer);
  camTimer = null;
  const img = $("#cam-img");
  if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
  img.removeAttribute("src");
  img.hidden = true;
  $("#cam-off").hidden = false;
}

$("#cam-preview-btn").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const msg = $("#cam-preview-msg");
  const stop = btn.dataset.mode === "stop";
  msg.textContent = "요청 보내는 중…";
  try {
    const res = await fetch("/api/camera/preview", {
      method: stop ? "DELETE" : "POST",
      headers: { "Content-Type": "application/json" },
      body: stop ? undefined : JSON.stringify({ seconds: 30 }),
    });
    const j = await res.json();
    msg.textContent = j.ok ? (stop ? "미리보기를 껐습니다." : "미리보기를 켰습니다. 카메라 위치를 맞춰 보세요.") : `실패: ${j.error}`;
  } catch (err) {
    msg.textContent = "bridge에 연결할 수 없습니다.";
  }
});

// ───────────────────────────────────────────── ESP32-S3
function renderEsp(e) {
  const card = $("#dev-esp");
  const pill = card.querySelector("[data-pill]");
  const f = (k) => card.querySelector(`[data-f="${k}"]`);
  const d = e?.data;
  if (!e || e.state === "never") setLevel(pill, "unknown", "연결된 적 없음");
  else if (e.state === "online") setLevel(pill, "good", "연결됨");
  else setLevel(pill, "critical", `끊김 · ${fmtDur(e.last_seen_sec)} 전 마지막 수신`);
  $("#esp-sim").hidden = !d?.simulated;

  f("temp").textContent = d?.chip_temp_c != null ? `${d.chip_temp_c}°C (칩 내부 온도, 주변 온도 아님)` : "—";
  f("rssi").textContent = d?.rssi_dbm != null ? `${d.rssi_dbm} dBm · ${e.rssi_quality}` : "—";
  f("seen").textContent = e?.last_seen_sec != null ? `${fmtDur(e.last_seen_sec)} 전 (총 ${e.count}회)` : "—";
  f("interval").textContent = e?.avg_interval_sec != null ? `${e.avg_interval_sec}초` : "—";
  f("ip").textContent = d ? `${d.ip || "—"} · ${d.fw || "—"}` : "—";
  const pf = f("phone");
  pf.replaceChildren();
  if (d?.phone_url) {
    const a = document.createElement("a");
    a.href = d.phone_url; a.textContent = d.phone_url; a.rel = "noopener";
    pf.append(a);
  } else pf.textContent = "—";
  f("ntfy").textContent = !d ? "—" : d.ntfy
    ? (d.push_ok === false ? "ntfy 설정됨 · 마지막 전송 실패 (ESP32 인터넷 확인)" : d.push_ok ? `ntfy 설정됨 · ${fmtDur(d.push_age_s)} 전 전송 성공` : "ntfy 설정됨 · 아직 보낸 알림 없음")
    : "꺼짐 (휴대폰 페이지가 열려 있을 때만 알림)";
  f("found").textContent = !d ? "—" : d.found_by === "beacon" ? "자동 찾기 (UDP 신호)" : d.found_by === "config" ? "설정한 주소" : (d.found_by || "—");
  f("uptime").textContent = d?.uptime_s != null ? fmtDur(d.uptime_s) : "—";
  $("#esp-note").textContent = e?.state === "never"
    ? "ESP32-S3를 켜면 같은 Wi-Fi에서 이 PC를 자동으로 찾아 연결합니다. 설정 방법: esp32/notifier_remote/README.md"
    : e?.state === "offline" ? "ESP32-S3의 전원·Wi-Fi를 확인하세요. 시리얼 모니터에 원인이 표시됩니다."
    : "휴대폰 페이지에서 상태 확인과 부저 끄기를 할 수 있습니다. 보드의 BOOT 버튼으로도 끌 수 있습니다.";
}

// ───────────────────────────────────────────── 부저 끄기 (대시보드 버튼)
$("#ack-btn").addEventListener("click", async () => {
  const msg = $("#ack-msg");
  msg.textContent = "부저 끄는 중…";
  try {
    const res = await fetch("/api/ack", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method: "dashboard" }) });
    const j = await res.json();
    msg.textContent = !res.ok ? `실패: ${j.error || res.status}` : j.acked ? "부저를 껐습니다." : "이미 꺼져 있습니다.";
  } catch (e) {
    msg.textContent = "bridge에 연결할 수 없습니다.";
  }
});

// ───────────────────────────────────────────── 같은 Wi-Fi에서 보기
function renderAccess() {
  const card = $("#dev-remote");
  const pill = card.querySelector("[data-pill]");
  $("#where-tag").textContent = access.local ? "이 PC" : "원격 접속";
  $("#remote-local").hidden = !(access.local && access.lan_enabled);
  $("#remote-remote").hidden = access.local;
  $("#remote-off").hidden = !(access.local && !access.lan_enabled);
  if (!access.lan_enabled && access.local) { setLevel(pill, "unknown", "꺼짐"); return; }
  setLevel(pill, "good", access.local ? "공개 중 · 토큰 필요" : "원격으로 보는 중");
  if (!access.local) return;
  $("#remote-token").textContent = access.token || "—";
  const ul = $("#remote-urls");
  const urls = access.urls || [];
  ul.replaceChildren(...urls.map((u) => {
    const li = document.createElement("li");
    const code = document.createElement("code");
    code.textContent = u;
    const b = document.createElement("button");
    b.type = "button"; b.className = "btn btn--ghost"; b.textContent = "주소 복사";
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(u); b.textContent = "복사됨"; }
      catch (e) { b.textContent = "복사 실패 · 직접 선택"; }
      setTimeout(() => { b.textContent = "주소 복사"; }, 2000);
    });
    li.append(code, b);
    return li;
  }));
  if (!urls.length) {
    const li = document.createElement("li");
    li.textContent = "이 PC의 Wi-Fi 주소를 찾지 못했습니다. 네트워크 연결을 확인하세요.";
    ul.append(li);
  }
}
