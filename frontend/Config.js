const KEY = "rag.settings";

const DEFAULTS = {
  apiBase: "http://localhost:8000", 
  mock: true,                       
};

export function getSettings() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
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
  requestTimeoutMs: 60_000,
};