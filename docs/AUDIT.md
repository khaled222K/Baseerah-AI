# Baseerah technical audit (October 2026)

What runs, where, and what happens when a part fails. Every value below is read from the code or from a measured run; the
page "عن النموذج" (`GET /model-info`) shows the same values live from the server.

## 1. Active language model

Baseerah does not hard-code one model. The server's `.env` (or environment) chooses it:

| setting | your current setup (from your screenshot) | default if unset |
|---|---|---|
| `BASEERAH_LLM` | `openai` (OpenAI-compatible API) | `retrieval` for `ask.py` / API (no model) |
| `BASEERAH_BASE_URL` | `http://localhost:11434/v1` (Ollama on your machine) | OpenAI's cloud (so it must be set) |
| `BASEERAH_MODEL` | `aya-expanse:8b` | `claude-sonnet-5-5` (only used with `BASEERAH_LLM=anthropic`) |

`aya-expanse:8b` is a real model, not a placeholder. Its details as reported by Ollama's `/api/show`, and shown on the
model page:
- **Family:** Cohere Command-R.
- **Size and format:** 8.0B parameters, GGUF, quantized Q4_K_M.
- **Context:** 8,192 tokens.
- **License:** CC-BY-NC 4.0, non-commercial use only.

**Where it runs:** locally, on the same machine as the API. No question or text leaves the machine.

Operational parameters in `openai` mode:

| parameter | value | where |
|---|---|---|
| reply format | JSON mode (`response_format: json_object`), falls back to plain if the server rejects it | `answer.llm_call` |
| request timeout | 240 s per call, no retries (`BASEERAH_LLM_TIMEOUT`) | `answer.llm_timeout` |
| site timeout | 300 s (`BASEERAH_TIMEOUT_MS`) | `api.frontend_config` |
| question rewrite | rules (no model call), to keep CPU time down (`BASEERAH_UNDERSTAND` overrides) | `answer.answer` |
| word glosses in "اشرح الحديث" | off (`BASEERAH_EXPLAIN_WORDS=1` turns them on) | `explain._explain` |

In `anthropic` mode, the parameters are:
- `max_tokens` 16,000;
- server-side refusal fallback on for `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-opus-5` and `claude-fable-5-1`;
- a 75 s timeout with 1 retry.

**Measured on a 4-core CPU without a GPU:** 60–90 s per answer once the model is loaded. The first request after start-up
also loads the model (about 2 minutes). These times come from `docs/BENCHMARK.md`.

## 2. Retrieval models (always local)

| stage | model / method | parameters |
|---|---|---|
| lexical search | SQLite FTS5, BM25 ranking | over `hadith_fts` and `rfts` (normalized Arabic) |
| dense search | `intfloat/multilingual-e5-small` | `query:` / `passage:` prefixes, cosine similarity, top 50 |
| fusion | Reciprocal Rank Fusion | k = 60; the question and each rewrite add their own ranked lists |
| reranker | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | reranks the top 30. Each passage keeps its best score over the question and up to 2 rewrites |
| evidence gate | thresholds in `evidence.py` | see below |

The evidence gate shows a text only when:
- its reranker score is at least −2.5, calibrated on `calib_set.json`; and
- its cosine similarity is at least 0.92, or it is at least 0.80 and the text shares a search word with the question.

If nothing passes, the answer is "لم أجد نصاً مباشراً…" and no text is shown.

**Change in this update:** the reranker now also scores the formal-Arabic rewrite. Before, a text could be found by its
rewrite but then rejected because the reranker only saw the original dialect or long-framed question. Effect, measured with
`evaluate.py`:

| measure | before | after |
|---|---|---|
| eval_set end to end: expected text shown | 47/78 | 47/78 |
| eval_set end to end: out of scope rejected | 7/8 | 7/8 |
| retrieval, default pipeline: R@1 | 0.526 | 0.526 |
| retrieval, default pipeline: R@3 | 0.679 | 0.667 |
| retrieval, default pipeline: R@10 | 0.756 | 0.769 |
| retrieval, default pipeline: MRR | 0.608 | 0.607 |
| calibration set (26 questions): correct decision | 21/26 | 22/26 |

**Unchanged:** the embeddings and the thresholds.

## 3. Failure handling (fallbacks)

| what fails | what the user gets |
|---|---|
| LLM unreachable, slow (timeout), refuses, or returns unreadable output | Mode A: the retrieved texts with their references, no explanation, and the notice "تعذّر الاتصال بالنموذج…". Tested in `tests/test_benchmark.py::test_unreachable_model_falls_back_to_texts_quickly` |
| LLM explanation quotes text (in «», "", “”, ﴿﴾ or `*…*`) that is not in the shown texts, or contains Latin/CJK letters | the explanation is dropped and the texts are shown with a notice |
| personal-case question | referral message plus general texts; the LLM is not called, so no generated ruling can appear next to it |
| LLM says the texts don't answer the question | "لم أجد نصاً مباشراً…" (no texts) |
| question rewrite by LLM fails | the rules rewrite is used |
| "اشرح الحديث" fails | the hadith is shown as stored, with "تعذّر الاتصال بالنموذج حالياً"; failures are not cached |
| API down | the site shows its own "unavailable" message; no server text reaches the user |

## 4. Offline guard (Hugging Face)

`envfile.offline_if_cached()` runs before any model library is imported, when `answer.py` or `semantic.py` is loaded.
If both retrieval models are already in the local Hugging Face cache and `HF_HUB_OFFLINE` is not set, it sets
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

- **Before:** every start-up still contacted huggingface.co to check for updates. The log showed "You are sending
  unauthenticated requests to the HF Hub".
- **After:** that message is gone, and a running Baseerah makes no Hugging Face calls.

An explicit `HF_HUB_OFFLINE=0` or `1` is respected, and `scripts/fetch_models.py` sets 0 to download. The model list is
kept in sync with the code by `tests/test_offline.py`. The model page shows "الاتصال بـ Hugging Face أثناء التشغيل: لا".

## 5. Database safety

- All runtime code opens `baseerah.db` and `embeddings.db` through `db.connect_ro`, a `file:…?mode=ro` URI. SQLite refuses
  any write on these connections. This covers `api.py`, `evidence.py`, `retrieve.py`, `check.py`, `explain.py` and
  `identify.py`.
- Only maintainer build commands write: `semantic.py embed`, `build_hadith_db.py`, and the `data_build/` loaders. None of
  them runs when you ask a question.
- Nothing in this update changes the database contents or any hadith grade.
- Every displayed hadith, ayah and tafsir is copied from the database by ID. Tests check that the displayed text equals the
  stored one (`test_pipeline.py`, `test_benchmark.py`).

## 6. Outbound network at runtime

- **Retrieval:** none. FTS5 and the vectors are in the local SQLite files, and the models come from the local cache.
- **LLM:** only the configured LLM server. With your setup that is `localhost:11434`, so nothing leaves the machine. In
  `anthropic` mode it is `api.anthropic.com`.
- **Model page:** `/model-info` calls `localhost:11434/api/show` with a 2 s timeout, and only when the model server is local.
- **Hadith links:** links to dorar.net are plain links the user can click. The server never fetches them.

## 7. Known limits (not fixed here)

- **Model size:** a local 8B model can misread a text while writing fluent Arabic. Quotation and script checks cannot catch
  a wrong paraphrase, which is why the texts are always shown next to the explanation. See case 1 in `docs/BENCHMARK.md`.
- **Corpus:** the corpus is Bukhari, Muslim, the Quran and al-Muyassar only. There are no history, sīra, fiqh-comparison or
  translation sources, so questions about history (spread of Islam), scholarly disagreement, consensus, or English
  equivalents can only be answered from what those texts say.
- **Weak retrieval areas:** dialect questions the lexicon has not seen, and meta-questions ("هل يتفق كل المسلمين على…",
  "ما معنى X لشخص لم يسمع به") still often end in "no direct text" in retrieval-only mode.
- **Tuning caveat:** the small term maps added in `understand.py` were written after seeing the benchmark failures, so the
  benchmark overstates how well they generalize. Examples: English religious terms (jihad → الجهاد), modern → classical
  words (النظافة → الطهور), and request framing ("أعطني حديثاً يثبت أن").
