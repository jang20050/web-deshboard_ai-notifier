// bridge WebSocket 연결: 끊기면 1→2→4…최대 10초 간격으로 다시 연결
export function connect({ onMessage, onStatus, token }) {
  let ws = null;
  let delay = 1000;
  let timer = null;

  const open = () => {
    onStatus("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    try {
      const q = token ? `?token=${encodeURIComponent(token)}` : "";
      ws = new WebSocket(`${proto}://${location.host}/ws${q}`);
    } catch (e) {
      schedule();
      return;
    }
    ws.addEventListener("open", () => { delay = 1000; onStatus("open"); });
    ws.addEventListener("message", (ev) => {
      try { onMessage(JSON.parse(ev.data)); } catch (e) { console.warn("bad message", e); }
    });
    ws.addEventListener("close", () => { onStatus("closed"); schedule(); });
    ws.addEventListener("error", () => { try { ws.close(); } catch (e) {} });
  };

  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(open, delay);
    delay = Math.min(delay * 2, 10000);
  };

  open();
}

export async function getJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}
