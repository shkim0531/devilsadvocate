"use strict";

// ---------- 공통 ----------
const $ = (sel) => document.querySelector(sel);
const SETTINGS_KEY = "da-settings";
const TICK_MS = 1500;

const store = {
  load() {
    try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}"); } catch { return {}; }
  },
  save(value) {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(value)); } catch { /* 저장 못 해도 동작에는 지장 없음 */ }
  },
};

async function api(path, options = {}) {
  const init = { method: options.method || "GET", headers: {} };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, init);
  const type = res.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    let message = typeof data === "string" ? data : data.detail;
    if (Array.isArray(message)) message = "입력값을 확인하세요.";
    throw new Error(message || `요청 실패 (${res.status})`);
  }
  return data;
}

function readSettings() {
  return {
    intensity: document.querySelector('input[name="intensity"]:checked').value,
    target_mode: document.querySelector('input[name="target"]:checked').value,
    company_context: $("#company-context").value,
    tts: $("#tts").checked,
  };
}

function applySettings(saved) {
  if (saved.intensity) {
    const el = document.querySelector(`input[name="intensity"][value="${saved.intensity}"]`);
    if (el) el.checked = true;
  }
  if (saved.target_mode) {
    const el = document.querySelector(`input[name="target"][value="${saved.target_mode}"]`);
    if (el) el.checked = true;
  }
  if (typeof saved.company_context === "string") $("#company-context").value = saved.company_context;
  $("#tts").checked = Boolean(saved.tts);
}

function sessionSettings() {
  const { intensity, target_mode, company_context } = readSettings();
  return { intensity, target_mode, company_context };
}

function updateTargetHint() {
  const mode = readSettings().target_mode;
  $("#target-hint").textContent = mode === "auto"
    ? "결정·지시성 발언을 알아서 골라 반론합니다."
    : "'대표 발언 중' 버튼을 누른 동안 나온 발언에만 반론합니다.";
}

function download(filename, text) {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

function setStatus(el, text, kind = "") {
  el.textContent = text;
  el.className = `live-status ${kind}`.trim();
}

// ---------- 반론 카드 ----------
function renderCard(card, { label, fresh = false } = {}) {
  const node = $("#card-template").content.firstElementChild.cloneNode(true);
  if (fresh) node.classList.add("fresh");
  node.querySelector(".badge").textContent = label || "반론";
  node.querySelector(".severity").textContent = "●".repeat(card.severity) + "○".repeat(5 - card.severity);
  node.querySelector(".severity").title = `심각도 ${card.severity}/5`;
  node.querySelector(".decision").textContent = card.decision;
  node.querySelector(".steelman").textContent = card.steelman;
  node.querySelector(".weakest-text").textContent = card.weakest_assumption;
  node.querySelector(".question-text").textContent = card.question_now;
  node.querySelector(".concede-text").textContent = card.concede_if;
  const points = node.querySelector(".points");
  for (const cp of card.counterpoints) {
    const li = document.createElement("li");
    const cat = document.createElement("span");
    cat.className = "cat";
    cat.textContent = cp.category;
    li.append(cat, document.createTextNode(cp.point));
    points.append(li);
  }
  const alts = node.querySelector(".alternatives");
  for (const alt of card.alternatives) {
    const li = document.createElement("li");
    li.textContent = alt;
    alts.append(li);
  }
  if (!card.alternatives.length) alts.closest(".block").hidden = true;
  return node;
}

function speak(card) {
  if (!readSettings().tts || !("speechSynthesis" in window)) return;
  const text = `반론입니다. 가장 약한 가정. ${card.weakest_assumption} 지금 던질 질문. ${card.question_now}`;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ko-KR";
  u.rate = 1.05;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

// ---------- 실시간 회의 ----------
const live = {
  sessionId: null,
  recognition: null,
  listening: false,
  ceoActive: false,
  tickTimer: null,
  ticking: false,
  cardCount: 0,
  note: "",
};

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

async function ensureSession() {
  if (live.sessionId) return live.sessionId;
  const res = await api("/api/sessions", { method: "POST", body: sessionSettings() });
  live.sessionId = res.id;
  $("#btn-now").disabled = false;
  $("#btn-export").disabled = false;
  $("#btn-ceo").disabled = false;
  scheduleTick();
  return live.sessionId;
}

async function pushSettings() {
  store.save(readSettings());
  updateTargetHint();
  if (!live.sessionId) return;
  try {
    await api(`/api/sessions/${live.sessionId}/settings`, { method: "PUT", body: sessionSettings() });
  } catch (err) {
    setStatus($("#live-status"), err.message, "error");
  }
}

function appendTranscript(text, isCeo) {
  const li = document.createElement("li");
  li.textContent = text;
  if (isCeo) li.classList.add("ceo");
  const list = $("#transcript");
  list.append(li);
  list.scrollTop = list.scrollHeight;
}

async function addUtterance(text, isCeo) {
  text = text.trim();
  if (!text) return;
  appendTranscript(text, isCeo);
  if ($("#live-status").classList.contains("error")) setStatus($("#live-status"), idleStatus());
  try {
    const id = await ensureSession();
    await api(`/api/sessions/${id}/utterances`, { method: "POST", body: { text, is_ceo: isCeo } });
  } catch (err) {
    setStatus($("#live-status"), err.message, "error");
  }
}

function showLiveCard(card, forced) {
  const box = $("#cards");
  box.querySelector(".empty")?.remove();
  live.cardCount += 1;
  const time = new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  const node = renderCard(card, { label: forced ? `#${live.cardCount} 요청` : `#${live.cardCount}`, fresh: true });
  node.querySelector(".when").textContent = time;
  box.prepend(node);
  speak(card);
}

function idleStatus() {
  return live.listening ? "듣는 중" : "대기 중";
}

function handleLiveResult(res) {
  if (res.status === "rebutted") {
    live.note = "";
    showLiveCard(res.card, res.forced);
    setStatus($("#live-status"), idleStatus());
  } else if (res.status === "skipped") {
    live.note = `반론 보류: ${res.reason || "결정이 아닌 발언"}`;
    setStatus($("#live-status"), `${idleStatus()} · ${live.note}`);
  } else if (res.status === "busy") {
    setStatus($("#live-status"), "반론 작성 중...", "busy");
  }
}

function scheduleTick() {
  clearTimeout(live.tickTimer);
  live.tickTimer = setTimeout(tick, TICK_MS);
}

async function tick() {
  if (!live.sessionId || live.ticking) return scheduleTick();
  live.ticking = true;
  const slow = setTimeout(() => setStatus($("#live-status"), "반론 작성 중...", "busy"), 400);
  try {
    const res = await api(`/api/sessions/${live.sessionId}/tick`, { method: "POST" });
    clearTimeout(slow);
    if (res.status === "waiting") {
      if (!$("#live-status").classList.contains("error")) {
        const cool = res.cooldown > 0 ? ` · 다음 반론까지 ${Math.ceil(res.cooldown)}초` : "";
        const note = live.note ? ` · ${live.note}` : "";
        setStatus($("#live-status"), idleStatus() + cool + note);
      }
    } else {
      handleLiveResult(res);
    }
  } catch (err) {
    clearTimeout(slow);
    setStatus($("#live-status"), err.message, "error");
  } finally {
    live.ticking = false;
    scheduleTick();
  }
}

async function rebutNow() {
  const btn = $("#btn-now");
  btn.disabled = true;
  setStatus($("#live-status"), "반론 작성 중...", "busy");
  try {
    const id = await ensureSession();
    handleLiveResult(await api(`/api/sessions/${id}/rebut-now`, { method: "POST" }));
  } catch (err) {
    setStatus($("#live-status"), err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function startRecognition() {
  const rec = new SpeechRecognition();
  rec.lang = "ko-KR";
  rec.continuous = true;
  rec.interimResults = true;
  rec.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) addUtterance(result[0].transcript, live.ceoActive);
      else interim += result[0].transcript;
    }
    $("#interim").textContent = interim;
  };
  rec.onerror = (event) => {
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      setStatus($("#live-status"), "마이크 권한이 없습니다. 주소창의 자물쇠 아이콘에서 마이크를 허용하세요.", "error");
      stopListening();
    } else if (event.error === "network") {
      setStatus($("#live-status"), "음성 인식 서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요.", "error");
    }
  };
  // Chrome은 침묵이 길면 인식을 멈추므로 회의 중에는 다시 시작한다.
  rec.onend = () => {
    if (live.listening) {
      try { rec.start(); } catch { /* 이미 시작됨 */ }
    }
  };
  rec.start();
  live.recognition = rec;
}

async function startListening() {
  try {
    await ensureSession();
  } catch (err) {
    setStatus($("#live-status"), err.message, "error");
    return;
  }
  live.listening = true;
  startRecognition();
  const btn = $("#btn-mic");
  btn.textContent = "⏸ 회의 일시 정지";
  btn.classList.add("recording");
  setStatus($("#live-status"), "듣는 중");
}

function stopListening() {
  live.listening = false;
  live.recognition?.stop();
  live.recognition = null;
  $("#interim").textContent = "";
  const btn = $("#btn-mic");
  btn.textContent = "🎙 회의 재개";
  btn.classList.remove("recording");
  if (!$("#live-status").classList.contains("error")) setStatus($("#live-status"), idleStatus());
}

function toggleCeo(force) {
  live.ceoActive = typeof force === "boolean" ? force : !live.ceoActive;
  $("#btn-ceo").setAttribute("aria-pressed", String(live.ceoActive));
}

async function exportSession() {
  if (!live.sessionId) return;
  try {
    const md = await api(`/api/sessions/${live.sessionId}/export`);
    download(`회의기록-${stamp()}.md`, md);
  } catch (err) {
    setStatus($("#live-status"), err.message, "error");
  }
}

// ---------- 회의록 분석 ----------
const analysis = { filename: null, markdown: "" };

function readFileText(file) {
  return file.arrayBuffer().then((buf) => {
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(buf);
    } catch {
      return new TextDecoder("euc-kr").decode(buf); // 윈도우 메모장(ANSI) 저장 파일
    }
  });
}

let parseTimer = null;
function refreshSpeakers() {
  clearTimeout(parseTimer);
  parseTimer = setTimeout(async () => {
    const content = $("#transcript-input").value;
    const select = $("#ceo-speaker");
    const previous = select.value;
    select.replaceChildren(new Option("자동 판단", ""));
    if (!content.trim()) return;
    try {
      const res = await api("/api/parse", { method: "POST", body: { content, filename: analysis.filename } });
      for (const name of res.speakers) select.append(new Option(name, name));
      const guess = res.speakers.find((s) => s.includes("대표"));
      select.value = res.speakers.includes(previous) ? previous : guess || "";
      $("#file-name").textContent = `${analysis.filename || "붙여 넣은 회의록"} · 발언 ${res.count}개`;
    } catch (err) {
      $("#file-name").textContent = err.message;
    }
  }, 300);
}

async function loadFile(file) {
  if (!file) return;
  analysis.filename = file.name;
  $("#transcript-input").value = await readFileText(file);
  refreshSpeakers();
}

async function loadSample() {
  try {
    $("#transcript-input").value = await api("/api/sample");
    analysis.filename = "예시_주간경영회의.txt";
    refreshSpeakers();
  } catch (err) {
    setStatus($("#analyze-status"), err.message, "error");
  }
}

async function analyze() {
  const content = $("#transcript-input").value;
  if (!content.trim()) {
    setStatus($("#analyze-status"), "회의록을 먼저 넣어 주세요.", "error");
    return;
  }
  const btn = $("#btn-analyze");
  btn.disabled = true;
  setStatus($("#analyze-status"), "반론 리포트 작성 중... (1~2분 걸릴 수 있습니다)", "busy");
  try {
    const { intensity, company_context } = readSettings();
    const res = await api("/api/analyze", {
      method: "POST",
      body: {
        content,
        filename: analysis.filename,
        ceo_speaker: $("#ceo-speaker").value || null,
        intensity,
        company_context,
      },
    });
    showReport(res.report, res.markdown);
    setStatus($("#analyze-status"), `완료 · 반론 ${res.report.cards.length}건`);
  } catch (err) {
    setStatus($("#analyze-status"), err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

function showReport(report, markdown) {
  analysis.markdown = markdown;
  $("#report-summary").textContent = report.meeting_summary;
  $("#report-overall").textContent = report.overall_assessment;
  $("#report-cards-title").textContent = `반론 (${report.cards.length}건)`;
  const box = $("#report-cards");
  box.replaceChildren();
  if (!report.cards.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "반론할 결정이 없었습니다.";
    box.append(p);
  }
  report.cards.forEach((card, i) => box.append(renderCard(card, { label: `#${i + 1}` })));
  $("#report").hidden = false;
  $("#report").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- 탭, 초기화 ----------
function switchTab(name) {
  for (const tab of document.querySelectorAll(".tab")) {
    const active = tab.dataset.tab === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  $("#tab-live").hidden = name !== "live";
  $("#tab-analyze").hidden = name !== "analyze";
}

async function checkServer() {
  const el = $("#server-status");
  try {
    const s = await api("/api/status");
    if (s.fake) {
      el.textContent = "가짜 응답 모드 (Claude 호출 안 함)";
    } else if (!s.ready) {
      el.textContent = "⚠️ API 키 없음 — .env를 확인하세요";
      el.classList.add("bad");
    } else {
      el.textContent = `모델: ${s.model}`;
    }
  } catch {
    el.textContent = "⚠️ 서버에 연결하지 못했습니다";
    el.classList.add("bad");
  }
}

function init() {
  applySettings(store.load());
  updateTargetHint();
  checkServer();

  for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  for (const input of document.querySelectorAll('#settings input[type="radio"]')) input.addEventListener("change", pushSettings);
  $("#tts").addEventListener("change", () => store.save(readSettings()));
  let ctxTimer = null;
  $("#company-context").addEventListener("input", () => {
    clearTimeout(ctxTimer);
    ctxTimer = setTimeout(pushSettings, 600);
  });

  if (!SpeechRecognition) {
    $("#speech-warning").hidden = false;
    $("#btn-mic").disabled = true;
  }
  $("#btn-mic").addEventListener("click", () => (live.listening ? stopListening() : startListening()));
  $("#btn-ceo").addEventListener("click", () => toggleCeo());
  $("#btn-now").addEventListener("click", rebutNow);
  $("#btn-export").addEventListener("click", exportSession);
  $("#manual-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("#manual-text");
    addUtterance(input.value, $("#manual-ceo").checked || live.ceoActive);
    input.value = "";
  });

  $("#file-input").addEventListener("change", (e) => loadFile(e.target.files[0]));
  $("#btn-sample").addEventListener("click", loadSample);
  $("#transcript-input").addEventListener("input", refreshSpeakers);
  $("#btn-analyze").addEventListener("click", analyze);
  $("#btn-save-md").addEventListener("click", () => download(`반론리포트-${stamp()}.md`, analysis.markdown));
  $("#btn-print").addEventListener("click", () => window.print());
  // 인쇄할 때는 접힌 '최강 버전'도 펼쳐서 보이게 한다.
  window.addEventListener("beforeprint", () => {
    for (const d of document.querySelectorAll("#report details")) d.open = true;
  });
}

init();
