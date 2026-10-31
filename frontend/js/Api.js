/**
 * Cliente de la API. Contrato que el backend debe cumplir:
 *
 *  POST /documents        (multipart, campo "file")
 *    -> 202 { job_id }
 *
 *  GET  /jobs/{job_id}
 *    -> 200 { job_id, status, stage, progress, document_id?, filename?, error? }
 *       status:   "pending" | "processing" | "completed" | "failed"
 *       stage:    "parsing" | "chunking" | "embedding" | "indexing" | null
 *       progress: 0..100
 *
 *  POST /ask  { question, history: [{role, content}], document_id? }
 *    -> 200 { answer, sufficient_info, sources: [{file, page}],
 *             image: { url, page, file, caption? } | null }
 */
import { getSettings, LIMITS } from "./Config";
import * as mock from "./Mock.js";

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", json, form } = {}) {
  const { apiBase } = getSettings();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), LIMITS.requestTimeoutMs);

  try {
    const res = await fetch(apiBase + path, {
      method,
      signal: ctrl.signal,
      headers: json ? { "Content-Type": "application/json" } : undefined,
      body: form ?? (json ? JSON.stringify(json) : undefined),
    });

    if (!res.ok) {
      let detail = "";
      try {
        const body = await res.json();
        detail = typeof body.detail === "string" ? body.detail : body.message || "";
      } catch { /* respuesta sin JSON */ }
      throw new ApiError(detail || `El servidor respondió con el error ${res.status}.`, res.status);
    }
    return await res.json();
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e.name === "AbortError") throw new ApiError("El servidor tardó demasiado en responder.");
    throw new ApiError("No se pudo conectar con el servidor. Revisa la URL de la API en Conexión.");
  } finally {
    clearTimeout(timer);
  }
}

const useMock = () => getSettings().mock;

export function uploadDocument(file) {
  if (useMock()) return mock.uploadDocument(file);
  const form = new FormData();
  form.append("file", file);
  return request("/documents", { method: "POST", form });
}

export function getJob(jobId) {
  if (useMock()) return mock.getJob(jobId);
  return request(`/jobs/${encodeURIComponent(jobId)}`);
}

export function ask({ question, history, document_id }) {
  if (useMock()) return mock.ask({ question, history, document_id });
  return request("/ask", { method: "POST", json: { question, history, document_id } });
}

/** Convierte URLs relativas del backend (ej. /images/abc.png) en absolutas. */
export function resolveUrl(url) {
  if (!url || /^(https?:|data:|blob:)/.test(url)) return url;
  return getSettings().apiBase.replace(/\/$/, "") + url;
}