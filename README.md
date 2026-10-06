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
3. **Hybrid retrieval** (`retrieve.py`): BM25 over `hadith_fts` and `rfts`, plus dense e5 search over all vectors, fused with Reciprocal Rank Fusion (k=60). The query and each rewrite add their own ranked lists. An optional multilingual cross-encoder reranker is behind `--rerank`.
4. **Evidence gate** (`evidence.py`): a hit is shown only if it passes the existing similarity thresholds. If nothing passes: "لم أجد نصاً مباشراً مرتبطاً بالسؤال في المصادر المتاحة…". Personal-case questions are referred to scholars.
5. **Explanation** (`answer.py`, modes b/c): the LLM may only pick IDs among the retrieved texts and write a short explanation. Any explanation that quotes text not present in the displayed passages is dropped (`quotes_ok`, using `verify.MARKS`).
