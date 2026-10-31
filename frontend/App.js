import { getSettings, saveSettings, LIMITS } from "./config.js";
import * as api from "./api.js";

/* ---------- Utilidades ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c != null) node.append(c.nodeType ? c : document.createTextNode(c));
  }
  return node;
}

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* cuota llena */ }
}

/* ---------- Estado ---------- */
const state = {
  messages: load("rag.chat", []),   // [{role, content, sufficient?, sources?, image?}]
  docs: load("rag.docs", []),       // [{id, name}] documentos ya indexados
  selectedDoc: load("rag.doc", ""),
  busy: false,
};

const SUGGESTIONS = [
  "¿Cada cuánto debo hacer el mantenimiento?",
  "Muéstrame el diagrama del lazo de control",
  "¿Qué clima hará mañana?",
];

const STAGE_LABEL = {
  parsing: "Leyendo páginas",
  chunking: "Dividiendo en secciones",
  embedding: "Generando embeddings",
  indexing: "Indexando",
};

/* ---------- Markdown seguro ---------- */
function renderMarkdown(text) {
  // La salida del LLM no es confiable: siempre se sanea antes de insertar HTML.
  if (!window.marked || !window.DOMPurify) {
    const p = el("p", { text });
    return p.outerHTML;
  }
  const html = window.marked.parse(text, { gfm: true, breaks: true });
  return window.DOMPurify.sanitize(html, { ADD_ATTR: ["target"] });
}

if (window.DOMPurify) {
  window.DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
}

/* ---------- Render del chat ---------- */
const messagesEl = $("#messages");

function renderAll() {
  messagesEl.replaceChildren();
  if (state.messages.length === 0) {
    messagesEl.append(renderWelcome());
    return;
  }
  state.messages.forEach((m) => messagesEl.append(renderMessage(m)));
  scrollToEnd();
}

function renderWelcome() {
  return el("div", { class: "welcome" },
    el("h2", { text: "¿Qué quieres saber de tus manuales?" }),
    el("p", { text: "Sube un PDF y pregunta en lenguaje natural. Cada respuesta indica de qué página salió." }),
    el("div", { class: "suggestions" },
      SUGGESTIONS.map((s) => el("button", { type: "button", text: s, onclick: () => send(s) }))),
  );
}

function renderMessage(m) {
  if (m.role === "user") {
    return el("div", { class: "msg user" }, el("div", { class: "bubble", text: m.content }));
  }

  if (m.role === "error") {
    return el("div", { class: "msg error", role: "alert" },
      el("div", { class: "bubble" },
        el("div", { text: m.content }),
        m.retry ? el("button", { class: "btn-ghost", type: "button", text: "Reintentar", onclick: () => retry(m) }) : null,
      ));
  }

  const body = el("div", { class: "md" });
  body.innerHTML = renderMarkdown(m.content);

  const bubble = el("div", { class: "bubble" }, body);
  if (m.sufficient === false) {
    bubble.append(el("div", { class: "notice" },
      el("span", { text: "Esta respuesta no se apoya en tus documentos: no se encontró información suficiente." })));
  }
  if (m.image) bubble.append(renderPlate(m.image));
  if (m.sources?.length) bubble.append(renderSources(m.sources));

  return el("div", { class: "msg assistant" }, bubble);
}

function renderPlate(img) {
  const url = api.resolveUrl(img.url);
  const alt = img.caption || `Imagen de la página ${img.page} de ${img.file}`;
  return el("figure", { class: "plate" },
    el("button", { class: "plate-view", type: "button", "aria-label": `Ampliar: ${alt}`, onclick: () => openLightbox(url, alt, img) },
      el("img", { src: url, alt, loading: "lazy" })),
    el("figcaption", { class: "plate-block" },
      img.caption ? el("div", { class: "plate-cap", text: img.caption }) : null,
      el("div", { class: "plate-file", text: img.file, title: img.file }),
      el("div", { class: "plate-page", text: `Página ${img.page}` }),
      el("div", { class: "plate-hint", text: "Pulsa para ampliar" }),
    ));
}

function renderSources(sources) {
  // Agrupa por archivo: "Manual.pdf — páginas 12, 13"
  const byFile = new Map();
  sources.forEach(({ file, page }) => {
    if (!byFile.has(file)) byFile.set(file, new Set());
    byFile.get(file).add(page);
  });
  const chips = [...byFile].map(([file, pages]) => {
    const list = [...pages].sort((a, b) => a - b);
    const label = list.length === 1 ? `Página ${list[0]}` : `Páginas ${list.join(", ")}`;
    return el("span", { class: "source" }, el("b", { text: file }), label);
  });
  return el("div", { class: "sources" }, "Fuente:", chips);
}

function showPending() {
  const node = el("div", { class: "msg assistant", id: "pending" },
    el("div", { class: "bubble pending", role: "status" },
      el("span", { class: "dots" }, el("i"), el("i"), el("i")),
      "Buscando en los documentos…"));
  messagesEl.append(node);
  scrollToEnd();
  return node;
}

function scrollToEnd() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* ---------- Lightbox ---------- */
const lightbox = $("#lightbox");
function openLightbox(url, alt, img) {
  $("#lightbox-img").src = url;
  $("#lightbox-img").alt = alt;
  $("#lightbox-caption").textContent = `${img.file} — Página ${img.page}${img.caption ? " — " + img.caption : ""}`;
  lightbox.showModal();
}
lightbox.addEventListener("click", (e) => { if (e.target === lightbox) lightbox.close(); });

/* ---------- Envío de preguntas ---------- */
function persistChat() {
  save("rag.chat", state.messages.filter((m) => m.role !== "error").slice(-60));
}

function addMessage(msg) {
  state.messages.push(msg);
  persistChat();
  if (state.messages.length === 1) messagesEl.replaceChildren();
  messagesEl.append(renderMessage(msg));
  scrollToEnd();
}

function setBusy(busy) {
  state.busy = busy;
  $("#send").disabled = busy;
  $("#question").disabled = busy;
  if (!busy) $("#question").focus();
}

async function send(question) {
  question = question.trim();
  if (state.busy || !question) return;

  // El historial se calcula ANTES de agregar la pregunta actual.
  const history = state.messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .slice(-LIMITS.historyTurns)
    .map(({ role, content }) => ({ role, content }));

  addMessage({ role: "user", content: question });
  setBusy(true);
  const pending = showPending();

  try {
    const res = await api.ask({ question, history, document_id: state.selectedDoc || null });
    pending.remove();
    addMessage({
      role: "assistant",
      content: res.answer ?? "",
      sufficient: res.sufficient_info !== false,
      sources: res.sources ?? [],
      image: res.image ?? null,
    });
  } catch (e) {
    pending.remove();
    addMessage({ role: "error", content: e.message || "Ocurrió un error inesperado.", retry: question });
  } finally {
    setBusy(false);
  }
}

function retry(errorMsg) {
  // Quita el error y la pregunta que lo originó, y la reenvía.
  state.messages = state.messages.filter((m) => m !== errorMsg);
  const last = state.messages[state.messages.length - 1];
  if (last?.role === "user" && last.content === errorMsg.retry) state.messages.pop();
  persistChat();
  renderAll();
  send(errorMsg.retry);
}

/* ---------- Compositor ---------- */
const form = $("#composer");
const input = $("#question");

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value;
  input.value = "";
  autosize();
  send(q);
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});
function autosize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
}
input.addEventListener("input", autosize);

$("#new-chat").addEventListener("click", () => {
  if (state.busy) return;
  state.messages = [];
  persistChat();
  renderAll();
});

/* ---------- Documentos: selector ---------- */
const docSelect = $("#doc-select");

function renderDocSelect() {
  docSelect.replaceChildren(el("option", { value: "", text: "Todos los documentos" }));
  state.docs.forEach((d) => docSelect.append(el("option", { value: d.id, text: d.name })));
  if (!state.docs.some((d) => d.id === state.selectedDoc)) state.selectedDoc = "";
  docSelect.value = state.selectedDoc;
}
docSelect.addEventListener("change", () => {
  state.selectedDoc = docSelect.value;
  save("rag.doc", state.selectedDoc);
});

/* ---------- Subida y seguimiento de jobs ---------- */
const dropzone = $("#dropzone");
const fileInput = $("#file-input");
const jobsEl = $("#jobs");
const jobsEmpty = $("#jobs-empty");

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("is-over"); }));
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("is-over"); }));
dropzone.addEventListener("drop", (e) => handleFiles(e.dataTransfer.files));
fileInput.addEventListener("change", () => { handleFiles(fileInput.files); fileInput.value = ""; });

function handleFiles(files) {
  [...files].forEach(startUpload);
}

function createJobItem(name) {
  jobsEmpty.hidden = true;
  const state = el("div", { class: "job-state", text: "Subiendo…" });
  const bar = el("span");
  const node = el("li", { class: "job", "data-status": "pending" },
    el("div", { class: "job-name", text: name, title: name }),
    state,
    el("div", { class: "job-bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0" }, bar));
  jobsEl.prepend(node);

  return {
    update({ status, stage, progress, error }) {
      node.dataset.status = status;
      const pct = Math.max(0, Math.min(100, progress ?? 0));
      bar.style.width = pct + "%";
      node.querySelector(".job-bar").setAttribute("aria-valuenow", String(pct));
      const text = {
        pending: "En cola…",
        processing: `${STAGE_LABEL[stage] ?? "Procesando"} (${pct} %)`,
        completed: "Listo para consultar",
        failed: error || "No se pudo procesar el documento.",
      }[status] ?? status;
      state.textContent = text;
    },
    fail(msg) { this.update({ status: "failed", error: msg }); },
  };
}

async function startUpload(file) {
  const item = createJobItem(file.name);

  if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
    return item.fail("Solo se aceptan archivos PDF.");
  }
  if (file.size > LIMITS.maxFileMB * 1024 * 1024) {
    return item.fail(`El archivo supera el límite de ${LIMITS.maxFileMB} MB.`);
  }

  try {
    const { job_id } = await api.uploadDocument(file);
    item.update({ status: "pending", progress: 0 });
    await track(job_id, item, file.name);
  } catch (e) {
    item.fail(e.message);
  }
}

async function track(jobId, item, fallbackName) {
  let delay = 1000;
  let failures = 0;

  for (;;) {
    await sleep(delay);
    try {
      const job = await api.getJob(jobId);
      failures = 0;
      item.update(job);

      if (job.status === "completed") {
        const id = job.document_id ?? jobId;
        if (!state.docs.some((d) => d.id === id)) {
          state.docs.push({ id, name: job.filename ?? fallbackName });
          save("rag.docs", state.docs);
          renderDocSelect();
        }
        return;
      }
      if (job.status === "failed") return;
      delay = Math.min(delay * 1.25, 4000); // espaciar consultas progresivamente
    } catch (e) {
      if (e.status === 404) return item.fail("El servidor no reconoce este trabajo.");
      if (++failures >= 5) return item.fail("Se perdió la conexión al consultar el progreso.");
      delay = Math.min(delay * 2, 8000);
    }
  }
}

/* ---------- Conexión ---------- */
const mockToggle = $("#mock-toggle");
const apiBase = $("#api-base");
const mockBadge = $("#mock-badge");

function syncSettingsUI() {
  const s = getSettings();
  mockToggle.checked = s.mock;
  apiBase.value = s.apiBase;
  apiBase.disabled = s.mock;
  mockBadge.hidden = !s.mock;
}
mockToggle.addEventListener("change", () => { saveSettings({ mock: mockToggle.checked }); syncSettingsUI(); });
apiBase.addEventListener("change", () => { saveSettings({ apiBase: apiBase.value.trim().replace(/\/$/, "") }); });

/* ---------- Inicio ---------- */
syncSettingsUI();
renderDocSelect();
renderAll();
input.focus();