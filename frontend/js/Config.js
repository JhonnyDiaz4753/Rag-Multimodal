const KEY = "rag.settings.v2";
const LEGACY_KEY = "rag.settings";

const DEFAULT_API_BASE = globalThis.location?.port === "3000" ? "/api" : "http://localhost:8000";

const DEFAULTS = {
  apiBase: DEFAULT_API_BASE,
  mock: false,
};

export function getSettings() {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored) return { ...DEFAULTS, ...JSON.parse(stored) };

    const legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) || "{}");
    return { ...DEFAULTS, apiBase: legacy.apiBase || DEFAULT_API_BASE };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveSettings(patch) {
  const next = { ...getSettings(), ...patch };
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}

export const LIMITS = {
  maxFileMB: 50,
  historyTurns: 8,      
  requestTimeoutMs: 300_000,
};