// 단일 시계열 선 그래프 (SVG). 외부 라이브러리 없음.
// - 선 2px, 영역 10% 채움, 끝점 표시와 현재값 라벨, 얇은 실선 격자
// - 마우스·키보드(←/→/Home/End)로 십자선과 툴팁, 같은 값을 표로 보기
// - 한 그래프에 한 가지 단위만 (축 2개 사용 안 함)
const NS = "http://www.w3.org/2000/svg";

function el(name, attrs = {}, parent) {
  const n = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

import { hhmm, hhmmss } from "./util.js";

export class LineChart {
  /**
   * @param {HTMLElement} root
   * @param {{name:string, unit:string, color:string, yMin:number, yMax:number,
   *          refs?:{value:number,label:string}[], windowSec?:number, empty?:string}} opts
   */
  constructor(root, opts) {
    this.root = root;
    this.o = { windowSec: 600, refs: [], ...opts };
    this.points = [];
    this.emptyMsg = opts.empty || "데이터를 기다리는 중입니다.";
    this.focusIdx = null;
    this.tooltip = document.getElementById("tooltip");

    this.plot = document.createElement("div");
    this.tools = document.createElement("div");
    this.tools.className = "chart__tools";
    this.summary = document.createElement("p");
    this.summary.className = "chart__summary";
    this.tableBtn = document.createElement("button");
    this.tableBtn.type = "button";
    this.tableBtn.className = "btn btn--ghost";
    this.tableBtn.textContent = "표로 보기";
    this.tableBtn.setAttribute("aria-expanded", "false");
    this.tableBox = document.createElement("div");
    this.tableBox.className = "chart__table table-wrap";
    this.tableBox.hidden = true;
    this.tableBox.id = `${root.id}-table`;
    this.tableBtn.setAttribute("aria-controls", this.tableBox.id);
    this.tableBtn.addEventListener("click", () => {
      const open = this.tableBox.hidden;
      this.tableBox.hidden = !open;
      this.tableBtn.setAttribute("aria-expanded", String(open));
      this.tableBtn.textContent = open ? "표 닫기" : "표로 보기";
      if (open) this.renderTable();
    });
    this.tools.append(this.summary, this.tableBtn);
    root.append(this.plot, this.tools, this.tableBox);

    new ResizeObserver(() => this.render()).observe(root);
  }

  setEmptyMessage(msg) { this.emptyMsg = msg; }

  setData(points) {
    this.points = points.filter((p) => p.v !== null && p.v !== undefined && !Number.isNaN(p.v));
    this.render();
    if (!this.tableBox.hidden) this.renderTable();
  }

  render() {
    const { name, unit, color, yMin, yMax, refs, windowSec } = this.o;
    const W = Math.max(this.root.clientWidth, 260);
    const H = 190;
    const m = { t: 12, r: 52, b: 26, l: 36 };
    const pw = W - m.l - m.r;
    const ph = H - m.t - m.b;
    const pts = this.points;
    // 다시 그려도 키보드 포커스·마우스 위치를 잃지 않게
    const hadFocus = this.plot.contains(document.activeElement);
    this.plot.replaceChildren();

    if (pts.length < 2) {
      const d = document.createElement("div");
      d.className = "chart__empty";
      d.textContent = this.emptyMsg;
      this.plot.append(d);
      this.summary.textContent = "";
      this.tableBtn.hidden = pts.length === 0;
      return;
    }
    this.tableBtn.hidden = false;

    const tEnd = pts[pts.length - 1].t;
    const tStart = tEnd - windowSec;
    const x = (t) => m.l + ((t - tStart) / windowSec) * pw;
    const y = (v) => m.t + ph - ((Math.min(Math.max(v, yMin), yMax) - yMin) / (yMax - yMin)) * ph;

    const vals = pts.map((p) => p.v);
    const last = pts[pts.length - 1];
    const min = Math.min(...vals), max = Math.max(...vals);
    const label = `${name}, 최근 ${Math.round(windowSec / 60)}분. 현재 ${last.v}${unit}, 최저 ${min}${unit}, 최고 ${max}${unit}. 화살표 키로 시점별 값을 볼 수 있습니다.`;

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label, tabindex: "0" });
    // 격자 (4칸)
    const g = el("g", { class: "grid" }, svg);
    for (let i = 0; i <= 4; i++) {
      const v = yMin + ((yMax - yMin) * i) / 4;
      el("line", { x1: m.l, x2: m.l + pw, y1: y(v), y2: y(v) }, g);
      const tx = el("text", { class: "axis", x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, svg);
      tx.textContent = Math.round(v);
    }
    // 시간 축: 처음·중간·끝
    [tStart, tStart + windowSec / 2, tEnd].forEach((t, i) => {
      const tx = el("text", { class: "axis", x: x(t), y: H - 6, "text-anchor": ["start", "middle", "end"][i] }, svg);
      tx.textContent = i === 2 ? "지금" : hhmm(t);
    });
    // 기준선 (주의·높음)
    const rg = el("g", { class: "ref" }, svg);
    refs.forEach((r) => {
      if (r.value <= yMin || r.value >= yMax) return;
      el("line", { x1: m.l, x2: m.l + pw, y1: y(r.value), y2: y(r.value) }, rg);
      const tx = el("text", { x: m.l + 4, y: y(r.value) - 4 }, rg);
      tx.textContent = r.label;
    });

    const visible = pts.filter((p) => p.t >= tStart);
    const d = visible.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    el("path", { class: "area", style: `fill:${color}`,
      d: `${d}L${x(visible[visible.length - 1].t).toFixed(1)},${y(yMin)}L${x(visible[0].t).toFixed(1)},${y(yMin)}Z` }, svg);
    el("path", { class: "line", style: `stroke:${color}`, d }, svg);
    el("circle", { class: "dot", cx: x(last.t), cy: y(last.v), r: 4.5, style: `fill:${color}` }, svg);
    const end = el("text", { class: "endlabel", x: x(last.t) + 8, y: y(last.v) + 4 }, svg);
    end.textContent = `${last.v}${unit}`;

    // 십자선 + 툴팁
    const cross = el("line", { class: "cross", y1: m.t, y2: m.t + ph, visibility: "hidden" }, svg);
    const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" }, svg);
    const show = (idx, clientX, clientY) => {
      const p = visible[idx];
      if (!p) return;
      this.focusIdx = idx;
      cross.setAttribute("x1", x(p.t)); cross.setAttribute("x2", x(p.t));
      cross.setAttribute("visibility", "visible");
      const tip = this.tooltip;
      tip.replaceChildren();
      const strong = document.createElement("strong");
      strong.textContent = `${p.v}${unit}`;
      const row = document.createElement("span");
      const key = document.createElement("span");
      key.className = "key"; key.style.background = color;
      row.append(key, document.createTextNode(`${name} · ${hhmmss(p.t)}`));
      tip.append(strong, row);
      tip.hidden = false;
      const r = svg.getBoundingClientRect();
      const px = clientX ?? r.left + (x(p.t) / W) * r.width;
      const py = clientY ?? r.top + (y(p.v) / H) * r.height;
      const tw = tip.offsetWidth;
      tip.style.left = `${Math.min(Math.max(8, px + 12), window.innerWidth - tw - 8)}px`;
      tip.style.top = `${Math.max(8, py - 56)}px`;
    };
    const hide = () => { cross.setAttribute("visibility", "hidden"); this.tooltip.hidden = true; };
    const nearest = (clientX) => {
      const r = svg.getBoundingClientRect();
      const t = tStart + (((clientX - r.left) / r.width) * W - m.l) / pw * windowSec;
      let best = 0, bd = Infinity;
      visible.forEach((p, i) => { const dd = Math.abs(p.t - t); if (dd < bd) { bd = dd; best = i; } });
      return best;
    };
    hit.addEventListener("pointermove", (e) => { this.hover = { x: e.clientX, y: e.clientY }; show(nearest(e.clientX), e.clientX, e.clientY); });
    hit.addEventListener("pointerleave", () => { this.hover = null; hide(); });
    svg.addEventListener("focus", () => show(this.focusIdx ?? visible.length - 1));
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (e) => {
      let i = this.focusIdx ?? visible.length - 1;
      if (e.key === "ArrowLeft") i = Math.max(0, i - 1);
      else if (e.key === "ArrowRight") i = Math.min(visible.length - 1, i + 1);
      else if (e.key === "Home") i = 0;
      else if (e.key === "End") i = visible.length - 1;
      else if (e.key === "Escape") { hide(); return; }
      else return;
      e.preventDefault();
      show(i);
    });
    this.plot.append(svg);
    if (hadFocus) svg.focus({ preventScroll: true });
    else if (this.hover) show(nearest(this.hover.x), this.hover.x, this.hover.y);
    this.summary.textContent = `현재 ${last.v}${unit} · 10분 최저 ${min}${unit} · 최고 ${max}${unit}`;
  }

  renderTable() {
    const { name, unit } = this.o;
    // 30초 간격으로 줄여서 표시 (최신순)
    const rows = [];
    let lastT = Infinity;
    for (let i = this.points.length - 1; i >= 0; i--) {
      const p = this.points[i];
      if (lastT - p.t >= 30) { rows.push(p); lastT = p.t; }
    }
    const table = document.createElement("table");
    table.className = "table";
    const cap = document.createElement("caption");
    cap.className = "sr-only";
    cap.textContent = `${name} 30초 간격 값, 최신순`;
    const thead = document.createElement("thead");
    const htr = document.createElement("tr");
    ["시각", `${name} (${unit})`].forEach((h, i) => {
      const th = document.createElement("th");
      th.scope = "col"; th.textContent = h; if (i) th.className = "num";
      htr.append(th);
    });
    thead.append(htr);
    const tb = document.createElement("tbody");
    rows.forEach((p) => {
      const tr = document.createElement("tr");
      const a = document.createElement("td"); a.textContent = hhmmss(p.t);
      const b = document.createElement("td"); b.className = "num"; b.textContent = p.v;
      tr.append(a, b); tb.append(tr);
    });
    table.append(cap, thead, tb);
    this.tableBox.replaceChildren(table);
  }
}
