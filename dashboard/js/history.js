// 작업 기록: 오늘 요약 + 최근 작업 표
import { getJSON } from "./socket.js";
import { $, fmtDur } from "./util.js";

const RESULT_KO = { done: "완료", interrupted: "중단(새 요청)", ended: "세션 종료" };
const ALERT_KO = { INPUT: "답변 대기", DONE: "완료", ERROR: "오류" };
const METHOD_KO = { gesture: "ok 제스처", button: "빵판 버튼", answered: "Claude에서 답함", new_task: "새 작업",
  phone: "휴대폰", esp32: "ESP32 버튼", dashboard: "대시보드" };

let busy = false;

export async function refreshHistory() {
  if (busy) return;
  busy = true;
  try {
    const [stats, tasks] = await Promise.all([getJSON("/api/stats"), getJSON("/api/tasks?limit=20")]);
    renderStats(stats);
    renderTasks(tasks);
  } catch (e) {
    /* bridge 연결이 돌아오면 다시 불러옴 */
  } finally {
    busy = false;
  }
}

function renderStats(s) {
  $("#st-tasks").textContent = s.tasks;
  $("#st-longest").textContent = s.tasks ? `가장 긴 작업 ${fmtDur(s.longest_sec)}` : "오늘 완료된 작업이 없습니다";
  $("#st-work").textContent = s.tasks ? fmtDur(s.work_sec) : "—";
  $("#st-alerts").textContent = s.alerts;
  $("#st-acked").textContent = s.alerts ? `그중 확인됨 ${s.acked}회` : "알림 없음";

  const by = s.by_method || {};
  const human = ["gesture", "button", "phone", "esp32", "dashboard"].filter((k) => by[k]);
  let total = 0, n = 0;
  human.forEach((k) => { total += by[k].avg_delay_sec * by[k].count; n += by[k].count; });
  $("#st-delay").textContent = n ? `${(total / n).toFixed(1)}초` : "—";
  const parts = Object.entries(by).map(([k, v]) => `${METHOD_KO[k] || k} ${v.count}회`);
  $("#st-methods").textContent = n ? `직접 끈 알림 기준 · ${parts.join(", ")}` : (parts.length ? parts.join(", ") : "직접 끈 알림 기록이 없습니다");
}

function td(text, cls) {
  const c = document.createElement("td");
  c.textContent = text;
  if (cls) c.className = cls;
  return c;
}

function renderTasks(rows) {
  const tb = $("#tasks-table tbody");
  $("#tasks-empty").hidden = rows.length > 0;
  $("#tasks-table").hidden = rows.length === 0;
  tb.replaceChildren(...rows.map((r) => {
    const tr = document.createElement("tr");
    const start = new Date(r.started * 1000);
    tr.append(
      td(start.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })),
      td(r.project || "—"),
      td(r.duration_sec != null ? fmtDur(r.duration_sec) : "진행 중", "num"),
      td(r.result ? RESULT_KO[r.result] || r.result : "진행 중"),
      td(r.alert_kind ? ALERT_KO[r.alert_kind] || r.alert_kind : "없음"),
      td(r.ack_method ? METHOD_KO[r.ack_method] || r.ack_method : r.alert_kind ? "확인 전" : "—"),
      td(r.ack_delay_sec != null ? `${r.ack_delay_sec}초` : "—", "num"),
    );
    return tr;
  }));
}
