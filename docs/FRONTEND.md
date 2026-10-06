# Baseerah web frontend

Static, RTL-first frontend in `frontend/` (HTML + CSS + vanilla JS modules, no build step, no framework).
It talks only to the Baseerah FastAPI backend; it never calls a model provider and holds no keys.

## Structure

```
frontend/
  index.html          Ask Baseerah: hero → conversation (answers, sources, actions)
  verify.html         تحققي من دليل
  sources.html        المصادر والموثوقية (categories from GET /sources)
  model.html          عن النموذج (all values from GET /model-info)
  saved.html          المحفوظات (localStorage)
  about.html          عن بصيرة + #contact
  privacy.html        الخصوصية (+ clear local data)
  css/  variables.css  global.css  components.css  chat.css  pages.css  responsive.css
  js/   config.js   ← the ONLY place that points at a backend (regenerated at deploy time on Vercel or Render)
        api.js      ← all HTTP calls + response normalizers (the ONLY place to adapt to a contract change)
        mock.js     ← mock adapter (placeholder data only), enabled by USE_MOCK
        storage.js  ui.js  icons.js  chat.js  verify.js  sources.js  model.js  saved.js  about.js  privacy.js
  assets/logo/mark.svg   stand-in mark — replace with the official logo file (same name)
  assets/logo/favicon.svg
  assets/images/pattern.svg
  scripts/write-config.sh   build step on Vercel and Render (writes js/config.js)
  tests/ui_test.py          Playwright end-to-end checks
```

## Run locally

```bash
uvicorn api:app --port 8000                     # backend (CORS allows http://localhost:5500 by default)
python -m http.server 5500 -d frontend          # frontend → http://localhost:5500
```

No backend? Set `USE_MOCK: true` in `frontend/js/config.js`. A banner marks mock mode, and all mock text is labeled as placeholder.
Mock trigger words for testing states are listed at the top of `js/mock.js` (e.g. `خطأ`, `لا-دليل`, `بدون-شرح`, `رابط-معطل`, `بطيء`).

Single origin alternative: `BASEERAH_SERVE_FRONTEND=1 uvicorn api:app --port 8000` serves `frontend/` at `/`, plus a generated `js/config.js` that points at the same origin. It works under any host name (localhost, 127.0.0.1, a domain) with no CORS setup.

## API contract (implemented in `api.py`)

`POST /chat` `{"question": "..."}` (1–1000 chars)
```json
{
  "status": "answered | insufficient_evidence",
  "kind": "answer | referral | identified | insufficient | clarify",
  "answer": "generated explanation or null (null in retrieval-only mode or if the LLM failed)",
  "message": "status message from the backend",
  "notice": "optional notice (e.g. retrieval-only mode)",
  "disclosure": "هذه الإجابة من أداة مدعومة بالذكاء الاصطناعي وليست من مختص شرعي.",
  "generated_label": "label shown above generated text",
  "mode": "retrieval | anthropic | openai",
  "sources": [Source]
}
```
Source object (all text fields are copied from the database):
```json
{ "id": "hadith-5882", "type": "hadith | ayah | tafsir", "name": "صحيح البخاري",
  "reference": "صحيح البخاري، كتاب الأدب، رقم 5882", "text": "verbatim text", "url": "https://...",
  "grade": "صحيح", "grade_basis": "...", "dorar": {"grade": "...", "muhaddith": "..."} | null,
  "note": {"text": "...", "source": "..."} | null, "numbering_note": "...",
  "ayah": {"reference": "...", "text": "...", "url": "..."}   // tafsir only
}
```

`POST /verify` `{"text": "..."}` (1–500 chars)
```json
{ "status": "matched | partial_match | not_matched | insufficient_evidence",
  "reason": "too_short | no_source | null", "message": "...", "coverage": 0.0-1.0,
  "matched_words": 4, "total_words": 4, "method": "...", "sources": [Source] }
```
Verification compares wording only (no generation): the share of the submitted words found in order in a stored hadith matn or ayah.
Thresholds are in `check.py`: `matched` needs ≥ 0.9 coverage; `partial_match` needs ≥ 0.7 coverage, ≥ 4 matched words and a 3-word contiguous run; `not_matched` needs ≥ 0.3 and returns no source.

`POST /explain` `{"source_id": "hadith-5882"}` (hadith only). The text is read from the DB by ID.
```json
{ "status": "explained | unavailable | rejected | not_explainable | error",
  "explanation": "generated text or null", "words": [{"word": "...", "meaning": "..."}],
  "message": "status message", "text": "verbatim hadith", "reference": "...",
  "stored_note": {"text": "...", "source": "..."} | null, "grounded_on": ["نص الحديث المعروض"],
  "label": "شرح مولَّد بالذكاء الاصطناعي (ليس نصاً شرعياً)", "disclosure": "...", "checks_failed": ["quote|number|collection"] }
```
- `unavailable`: the server runs in retrieval mode.
- `rejected`: the generated text failed the grounding checks in `explain.py`, so it is not returned.
- Final results are cached per hadith and model; failures are not cached.

`GET /sources` → `{"categories": [{key, type, name, description, count, unit, items?}], "grading": {basis[], dorar_matched}}` (counts from the DB).

`GET /model-info` → `{mode, model_name, provider, model_version, runtime{...}, retrieval{...}, abstention{...}, evaluation}`. `runtime` (null fields omitted on the page) gives location (local/remote), host name, Ollama size/quantization/context when the model server is local, understanding backend, JSON mode, glosses, timeout and the fallback; it never contains keys or full URLs. `evaluation` is `eval_metrics.json`, copied from real `evaluate.py` runs by `scripts/export_metrics.py`. When it is absent, the page shows "لم تُنشر نتيجة قياس نهائية بعد.".

`GET /health` → `{"status": "ok"}`.

Errors are always `{"status": "error", "message": "<generic Arabic text>"}` (422 for invalid input, 500 otherwise). The frontend ignores the message and shows its own text by error kind, so no server text or trace reaches the user.

## Environment variables

| Where | Variable | Purpose |
|---|---|---|
| Static site (build) | `API_BASE_URL` | Backend URL, e.g. `https://baseerah-api.onrender.com` (empty = same origin) |
| | `USE_MOCK` | `true` = mock data (default `false`) |
| | `REQUEST_TIMEOUT_MS` | default `90000` |
| | `CONTACT_EMAIL` | optional |
| API | `BASEERAH_CORS_ORIGINS` | comma-separated allowed frontend origins |
| | `BASEERAH_LLM` | `retrieval` (default, no key), `anthropic`, or `openai` |
| | `ANTHROPIC_API_KEY` | only for `anthropic`; locally put it in `.env` (git-ignored, see `.env.example`); on Render set it as a secret env var |
| | `BASEERAH_MODEL` | model id for the LLM backend |
| | `BASEERAH_BASE_URL` | OpenAI-compatible server URL (required for `openai`, otherwise the SDK defaults to OpenAI's cloud) |
| | `HF_HOME`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` | ship models with the build; no Hugging Face calls at runtime (set automatically once both models are cached, see `envfile.py`) |
| | `BASEERAH_LLM_TIMEOUT` | seconds per LLM call (default 240 local / 75 Anthropic) |
| | `BASEERAH_RERANK` | `0` disables the reranker (also disables its relevance gate) |
| | `BASEERAH_SERVE_FRONTEND` | `1` = serve `frontend/` from the API |
| | `BASEERAH_DB`, `BASEERAH_VEC` | database paths (defaults `baseerah.db`, `embeddings.db`) |

## Deploy on Render

`render.yaml` defines both services (Blueprint):

1. Render → New → Blueprint → select this repo/branch. Render pulls the Git LFS databases during the clone.
2. **API (`baseerah-api`)**: the build installs CPU torch and requirements, then pre-downloads both models into `HF_HOME`. At runtime `HF_HUB_OFFLINE=1`, and health checks hit `/health`.
   **Memory:** measured RSS is about 1.7 GB with both models loaded, so use an instance with at least 2 GB RAM. The free 512 MB instance will not run it.
3. **Static site (`baseerah-web`)**: the build runs `frontend/scripts/write-config.sh` and publishes `frontend/`.
4. After the first deploy:
   - set `API_BASE_URL` on the static site to the API's URL;
   - set `BASEERAH_CORS_ORIGINS` on the API to the static site's URL (`https://<name>.onrender.com`, plus any custom domain);
   - redeploy both.
5. Optional: `BASEERAH_LLM=anthropic` + `ANTHROPIC_API_KEY`, or `openai` + `BASEERAH_BASE_URL`, on the API only.

Notes:
- **LFS bandwidth:** each deploy pulls about 126 MB of LFS data. GitHub's free LFS bandwidth quota is limited, so frequent deploys may need a data pack or another way to ship the DBs.
- **Single service:** you can skip the static site and set `BASEERAH_SERVE_FRONTEND=1` on the API. The site then calls the API on its own origin automatically.

## Testing

```bash
python -m pytest                       # backend + API contract tests
# UI (Playwright + Chromium): three static servers, see the docstring in the file
python frontend/tests/ui_test.py
```
`ui_test.py` covers:
- all 7 pages × desktop/tablet/mobile: RTL, footer, no console errors, no horizontal scroll, no login UI;
- chat with real sources and the four actions, the AI notice, copy, save toggle and badge, history reopen;
- the saved page (open, delete, empty state), the off-topic answer, and verify matched / not_matched / insufficient;
- `/sources` and `/model-info` rendering;
- every mock edge state, including an HTML-injection question and a `javascript:` URL;
- backend down, the mobile drawer, and the skip link.

Manual checklist: real phone keyboard behavior, screen reader pass (VoiceOver/TalkBack), the official logo file in place, and the production URLs in config.
