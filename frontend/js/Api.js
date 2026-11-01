/**
 * Cliente de la API. Contrato que el backend debe cumplir:
 *
 *  POST /documents        (multipart, campo "file")
 *    -> 202 { job_id, document_id, status_url }
 *
 *  GET  /jobs/{job_id}
 *    -> 200 { job_id, status, stage, progress }
 *       status:   "pending" | "processing" | "completed" | "failed"
 *       stage:    "parsing" | "chunking" | "embedding" | "indexing" | null
 *       progress: 0..100
 *
 *  POST /ask  { question, history: [{role, content}], doc_ids? }
 *    -> 200 { answer, sources: [{file, page}], image: data-uri | null }
 */
import { getSettings, LIMITS } from "./Config.js";
import * as mock from "./Mock.js";

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", json, form } = {}) {
  const { apiBase } = getSettings();
  const base = apiBase.replace(/\/$/, "");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), LIMITS.requestTimeoutMs);
  const requestId =
    globalThis.crypto?.randomUUID?.() ??
    `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  try {
    const res = await fetch(base + path, {
      method,
      signal: ctrl.signal,
      headers: {
        "X-Request-ID": requestId,
        ...(json ? { "Content-Type": "application/json" } : {}),
      },
      body: form ?? (json ? JSON.stringify(json) : undefined),
    });

    if (!res.ok) {
      let detail = "";
      try {
        const body = await res.json();
        detail =
          typeof body.detail === "string" ? body.detail : body.message || "";
      } catch {
        /* respuesta sin JSON */
      }
      throw new ApiError(
        detail || `El servidor respondió con el error ${res.status}.`,
        res.status,
      );
    }
    return await res.json();
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (e.name === "AbortError")
      throw new ApiError("El servidor tardó demasiado en responder.");
    throw new ApiError(
      "No se pudo conectar con el servidor. Revisa la URL de la API en Conexión.",
    );
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

export async function ask({ question, history, document_id }) {
  if (useMock()) return mock.ask({ question, history, document_id });
  const response = await request("/ask", {
    method: "POST",
    json: { question, history, doc_ids: document_id ? [document_id] : null },
  });
  const source = response.sources?.[0];
  return {
    ...response,
    image: response.image
      ? {
          url: response.image,
          file: source?.file ?? "",
          page: source?.page ?? "",
          caption: "",
        }
      : null,
  };
}

/** Convierte URLs relativas del backend (ej. /images/abc.png) en absolutas. */
export function resolveUrl(url) {
  if (!url || /^(https?:|data:|blob:)/.test(url)) return url;
  return getSettings().apiBase.replace(/\/$/, "") + url;
}
