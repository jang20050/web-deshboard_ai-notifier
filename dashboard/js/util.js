// 공통 도우미
export const $ = (sel) => document.querySelector(sel);

export const LEVEL_TEXT = { good: "정상", warning: "주의", critical: "높음", unknown: "측정 불가" };
const LEVEL_ICON = { good: "i-good", warning: "i-warning", serious: "i-warning", critical: "i-critical", unknown: "i-unknown" };

/** 상태 표시: 색 + 아이콘 모양 + 글자 (색만으로 전달하지 않음) */
export function setLevel(node, level, text) {
  node.dataset.level = level;
  node.querySelector("use").setAttribute("href", `#${LEVEL_ICON[level] || "i-unknown"}`);
  node.querySelector("span").textContent = text;
}

export function mmss(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function fmtDur(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}분 ${String(s % 60).padStart(2, "0")}초`;
  return `${Math.floor(m / 60)}시간 ${m % 60}분`;
}

export function rel(ts, now) {
  if (!ts) return "—";
  const d = Math.max(0, (now || Date.now() / 1000) - ts);
  if (d < 5) return "방금";
  return `${fmtDur(d)} 전`;
}

const p2 = (n) => String(n).padStart(2, "0");
export const hhmm = (ts) => { const d = new Date(ts * 1000); return `${p2(d.getHours())}:${p2(d.getMinutes())}`; };
export const hhmmss = (ts) => { if (!ts) return "—"; const d = new Date(ts * 1000); return `${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
