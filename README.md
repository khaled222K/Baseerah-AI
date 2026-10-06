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
