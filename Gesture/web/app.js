// 제스처 학습기: 웹캠 촬영 → 서버 저장 → 학습 → 실시간 테스트
const $ = (id) => document.getElementById(id);
const video = $("video");
const canvas = $("canvas");

const CAPTURE_WIDTH = 320; // 분류 모델은 224px 로 줄여 쓰므로 이 정도면 충분
const BURST_INTERVAL_MS = 200;
const TEST_INTERVAL_MS = 300;

let activeClass = null;
let burstTimer = null;
let testing = false;
let pollTimer = null;

// ---------- 카메라 ----------

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    $("cam-status").textContent = "카메라 연결됨 (화면은 거울 모드, 저장은 원본 방향)";
  } catch (e) {
    $("cam-status").textContent = `카메라를 열 수 없습니다: ${e.message}`;
  }
}

function grabJpeg() {
  if (!video.videoWidth) return Promise.resolve(null);
  const scale = CAPTURE_WIDTH / video.videoWidth;
  canvas.width = CAPTURE_WIDTH;
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
}

// ---------- API ----------

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

// ---------- 클래스 ----------

function renderClasses(classes) {
  const list = $("class-list");
  list.innerHTML = "";
  if (activeClass && !classes.some((c) => c.name === activeClass)) activeClass = null;
  if (!activeClass && classes.length) activeClass = classes[0].name;

  for (const c of classes) {
    const li = document.createElement("li");
    li.className = c.name === activeClass ? "active" : "";

    const pick = document.createElement("button");
    pick.type = "button";
    pick.className = "pick";
    pick.textContent = c.name;
    pick.setAttribute("aria-pressed", String(c.name === activeClass));
    pick.onclick = () => { activeClass = c.name; renderClasses(classes); };

    const count = document.createElement("span");
    count.className = "count";
    count.textContent = `${c.count}장`;

    const del = document.createElement("button");
    del.type = "button";
    del.className = "del ghost";
    del.textContent = "삭제";
    del.setAttribute("aria-label", `${c.name} 클래스와 사진 모두 삭제`);
    del.onclick = async () => {
      if (!confirm(`'${c.name}' 클래스와 사진 ${c.count}장을 모두 지울까요?`)) return;
      renderClasses((await api(`/api/classes/${c.name}`, { method: "DELETE" })).classes);
    };

    li.append(pick, count, del);
    list.append(li);
  }
  $("active-class").textContent = activeClass || "없음";
  for (const id of ["snap", "burst", "undo"]) $(id).disabled = !activeClass;
}

async function refreshClasses() {
  renderClasses((await api("/api/classes")).classes);
}

$("add-form").onsubmit = async (e) => {
  e.preventDefault();
  const name = $("new-class").value.trim();
  try {
    const { classes } = await api("/api/classes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    activeClass = name;
    $("new-class").value = "";
    renderClasses(classes);
  } catch (err) {
    alert(err.message);
  }
};

// ---------- 촬영 ----------

async function snap() {
  if (!activeClass) return;
  const blob = await grabJpeg();
  if (!blob) return;
  const flash = $("flash");
  flash.classList.add("on");
  requestAnimationFrame(() => requestAnimationFrame(() => flash.classList.remove("on")));
  try {
    await api(`/api/capture/${activeClass}`, {
      method: "POST",
      headers: { "Content-Type": "image/jpeg" },
      body: blob,
    });
    const countEl = [...document.querySelectorAll("#class-list li")]
      .find((li) => li.querySelector(".pick").textContent === activeClass)?.querySelector(".count");
    if (countEl) countEl.textContent = `${parseInt(countEl.textContent, 10) + 1}장`;
  } catch (err) {
    stopBurst();
    alert(err.message);
  }
}

function startBurst() {
  if (!activeClass || burstTimer) return;
  burstTimer = setInterval(snap, BURST_INTERVAL_MS);
  $("burst").setAttribute("aria-pressed", "true");
  $("burst").firstChild.textContent = "연속 촬영 정지 ";
}

function stopBurst() {
  if (!burstTimer) return;
  clearInterval(burstTimer);
  burstTimer = null;
  $("burst").setAttribute("aria-pressed", "false");
  $("burst").firstChild.textContent = "연속 촬영 시작 ";
  refreshClasses();
}

$("snap").onclick = snap;
$("burst").onclick = () => (burstTimer ? stopBurst() : startBurst());
$("undo").onclick = async () => {
  if (activeClass) renderClasses((await api(`/api/classes/${activeClass}/last`, { method: "DELETE" })).classes);
};

document.addEventListener("keydown", (e) => {
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); snap(); }
  if (e.code === "KeyB") { burstTimer ? stopBurst() : startBurst(); }
});

// ---------- 학습 ----------

function renderTrain(s) {
  const msg = $("train-msg");
  msg.textContent = s.error ? `${s.message}: ${s.error}` : s.message;
  msg.className = s.error ? "error" : (!s.running && s.finished_at ? "done" : "");
  $("train").disabled = s.running;
  $("train-progress").max = s.epochs || 1;
  $("train-progress").value = s.epoch || 0;

  const m = s.metrics || {};
  $("train-metrics").textContent = m.accuracy_top1 !== undefined
    ? `검증 정확도(top1): ${(m.accuracy_top1 * 100).toFixed(1)}%  ·  val loss: ${m.loss ?? "-"}`
    : "";

  const info = s.model;
  $("model-info").textContent = info
    ? `저장된 모델: models/gesture_cls.pt · 클래스 [${info.classes.join(", ")}] · ${info.base_model} · ${info.trained_at}`
    : "아직 저장된 모델이 없습니다.";
}

async function pollTraining() {
  const s = await api("/api/train/status");
  renderTrain(s);
  if (s.running) {
    pollTimer = setTimeout(pollTraining, 1500);
  } else {
    pollTimer = null;
  }
}

$("train").onclick = async () => {
  stopBurst();
  try {
    await api("/api/train", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        size: $("size").value,
        epochs: Number($("epochs").value),
        imgsz: Number($("imgsz").value),
      }),
    });
    if (!pollTimer) pollTraining();
  } catch (err) {
    alert(err.message);
  }
};

// ---------- 실시간 테스트 ----------

function renderProbs(result) {
  const list = $("probs");
  list.innerHTML = "";
  for (const r of result.all) {
    const li = document.createElement("li");
    const pct = (r.prob * 100).toFixed(1);
    li.innerHTML = `<span></span><div class="bar"><span style="width:${pct}%"></span></div><span class="pct">${pct}%</span>`;
    li.firstChild.textContent = r.name;
    list.append(li);
  }
  const label = $("live-label");
  label.hidden = false;
  label.textContent = `${result.top.name} ${(result.top.prob * 100).toFixed(0)}%`;
}

async function testLoop() {
  if (!testing) return;
  try {
    const blob = await grabJpeg();
    if (blob) {
      renderProbs(await api("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "image/jpeg" },
        body: blob,
      }));
    }
  } catch (err) {
    stopTest();
    alert(err.message);
    return;
  }
  setTimeout(testLoop, TEST_INTERVAL_MS);
}

function stopTest() {
  testing = false;
  $("test").setAttribute("aria-pressed", "false");
  $("test").textContent = "테스트 시작";
  $("live-label").hidden = true;
}

$("test").onclick = () => {
  if (testing) return stopTest();
  testing = true;
  $("test").setAttribute("aria-pressed", "true");
  $("test").textContent = "테스트 정지";
  testLoop();
};

// ---------- 시작 ----------

startCamera();
refreshClasses();
pollTraining();
