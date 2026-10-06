"""FastAPI service.

  uvicorn api:app --port 8000

Endpoints used by the web frontend (frontend/): POST /chat, POST /verify, GET /sources, GET /model-info, GET /health.
GET|POST /ask keeps returning the raw answer.answer() output for the CLI-style integration.
Set BASEERAH_SERVE_FRONTEND=1 to also serve frontend/ from the same origin."""
import json, logging, os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from answer import answer, MODES, MODEL
from ask import default_mode

DB = os.environ.get("BASEERAH_DB", "baseerah.db")
VEC = os.environ.get("BASEERAH_VEC", "embeddings.db")
ROOT = Path(__file__).resolve().parent
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "BASEERAH_CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500").split(",") if o.strip()]
MAX_QUESTION = 1000
MAX_VERIFY = 500
GENERIC_ERROR = "تعذّر إكمال الطلب حاليًا. حاولي مرة أخرى بعد قليل."
VERIFY_MESSAGES = {
    "matched": "النص المُدخل يطابق نصًا مخزنًا في المصادر المعتمدة لدى بصيرة.",
    "partial_match": "النص قريب من نص مخزن لكنه لا يطابقه حرفيًا؛ يُعرض النص المخزن كما هو للمقارنة.",
    "not_matched": "الصيغة المُدخلة لا تطابق أي نص مخزن في المصادر المتاحة لدى بصيرة. "
                   "قد يكون النص واردًا في مصادر أخرى غير مشمولة في قاعدة بصيرة.",
    "insufficient_evidence": "لم يتم العثور على مصدر كافٍ للتحقق من هذا النص.",
    "too_short": "النص قصير جدًا للتحقق؛ أدخلي ثلاث كلمات على الأقل.",
}

log = logging.getLogger("baseerah")
app = FastAPI(title="Baseerah")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "ngrok-skip-browser-warning"])


@app.exception_handler(Exception)
def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"status": "error", "message": GENERIC_ERROR}, status_code=500)


@app.exception_handler(RequestValidationError)
def invalid(request: Request, exc: RequestValidationError):
    return JSONResponse({"status": "error", "message": "الطلب غير صالح أو أطول من الحد المسموح."}, status_code=422)


@app.on_event("startup")
def warm():
    from retrieve import get_retriever
    get_retriever(DB, VEC).qvec("بسم الله")


# ---------- /ask (raw pipeline output) ----------
class Ask(BaseModel):
    q: str
    mode: str | None = None


def run(q, mode):
    mode = mode or default_mode()
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    if not q.strip():
        raise HTTPException(400, "q is empty")
    return answer(q, DB, VEC, mode)


@app.get("/ask")
def ask_get(q: str, mode: str | None = None):
    return run(q, mode)


@app.post("/ask")
def ask_post(body: Ask):
    return run(body.q, body.mode)


# ---------- frontend contract ----------
def source_of(e):
    """One displayed text as a frontend source object. Every text field is copied from the database."""
    if e["kind"] == "hadith":
        from identify import NUMBERING_NOTE
        return {"id": f"hadith-{e['id']}", "type": "hadith", "name": e["ref"].split("،")[0].strip(),
                "reference": f"{e['ref']}، رقم {e['number']}", "number": e["number"], "text": e["text"],
                "url": e["link"]["url"], "grade": e["grade"], "grade_basis": e["grade_basis"], "dorar": e["dorar"],
                "note": e.get("note"), "numbering_note": NUMBERING_NOTE}
    src = {"id": f"{e['kind']}-{e.get('unit', e['ref'])}", "type": e["kind"], "name": e["source"],
           "reference": e["ref"], "text": e["text"], "url": e["url"]}
    if e.get("ayah"):
        src["ayah"] = {"reference": e["ayah"]["ref"], "text": e["ayah"]["text"], "url": e["ayah"]["url"]}
    return src


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)


@app.post("/chat")
def chat(body: ChatIn):
    q = body.question.strip()
    if not q:
        return JSONResponse({"status": "error", "message": "السؤال فارغ."}, status_code=400)
    mode = default_mode()
    out = answer(q, DB, VEC, mode)
    if out.get("error"):
        log.warning("LLM step failed (%s): %s", mode, out["error"])
    status = "answered" if out["status"] in ("answer", "referral", "identified") else "insufficient_evidence"
    return {"status": status, "kind": out["status"], "answer": out["explanation"], "message": out["message"],
            "notice": out["notice"], "disclosure": out["disclosure"], "generated_label": out["generated_label"],
            "mode": mode, "sources": [source_of(e) for e in out["texts"]]}


class VerifyIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_VERIFY)


@app.post("/verify")
def verify(body: VerifyIn):
    from check import check
    r = check(body.text.strip())
    key = "too_short" if r.get("reason") == "too_short" else r["status"]
    return {"status": r["status"], "reason": r.get("reason"), "message": VERIFY_MESSAGES[key],
            "coverage": r["coverage"], "matched_words": r.get("matched_words"), "total_words": r.get("total_words"),
            "method": "مطابقة لفظية بين النص المُدخل والنصوص المخزنة (دون توليد)",
            "sources": [source_of(r["match"])] if r.get("match") else []}


class ExplainIn(BaseModel):
    source_id: str = Field(pattern=r"^hadith-\d{1,6}$")


@app.post("/explain")
def explain_hadith(body: ExplainIn):
    """Generated explanation of one stored hadith (requires BASEERAH_LLM=anthropic|openai)."""
    from explain import explain
    r = explain(int(body.source_id.split("-")[1]), default_mode(), DB)
    if r["status"] == "not_found":
        return JSONResponse({"status": "error", "message": "الحديث غير موجود."}, status_code=404)
    if r.get("error"):
        log.warning("explain %s failed: %s", body.source_id, r["error"])
    return {k: v for k, v in r.items() if k not in ("error", "problems")} | (
        {"checks_failed": r["problems"]} if r.get("problems") else {})


@app.get("/sources")
def sources():
    from db import connect_ro
    from evidence import TAFSIR_NAME
    db = connect_ro(DB)
    count = lambda sql: db.execute(sql).fetchone()[0]
    books = db.execute("SELECT book, count(*) FROM hadith GROUP BY book ORDER BY book").fetchall()
    names = {"bukhari": "صحيح البخاري", "muslim": "صحيح مسلم"}
    note_sources = [r[0] for r in db.execute("SELECT DISTINCT source FROM hadith_notes WHERE source != ''")]
    cats = [
        {"key": "quran", "type": "quran", "name": "القرآن الكريم",
         "description": "نص المصحف من مجمع الملك فهد لطباعة المصحف الشريف (رواية حفص).",
         "count": count("SELECT count(*) FROM records WHERE source='quran'"), "unit": "آية"},
        {"key": "hadith", "type": "hadith", "name": "الحديث النبوي",
         "description": "أحاديث الصحيحين: " + "، ".join(names.get(b, b) for b, _ in books) + ".",
         "count": count("SELECT count(*) FROM hadith"), "unit": "حديث",
         "items": [{"name": names.get(b, b), "count": n} for b, n in books]},
        {"key": "tafsir", "type": "tafsir", "name": "التفسير", "description": TAFSIR_NAME + ".",
         "count": count("SELECT count(*) FROM records WHERE source='tafsir'"), "unit": "تفسير آية"},
    ]
    notes = count("SELECT count(*) FROM hadith_notes")
    if notes:
        cats.append({"key": "notes", "type": "other", "name": "شروح مساندة",
                     "description": "شروح مختارة لبعض الأحاديث من: " + "، ".join(note_sources) + ".",
                     "count": notes, "unit": "شرح"})
    basis = [r[0] for r in db.execute("SELECT DISTINCT grade_source FROM hadith")]
    return {"categories": cats, "grading": {"basis": basis,
            "dorar_matched": count("SELECT count(*) FROM hadith WHERE dorar_grade IS NOT NULL AND dorar_grade != 'لم يُطابَق'")}}


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}


def ollama_details(base_url, model):
    """Size and quantization reported by an Ollama server for model, or None (other servers, or unreachable)."""
    import urllib.request
    root = base_url.rstrip("/").removesuffix("/v1")
    try:
        req = urllib.request.Request(f"{root}/api/show", data=json.dumps({"model": model}).encode(),
                                     headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=2))
    except Exception:
        return None
    info, det = d.get("model_info") or {}, d.get("details") or {}
    ctx = next((v for k, v in info.items() if k.endswith(".context_length")), None)
    return {"server": "Ollama", "family": det.get("family"), "parameter_size": det.get("parameter_size"),
            "quantization": det.get("quantization_level"), "format": det.get("format"), "context_length": ctx}


def runtime_info(mode):
    """How the active LLM runs: where, with which settings, and what happens when it fails. No keys or full URLs."""
    if mode == "retrieval":
        return {"location": None, "fallback": "لا يوجد نموذج لغوي: تُعرض النصوص المسترجعة فقط."}
    from urllib.parse import urlparse
    from answer import LLM_MAX_TOKENS, FALLBACK_MODELS
    understanding = os.environ.get("BASEERAH_UNDERSTAND") or ("rules" if mode == "openai" else mode)
    out = {"understanding": understanding,
           "explain_glosses": os.environ.get("BASEERAH_EXPLAIN_WORDS", "0" if mode == "openai" else "1") == "1",
           "timeout_ms": int(os.environ.get("BASEERAH_TIMEOUT_MS", "300000" if mode == "openai" else "90000")),
           "fallback": "عند تعذر الاتصال بالنموذج تُعرض النصوص المسترجعة بمراجعها دون شرح مولَّد."}
    if mode == "anthropic":
        out.update(location="remote", host="api.anthropic.com", max_tokens=LLM_MAX_TOKENS,
                   server_fallback=MODEL in FALLBACK_MODELS and os.environ.get("BASEERAH_FALLBACKS", "1") != "0")
    else:
        base = os.environ.get("BASEERAH_BASE_URL") or "https://api.openai.com/v1"
        host = urlparse(base).hostname or ""
        out.update(location="local" if host in LOCAL_HOSTS else "remote", host=host, json_mode=True,
                   details=ollama_details(base, MODEL) if host in LOCAL_HOSTS else None)
    return out


@app.get("/model-info")
def model_info():
    import evidence
    from db import connect_ro
    from retrieve import RERANKER, RRF_K, POOL, RERANK_POOL, RERANK_REWRITES
    mode = default_mode()
    emb = connect_ro(VEC).execute("SELECT v FROM meta WHERE k='model'").fetchone()[0]
    metrics = ROOT / "eval_metrics.json"
    return {
        "mode": mode,
        "model_name": None if mode == "retrieval" else MODEL,
        "provider": {"anthropic": "Anthropic", "openai": "OpenAI-compatible"}.get(mode),
        "model_version": None,
        "runtime": runtime_info(mode),
        "retrieval": {"embedding_model": emb, "reranker": RERANKER if evidence.RERANK else None,
                      "lexical": "SQLite FTS5 (BM25)", "fusion": f"Reciprocal Rank Fusion (k={RRF_K})",
                      "candidates": POOL, "rerank_pool": RERANK_POOL if evidence.RERANK else None,
                      "rerank_rewrites": RERANK_REWRITES if evidence.RERANK else None,
                      "hf_offline": os.environ.get("HF_HUB_OFFLINE") == "1", "databases_read_only": True},
        "abstention": {"min_similarity": evidence.T_LEX, "high_similarity": evidence.T_HIGH,
                       "min_rerank_score": evidence.T_RERANK if evidence.RERANK else None},
        "evaluation": json.load(open(metrics, encoding="utf-8")) if metrics.exists() else None,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if os.environ.get("BASEERAH_SERVE_FRONTEND") == "1":
    from fastapi.responses import Response
    from fastapi.staticfiles import StaticFiles

    @app.get("/js/config.js", include_in_schema=False)
    def frontend_config():
        """When this API serves the site, the site calls back to the same origin, whatever host name the
        browser used (localhost, 127.0.0.1, a domain), so no CORS setup is needed."""
        cfg = {"API_BASE_URL": "", "USE_MOCK": False, "REQUEST_TIMEOUT_MS": int(os.environ.get(
            "BASEERAH_TIMEOUT_MS", "300000" if default_mode() == "openai" else "90000")),
               "CONTACT_EMAIL": os.environ.get("CONTACT_EMAIL", "")}
        return Response(f"window.BASEERAH_CONFIG = {json.dumps(cfg, ensure_ascii=False)};\n",
                        media_type="application/javascript", headers={"Cache-Control": "no-store"})

    class FreshStatic(StaticFiles):
        """Browsers must revalidate site files on every load, so an update is never hidden by a stale cache."""
        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            resp.headers["Cache-Control"] = "no-cache"
            return resp

    app.mount("/", FreshStatic(directory=ROOT / "frontend", html=True), name="frontend")
