# Baseerah (بصيرة)

Baseerah retrieves Islamic texts from a local database in response to a question: hadith from Sahih al-Bukhari and Sahih Muslim, Quran ayat, and Tafsir al-Muyassar. Retrieval is fully local (SQLite FTS5 + dense vectors). Nothing is searched on the internet.

> This tool is AI-assisted and is **not** a qualified religious scholar (ليست من مختص شرعي). Every displayed hadith, ayah, and tafsir comes verbatim from `text_original` / `matn_display` in the database. The model only picks IDs of retrieved passages and may write a short explanation; explanations that quote text not present in the displayed passages are dropped.

## Setup

```bash
git lfs install && git lfs pull          # the two .db files are stored with Git LFS
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

The first run downloads `intfloat/multilingual-e5-small` from Hugging Face once; after that everything runs offline.

## Data

| File | Contents |
|---|---|
| `baseerah.db` | `records` (6,236 ayat + 6,236 tafsir entries), `hadith` (14,736: Bukhari + Muslim), `weak_hadith`, `hadith_notes`, FTS5 indexes `records_fts`, `hadith_fts` |
| `embeddings.db` | `vec(kind, ref_id, v)` float32 e5 vectors, `meta`, and `rfts` (FTS5 over normalized records text) |

Runtime code opens both databases read-only (`mode=ro`, see `db.py`). Only maintainer build steps write:

- `python semantic.py embed` writes vectors and `rfts` into `embeddings.db` (resumable, skips rows that already exist).
- `python build_hadith_db.py build|dorar` (re)builds or enriches the `hadith` table. Not needed for normal use, and it changes the DB.
- `data_build/load_quran.py` and `data_build/load_tafsir.py` rebuild `records` from `Quran.json` / `Tafsir.csv` into `data_build/baseerah.db` (a separate file next to the loaders). The `url` column of the shipped DB was filled in separately and is not produced by these loaders.

## Usage

```bash
python ask.py "ما حق الجار في الإسلام؟"                    # mode (a): retrieval only, no LLM, no key
python ask.py "وش أركان الإسلام؟" --mode anthropic          # mode (b): explanation via Anthropic API (ANTHROPIC_API_KEY)
BASEERAH_LLM=openai BASEERAH_BASE_URL=http://localhost:11434/v1 BASEERAH_MODEL=qwen2.5:7b \
  python ask.py "كم عدة المطلقة؟"                           # mode (c): local OpenAI-compatible server (Ollama, llama.cpp…)
python ask.py "ليس الشديد بالصرعة" --json                   # identifies the hadith being quoted

uvicorn api:app --port 8000      # GET /ask?q=...&mode=retrieval   or   POST /ask {"q": "...", "mode": "retrieval"}
```

Without `--mode`, `ask.py` and the API use `BASEERAH_LLM` if set, otherwise retrieval-only mode. If the LLM is unreachable, the texts are still shown, without an explanation.

## How it works

1. **Query understanding** (`understand.py`): the question (Gulf dialect or MSA) becomes formal-Arabic search rewrites and keywords. The `rules` backend (Gulf→MSA lexicon + keyword extraction) needs no model; the `anthropic` / `openai` backends ask the LLM for JSON only, with no search tool. Rewrites are used for search only and are never displayed. Any LLM failure falls back to `rules`.
2. **Hadith identification** (`identify.py`): when the user types part of a hadith or describes one ("حديث معناه…"), candidates from FTS + dense search are scored with `SequenceMatcher` against the normalized matn. The result gives the hadith ID, book, number and reference. Numbers follow the hadith-json dataset and can differ from printed editions; the output says so.
3. **Hybrid retrieval** (`retrieve.py`): BM25 over `hadith_fts` and `rfts`, plus dense e5 search over all vectors, fused with Reciprocal Rank Fusion (k=60). The query and each rewrite add their own ranked lists. A multilingual cross-encoder reranks the top 30 (on by default; `BASEERAH_RERANK=0` turns it off, `retrieve.py --rerank` for the CLI).
4. **Evidence gate** (`evidence.py`): a hit is shown only if it passes the existing similarity thresholds. If nothing passes: "لم أجد نصاً مباشراً مرتبطاً بالسؤال في المصادر المتاحة…". Personal-case questions are referred to scholars.
5. **Explanation** (`answer.py`, modes b/c): the LLM may only pick IDs among the retrieved texts and write a short explanation. Any explanation that quotes text not present in the displayed passages is dropped (`quotes_ok`, using `verify.MARKS`).

## Evaluation

`eval_set.json` has 86 items: 44 hadith topic questions, 24 ayah questions, 10 quotes/paraphrases of hadith, and 8 out-of-scope questions. 33 are in Gulf dialect, 53 in MSA. Every expected ID was checked by reading the text in `baseerah.db`. No item is marked `unverified`; items marked that way would be excluded from scores. Expected lists can miss other narrations of the same hadith, so scores are a lower bound.

Recall@k = share of questions with at least one expected hadith/ayah in the top k (a tafsir hit counts as its ayah). MRR is computed over the top 10. All numbers below come from `python evaluate.py` runs (`runs/*.json`, not committed).

### Retrieval (78 scored questions)

| variant | R@1 | R@3 | R@10 | MRR |
|---|---|---|---|---|
| FTS only (BM25) | 0.269 | 0.462 | 0.590 | 0.378 |
| vector only (e5-small) | 0.333 | 0.449 | 0.577 | 0.405 |
| hybrid (RRF) | 0.359 | 0.526 | 0.692 | 0.465 |
| hybrid + reranker | 0.500 | 0.667 | 0.731 | 0.585 |
| hybrid + reranker + rules rewrites (default) | 0.526 | 0.679 | 0.756 | 0.608 |

- Reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`): 23 questions improve, 12 get worse. It costs about 1.4 s/query on CPU. It is on by default (`BASEERAH_RERANK=0` turns it off).
- Embedding the query with `norm()` instead of `clean()` hurts dense search (MRR 0.228 vs 0.405), because passages were embedded with `clean()`. So the dense side uses `clean()` and the lexical side uses `norm()`.
- Rules rewrites help only Gulf questions. Because the lexicon was written after the eval questions, they were re-checked on `eval_gulf_holdout.json` (19 Gulf questions written afterwards): with the reranker, R@1 0.211 → 0.263, MRR 0.251 → 0.278 (one question). **Unseen Gulf dialect remains the weakest area** (MRR ≈ 0.28 vs 0.65 for MSA).

### End to end, retrieval-only mode (`python evaluate.py --e2e legacy,hybrid+rerank`)

| pipeline | expected text shown (78) | out-of-scope rejected (8) |
|---|---|---|
| original `semantic_search` (women-specific hadith only) | 27 | 5 |
| hybrid + reranker, no rerank gate | 52 | 4 |
| hybrid + reranker + gate `T_RERANK=-2.5` (default) | 47 | 7 |

`T_RERANK` was picked on `calib_set.json` (the 14 questions in `evidence.py`'s `EVAL` plus 12 new out-of-scope ones), not on `eval_set.json`.

Known limits: in retrieval-only mode there is no LLM relevance check, so a text can be shown because it shares a key word (e.g. "وش أجر اللي يبني مسجد؟" returns 9:107 about masjid al-ḍirār). One out-of-scope question in the eval set ("منو فاز بمباراة الهلال امس؟") still gets texts. The personal-case question in `evidence.py eval` now gets "no evidence" instead of a referral.

### Fine-tuning (stage 6, optional, not adopted)

RAG itself does not train any model; `training/finetune.py` is the only training in this project. With no API key available, the 215 synthetic questions (`training/synthetic_questions.jsonl`, 168 hadith) were written by hand by the assistant. `training/sample.py` excludes every eval target and any hadith sharing a 4-gram or ≥50% word overlap with one. Epochs were chosen on a dev split of the synthetic pairs only (base 0.714 → epoch 1 0.738 → later epochs lower; `training/finetune_log.json`). Then the whole corpus was re-embedded with the model (`embeddings_ft.db`) and evaluated once:

| set / variant | base R@1 | FT R@1 | base R@10 | FT R@10 | base MRR | FT MRR |
|---|---|---|---|---|---|---|
| eval_set, vector only | 0.321 | 0.385 | 0.577 | 0.705 | 0.395 | 0.482 |
| eval_set, default pipeline | 0.526 | 0.551 | 0.756 | 0.769 | 0.608 | 0.623 |
| Gulf hold-out, vector only | 0.053 | 0.211 | 0.316 | 0.316 | 0.126 | 0.239 |
| Gulf hold-out, default pipeline | 0.263 | 0.211 | 0.368 | 0.368 | 0.278 | 0.257 |

Dense search alone improves clearly. In the default pipeline (hybrid + reranker), the change is +2 questions on eval_set and −1 on the Gulf hold-out, which is within noise. The evidence-gate thresholds are also calibrated to the base model's cosine scores. So the base model stays the default. Caveat: the same author wrote the training and eval questions, so even the dense-only gain may be optimistic. To reproduce: `python training/finetune.py`, then `python semantic.py embed --model models/e5-small-baseerah --vec embeddings_ft.db`, then `python evaluate.py --vec embeddings_ft.db`.
