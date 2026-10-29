// 휴대폰용 페이지 (ESP32-S3가 직접 제공). 외부 파일·인터넷 없이 동작.
// WCAG 2.2: 상태는 아이콘 모양+글자, 큰 버튼(56px), 조작 결과 안내(aria-live), 다크 모드, 확대 가능
#pragma once
#include <Arduino.h>

static const char PHONE_PAGE[] PROGMEM = R"HTML(<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1a1a19">
<title>AI 작업 알림</title>
<style>
:root{color-scheme:light dark;--bg:#f9f9f7;--card:#fcfcfb;--t:#0b0b0b;--t2:#52514e;--line:rgba(11,11,11,.12);--track:#cde2fb;
--work:#2a78d6;--input:#fab219;--done:#0ca30c;--seen:#898781;--bad:#d03b3b;--focus:#1c5cab}
@media (prefers-color-scheme:dark){:root{--bg:#0d0d0d;--card:#1a1a19;--t:#f0efec;--t2:#c3c2b7;--line:rgba(255,255,255,.14);--track:#1f3550;--work:#3987e5;--focus:#86b6ef}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font:16px/1.5 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif}
main{max-width:480px;margin:0 auto;padding:16px;display:grid;gap:14px}
h1{font-size:19px;margin:0}header{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.pill{display:inline-flex;gap:6px;align-items:center;font-size:14px;font-weight:600;padding:4px 10px;border-radius:999px;border:1px solid var(--line)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--seen)}.ok .dot{background:var(--done)}.bad .dot{background:var(--bad)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;display:grid;gap:12px;border-left:7px solid var(--c,var(--seen))}
[data-s=WORK]{--c:var(--work)}[data-s=INPUT]{--c:var(--input)}[data-s=DONE]{--c:var(--done)}[data-s=ERROR]{--c:var(--bad)}
.state{display:flex;gap:12px;align-items:center}.ico{width:40px;height:40px;flex:none;color:var(--c,var(--seen))}
.label{font-size:24px;font-weight:750;margin:0;line-height:1.2}.sub{color:var(--t2);margin:0}
.pct{font-size:56px;font-weight:700;line-height:1;margin:0}.pct small{font-size:24px;color:var(--t2)}
.bar{height:14px;border-radius:999px;background:var(--track);overflow:hidden}.fill{height:100%;width:0;background:var(--c,var(--work));border-radius:999px;transition:width .5s}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 14px}dt{color:var(--t2)}dd{margin:0;font-weight:600;overflow-wrap:anywhere}
button{font:inherit;min-height:56px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--t);font-weight:700;font-size:18px;padding:10px 16px;cursor:pointer}
#ack{background:var(--input);color:#0b0b0b;border-color:transparent}#ack:disabled{background:var(--card);color:var(--t2);border-color:var(--line);cursor:not-allowed}
#snd[aria-pressed=true]{background:var(--work);color:#fff;border-color:transparent}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.msg{min-height:1.5em;margin:0;font-weight:600}.note{font-size:14px;color:var(--t2);margin:0}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style></head><body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
<symbol id="i-WORK" viewBox="0 0 24 24"><path d="M12 3a9 9 0 1 0 9 9M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></symbol>
<symbol id="i-INPUT" viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/><path d="M12 13v.01M10 8.5a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></symbol>
<symbol id="i-DONE" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="m7.5 12.5 3 3 6-6.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></symbol>
<symbol id="i-SEEN" viewBox="0 0 24 24"><path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z" fill="none" stroke="currentColor" stroke-width="2.2"/><circle cx="12" cy="12" r="3" fill="currentColor"/></symbol>
<symbol id="i-IDLE" viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1.5" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1.5" fill="currentColor"/></symbol>
<symbol id="i-ERROR" viewBox="0 0 24 24"><path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M12 7.5v5.5M12 16.5v.01" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></symbol>
</svg>
<main>
<header><h1>AI 작업 알림</h1><p class="pill" id="conn"><span class="dot" aria-hidden="true"></span><span id="connt">연결 확인 중</span></p></header>
<section class="card" id="card" data-s="IDLE" aria-labelledby="label">
 <div class="state"><svg class="ico" aria-hidden="true"><use id="ico" href="#i-IDLE"/></svg>
  <div><p class="label" id="label">대기 중</p><p class="sub" id="sub">작업 없음</p></div></div>
 <p class="pct"><span id="pct">—</span><small>%</small></p>
 <div class="bar" role="progressbar" id="bar" aria-label="AI 작업 진행도(추정)" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="fill" id="fill"></div></div>
 <dl><dt id="tl">경과 시간</dt><dd id="time">—</dd><dt>프로젝트</dt><dd id="proj">—</dd></dl>
</section>
<button type="button" id="ack" disabled>부저 끄기</button>
<p class="msg" id="msg" role="status" aria-live="polite"></p>
<button type="button" id="snd" aria-pressed="false">이 휴대폰에서도 소리·진동 켜기</button>
<p class="note">이 페이지가 화면에 열려 있을 때만 휴대폰에서 소리가 납니다. 잠금 화면 알림은 ntfy 앱을 쓰세요 (<span id="ntfy">확인 중</span>).</p>
<section class="card" aria-label="장치 정보" style="border-left-width:1px"><dl>
 <dt>PC bridge</dt><dd id="br">—</dd><dt>Wi-Fi 신호</dt><dd id="rssi">—</dd><dt>칩 온도</dt><dd id="temp">—</dd><dt>펌웨어</dt><dd id="fw">—</dd></dl></section>
</main>
<script>
const $=s=>document.querySelector(s);
const ST={IDLE:"대기 중",WORK:"작업 중",INPUT:"답변 기다리는 중",DONE:"작업 완료",ERROR:"오류",SEEN:"확인함",UNKNOWN:"PC 연결 안 됨"};
const PH={READING:"파악",PLANNING:"정리",BUILDING:"만드는 중",REVIEWING:"최종 검토"};
const RS={permission:"권한 요청",AskUserQuestion:"질문",ExitPlanMode:"계획 승인"};
const ALERT=new Set(["INPUT","DONE","ERROR"]);
const mmss=s=>{s=Math.max(0,Math.floor(s||0));return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0")};
const dur=s=>{s=Math.round(s||0);return s<60?s+"초":Math.floor(s/60)+"분 "+String(s%60).padStart(2,"0")+"초"};
let lastSeq=null,sound=false,ctx=null,prevState=null;
function beep(kind){if(!sound||!ctx)return;const f=kind==="DONE"?[523,659,784]:[880,659,880,659];let t=ctx.currentTime;
 f.forEach(fr=>{const o=ctx.createOscillator(),g=ctx.createGain();o.frequency.value=fr;g.gain.setValueAtTime(.2,t);g.gain.exponentialRampToValueAtTime(.001,t+.22);o.connect(g).connect(ctx.destination);o.start(t);o.stop(t+.24);t+=.26});
 if(navigator.vibrate)navigator.vibrate(kind==="DONE"?[300,120,300]:[200,100,200,100,200]);}
$("#snd").onclick=()=>{sound=!sound;$("#snd").setAttribute("aria-pressed",sound);
 $("#snd").textContent=sound?"휴대폰 소리·진동 켜짐 (누르면 끄기)":"이 휴대폰에서도 소리·진동 켜기";
 if(sound){ctx=ctx||new (window.AudioContext||window.webkitAudioContext)();ctx.resume();beep("DONE")}};
$("#ack").onclick=async()=>{const m=$("#msg");m.textContent="부저 끄는 중…";$("#ack").disabled=true;
 try{const r=await fetch("/api/ack",{method:"POST",headers:{"Content-Type":"application/json"},body:'{"method":"phone"}'});const j=await r.json();
  m.textContent=j.ok?(j.acked?"부저를 껐습니다.":"이미 꺼져 있거나 알림이 없습니다."):"실패: "+(j.error||r.status)}catch(e){m.textContent="ESP32에 연결할 수 없습니다."}
 tick()};
function render(d){const a=d.ai||{},e=d.esp||{},s=e.bridge_ok?(a.state||"IDLE"):"UNKNOWN";
 $("#card").dataset.s=s;$("#ico").setAttribute("href","#i-"+(ST[s]&&s!=="UNKNOWN"?s:"IDLE"));
 $("#label").textContent=ST[s]||s;
 let sub="작업 없음";if(s==="WORK")sub=(PH[a.phase]||"")+" 단계";else if(s==="INPUT")sub=(RS[a.input_reason]||"답변 필요")+" · "+mmss(a.alert_elapsed)+" 경과";
 else if(s==="DONE")sub="결과를 확인하세요";else if(s==="SEEN")sub="알림 확인됨"+(a.last_ack?" ("+({gesture:"제스처",button:"버튼",phone:"휴대폰",esp32:"ESP32 버튼",dashboard:"대시보드",answered:"바로 답함"}[a.last_ack]||a.last_ack)+")":"");
 else if(s==="UNKNOWN")sub=e.bridge_err||"PC의 bridge를 찾는 중";
 $("#sub").textContent=sub;
 const show=s!=="IDLE"&&s!=="UNKNOWN",pc=(s==="DONE"||(s==="SEEN"&&a.alert==="DONE"))?100:(a.percent||0);
 $("#pct").textContent=show?pc:"—";$("#fill").style.width=(show?pc:0)+"%";$("#bar").setAttribute("aria-valuenow",show?pc:0);
 const fin=a.elapsed==null&&a.duration!=null&&show;$("#tl").textContent=fin?"걸린 시간":"경과 시간";
 $("#time").textContent=a.elapsed!=null?dur(a.elapsed):fin?dur(a.duration):"—";$("#proj").textContent=a.project||"—";
 const alert=ALERT.has(s);$("#ack").disabled=!alert;$("#ack").textContent=alert?"부저 끄기":"알림 없음";
 document.title=(alert?"[알림] ":"")+"AI 작업 알림 · "+(ST[s]||s);
 if(lastSeq!==null&&a.alert_seq>lastSeq&&ALERT.has(a.state))beep(a.state);if(a.alert_seq!=null)lastSeq=a.alert_seq;
 if(prevState&&prevState!==s)$("#msg").textContent="상태: "+(ST[s]||s);prevState=s;
 const c=$("#conn");c.className="pill "+(e.bridge_ok?"ok":"bad");$("#connt").textContent=e.bridge_ok?"PC 연결됨":"PC 연결 안 됨";
 $("#br").textContent=e.bridge?(e.bridge+" ("+(e.found_by==="beacon"?"자동 찾음":"설정값")+")"):"찾는 중";
 $("#rssi").textContent=e.rssi!=null?e.rssi+" dBm":"—";$("#temp").textContent=e.temp!=null?e.temp+"°C (칩 내부)":"—";
 $("#fw").textContent=(e.fw||"—")+" · "+(e.ip||"");
 $("#ntfy").textContent=e.ntfy?(e.push_ok===false?"설정됨, 마지막 전송 실패":"설정됨"):"설정 안 됨";}
async function tick(){try{const c=new AbortController(),t=setTimeout(()=>c.abort(),2500);
 const r=await fetch("/api/state",{cache:"no-store",signal:c.signal});clearTimeout(t);render(await r.json())}
 catch(e){$("#conn").className="pill bad";$("#connt").textContent="ESP32 연결 끊김"}}
tick();setInterval(tick,1000);
</script></body></html>)HTML";
