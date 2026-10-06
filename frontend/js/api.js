// API service layer. All backend calls and all response-shape mapping live here.
// If the backend contract changes, edit the normalize* functions below and nothing else.
import * as mock from "./mock.js";

const cfg = window.BASEERAH_CONFIG || {};
export const config = {
  apiBaseUrl: String(cfg.API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, ""),
  useMock: cfg.USE_MOCK === true,
  timeoutMs: Number(cfg.REQUEST_TIMEOUT_MS) || 90000,
  contactEmail: String(cfg.CONTACT_EMAIL || ""),
};

// errorKind: "unavailable" (network / timeout / 502-504) | "server" (other failures) | "invalid" (4xx)
class ApiError extends Error {
  constructor(kind) {
    super(kind);
    this.kind = kind;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), config.timeoutMs);
  let res;
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch {
    throw new ApiError("unavailable");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    if ([502, 503, 504].includes(res.status)) throw new ApiError("unavailable");
    throw new ApiError(res.status >= 400 && res.status < 500 ? "invalid" : "server");
  }
  try {
    return await res.json();
  } catch {
    throw new ApiError("server");
  }
}

// ---------- Safety helpers ----------
export function safeUrl(u) {
  if (typeof u !== "string" || !u.trim()) return null;
  try {
    const url = new URL(u, window.location.href);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}
const str = (v) => (typeof v === "string" ? v : v == null ? "" : String(v));
const strOrNull = (v) => (typeof v === "string" && v.trim() ? v : null);

// ---------- Normalizers (backend JSON -> UI model) ----------
export function normalizeSource(s, i = 0) {
  if (!s || typeof s !== "object") return null;
  const type = ["hadith", "ayah", "tafsir"].includes(s.type) ? s.type : "other";
  return {
    id: str(s.id ?? `source-${i}`),
    type,
    name: str(s.name) || "مصدر",
    reference: str(s.reference),
    text: str(s.text),
    url: safeUrl(s.url),
    grade: strOrNull(s.grade),
    gradeBasis: strOrNull(s.grade_basis),
    dorar: s.dorar && typeof s.dorar === "object"
      ? { grade: str(s.dorar.grade), muhaddith: str(s.dorar.muhaddith) } : null,
    note: s.note && typeof s.note === "object" && s.note.text
      ? { text: str(s.note.text), source: str(s.note.source) } : null,
    numberingNote: strOrNull(s.numbering_note),
    ayah: s.ayah && typeof s.ayah === "object"
      ? { reference: str(s.ayah.reference), text: str(s.ayah.text), url: safeUrl(s.ayah.url) } : null,
  };
}

const sourcesOf = (raw) => (Array.isArray(raw) ? raw.map(normalizeSource).filter(Boolean) : []);

export function normalizeChat(raw) {
  const status = ["answered", "insufficient_evidence", "error"].includes(raw?.status) ? raw.status : "error";
  return {
    status,
    kind: strOrNull(raw?.kind),                 // answer | referral | identified | insufficient | clarify
    answer: strOrNull(raw?.answer),             // generated explanation; null when no LLM text is available
    message: strOrNull(raw?.message),
    notice: strOrNull(raw?.notice),
    disclosure: strOrNull(raw?.disclosure),
    generatedLabel: strOrNull(raw?.generated_label),
    sources: sourcesOf(raw?.sources),
  };
}

export function normalizeVerify(raw) {
  const ok = ["matched", "partial_match", "not_matched", "insufficient_evidence", "error"];
  return {
    status: ok.includes(raw?.status) ? raw.status : "error",
    reason: strOrNull(raw?.reason),
    message: strOrNull(raw?.message),
    coverage: typeof raw?.coverage === "number" ? raw.coverage : null,
    matchedWords: Number.isFinite(raw?.matched_words) ? raw.matched_words : null,
    totalWords: Number.isFinite(raw?.total_words) ? raw.total_words : null,
    method: strOrNull(raw?.method),
    sources: sourcesOf(raw?.sources),
  };
}

export function normalizeSources(raw) {
  const cats = Array.isArray(raw?.categories) ? raw.categories : Array.isArray(raw) ? raw : [];
  return {
    categories: cats.filter((c) => c && typeof c === "object").map((c) => ({
      key: str(c.key || c.name),
      type: str(c.type),
      name: str(c.name),
      description: str(c.description),
      count: Number.isFinite(c.count) ? c.count : null,
      unit: str(c.unit),
      items: Array.isArray(c.items) ? c.items.map((x) => ({ name: str(x?.name), count: Number.isFinite(x?.count) ? x.count : null })) : [],
    })),
    grading: raw?.grading && typeof raw.grading === "object"
      ? { basis: Array.isArray(raw.grading.basis) ? raw.grading.basis.map(str) : [],
          dorarMatched: Number.isFinite(raw.grading.dorar_matched) ? raw.grading.dorar_matched : null }
      : null,
  };
}

export function normalizeModelInfo(raw) {
  const r = raw?.retrieval || {};
  const a = raw?.abstention || {};
  return {
    mode: strOrNull(raw?.mode),
    modelName: strOrNull(raw?.model_name),
    provider: strOrNull(raw?.provider),
    modelVersion: strOrNull(raw?.model_version),
    retrieval: { embeddingModel: strOrNull(r.embedding_model), reranker: strOrNull(r.reranker),
                 lexical: strOrNull(r.lexical), fusion: strOrNull(r.fusion) },
    abstention: { minSimilarity: a.min_similarity ?? null, highSimilarity: a.high_similarity ?? null,
                  minRerankScore: a.min_rerank_score ?? null },
    evaluation: raw?.evaluation && typeof raw.evaluation === "object" ? raw.evaluation : null,
  };
}

export function normalizeExplain(raw) {
  const ok = ["explained", "unavailable", "rejected", "not_explainable", "error"];
  return {
    status: ok.includes(raw?.status) ? raw.status : "error",
    message: strOrNull(raw?.message),
    explanation: strOrNull(raw?.explanation),
    words: Array.isArray(raw?.words) ? raw.words.filter((w) => w && w.word && w.meaning).map((w) => ({ word: str(w.word), meaning: str(w.meaning) })) : [],
    reference: strOrNull(raw?.reference),
    text: strOrNull(raw?.text),
    storedNote: raw?.stored_note && raw.stored_note.text ? { text: str(raw.stored_note.text), source: str(raw.stored_note.source) } : null,
    groundedOn: Array.isArray(raw?.grounded_on) ? raw.grounded_on.map(str) : [],
    label: strOrNull(raw?.label),
    disclosure: strOrNull(raw?.disclosure),
  };
}

// ---------- Public API ----------
const fail = (e) => ({ status: "error", errorKind: e instanceof ApiError ? e.kind : "server" });

export async function chat(question) {
  try {
    const raw = config.useMock ? await mock.chat(question) : await request("/chat", { method: "POST", body: { question } });
    return normalizeChat(raw);
  } catch (e) {
    return { ...normalizeChat({ status: "error" }), ...fail(e) };
  }
}

export async function verify(text) {
  try {
    const raw = config.useMock ? await mock.verify(text) : await request("/verify", { method: "POST", body: { text } });
    return normalizeVerify(raw);
  } catch (e) {
    return { ...normalizeVerify({ status: "error" }), ...fail(e) };
  }
}

export async function explain(sourceId) {
  try {
    const raw = config.useMock ? await mock.explain(sourceId) : await request("/explain", { method: "POST", body: { source_id: sourceId } });
    return normalizeExplain(raw);
  } catch (e) {
    return { ...normalizeExplain({ status: "error" }), ...fail(e) };
  }
}

export async function getSources() {
  try {
    const raw = config.useMock ? await mock.sources() : await request("/sources");
    return { status: "ok", ...normalizeSources(raw) };
  } catch (e) {
    return fail(e);
  }
}

export async function getModelInfo() {
  try {
    const raw = config.useMock ? await mock.modelInfo() : await request("/model-info");
    return { status: "ok", ...normalizeModelInfo(raw) };
  } catch (e) {
    return fail(e);
  }
}
