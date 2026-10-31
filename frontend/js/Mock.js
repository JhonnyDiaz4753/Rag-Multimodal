/** Backend simulado. Permite probar toda la UI sin servidor. */

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const jobs = new Map();

const STAGES = [
  { stage: "parsing", from: 0, to: 35 },
  { stage: "chunking", from: 35, to: 55 },
  { stage: "embedding", from: 55, to: 85 },
  { stage: "indexing", from: 85, to: 100 },
];
const TOTAL_MS = 8000;

export async function uploadDocument(file) {
  await wait(400);
  if (/fail|error/i.test(file.name)) {
    const id = crypto.randomUUID();
    jobs.set(id, { start: Date.now(), filename: file.name, fail: true });
    return { job_id: id };
  }
  const id = crypto.randomUUID();
  jobs.set(id, { start: Date.now(), filename: file.name, document_id: crypto.randomUUID() });
  return { job_id: id };
}

export async function getJob(jobId) {
  await wait(150);
  const job = jobs.get(jobId);
  if (!job) {
    const err = new Error("Trabajo no encontrado.");
    err.status = 404;
    throw err;
  }

  const elapsed = Date.now() - job.start;
  const pct = Math.min(100, Math.round((elapsed / TOTAL_MS) * 100));

  if (job.fail && pct > 40) {
    return { job_id: jobId, status: "failed", stage: "parsing", progress: 40, error: "No se pudo leer el PDF: archivo dañado o protegido." };
  }
  if (pct === 0) return { job_id: jobId, status: "pending", stage: null, progress: 0 };
  if (pct >= 100) {
    return { job_id: jobId, status: "completed", stage: null, progress: 100, document_id: job.document_id, filename: job.filename };
  }
  const stage = STAGES.find((s) => pct >= s.from && pct < s.to)?.stage ?? "indexing";
  return { job_id: jobId, status: "processing", stage, progress: pct };
}

/** Diagrama de ejemplo (SVG embebido) para no depender de archivos externos. */
function sampleDiagram() {
  const svg = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" font-family="sans-serif">
  <rect width="640" height="360" fill="#fff"/>
  <g stroke="#18232e" stroke-width="2" fill="none">
    <rect x="40" y="130" width="130" height="80" fill="#e3eafa"/>
    <rect x="255" y="130" width="130" height="80" fill="#e3eafa"/>
    <rect x="470" y="130" width="130" height="80" fill="#fff4d1"/>
    <path d="M170 170 H255 M385 170 H470"/>
    <path d="M247 162 l8 8 l-8 8 M462 162 l8 8 l-8 8"/>
    <path d="M320 130 V70 H105 V130" stroke-dasharray="6 5"/>
  </g>
  <g fill="#18232e" font-size="16" text-anchor="middle">
    <text x="105" y="176">Sensor</text>
    <text x="320" y="176">Controlador</text>
    <text x="535" y="176">Actuador</text>
    <text x="212" y="60" font-size="13" fill="#4a5967">retroalimentación</text>
    <text x="320" y="320" font-size="14" fill="#4a5967">Figura 3.2 — Lazo de control</text>
  </g>
</svg>`;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

export async function ask({ question }) {
  await wait(900 + Math.random() * 700);
  const q = question.toLowerCase();

  if (/error|falla.*servidor|500/.test(q)) {
    const err = new Error("El proveedor del modelo no está disponible. Inténtalo de nuevo en unos segundos.");
    err.status = 503;
    throw err;
  }

  if (/clima|futbol|fútbol|receta|pel[ií]cula/.test(q)) {
    return {
      answer: "No tengo información suficiente en los documentos para responder esa pregunta.",
      sufficient_info: false,
      sources: [],
      image: null,
    };
  }

  if (/diagrama|figura|esquema|imagen|lazo|control/.test(q)) {
    return {
      answer:
        "El sistema funciona como un **lazo de control cerrado**:\n\n" +
        "1. El *sensor* mide la variable del proceso.\n" +
        "2. El *controlador* compara la medición con el valor objetivo.\n" +
        "3. El *actuador* corrige la diferencia.\n\n" +
        "| Parámetro | Valor nominal |\n|---|---|\n| Tiempo de muestreo | 10 ms |\n| Tolerancia | ±2 % |\n\n" +
        "Puedes ver el esquema completo en la figura.",
      sufficient_info: true,
      sources: [
        { file: "Manual_Motor.pdf", page: 12 },
        { file: "Manual_Motor.pdf", page: 13 },
      ],
      image: {
        url: sampleDiagram(),
        file: "Manual_Motor.pdf",
        page: 12,
        caption: "Figura 3.2 — Lazo de control",
      },
    };
  }

  return {
    answer:
      "Según el manual, el **intervalo de mantenimiento** recomendado es cada *500 horas* de operación.\n\n" +
      "> Revisa el nivel de aceite antes de cada arranque.\n\n" +
      "Ejemplo de comando de diagnóstico:\n\n```\nDIAG --motor --nivel=2\n```",
    sufficient_info: true,
    sources: [{ file: "Manual_Motor.pdf", page: 48 }],
    image: null,
  };
}