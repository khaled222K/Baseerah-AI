# Baseerah (بصيرة)

**إجابةٌ تستند إلى أصل. محتوى شرعي قابل للتتبع إلى مصدره.**

Baseerah answers Islamic questions, mainly questions women ask, by showing the original texts with their references:
- hadith from Sahih al-Bukhari and Sahih Muslim;
- Quran ayat;
- Tafsir al-Muyassar.

Search is fully local (SQLite FTS5 plus dense vectors); nothing is looked up on the internet. A language model may add a
short explanation, but it never writes the texts.

> **Disclaimer.** Baseerah is AI-assisted and is **not** a qualified religious scholar (ليست من مختص شرعي).
> - **Texts:** every hadith, ayah and tafsir shown is copied verbatim from the database by ID.
> - **Personal cases:** questions about a personal case are referred to scholars.

- **Live demo:** https://baseerah-ai-sigma.vercel.app
  - The website is hosted on Vercel; the API runs on the team's computer through ngrok.
  - The site answers only while that computer is on (see [docs/DEPLOY_VERCEL.md](docs/DEPLOY_VERCEL.md)).
- **Challenge:** AI Challenge: Serving Islamic Content (تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي), October 2026.

## نبذة بالعربية

**الفكرة:** بصيرة أداة تجيب عن الأسئلة الشرعية، وخصوصاً أسئلة المرأة، بعرض النصوص الأصلية بلفظها ومرجعها ورابطها. لا تعرض
إجابة مولَّدة بلا دليل.

**المصادر:** صحيح البخاري، وصحيح مسلم، والقرآن الكريم، والتفسير الميسّر. كلها مخزّنة في قاعدة بيانات محلية، ولا يُبحث في
الإنترنت.

**طريقة العمل:**
1. تبحث بصيرة بالكلمات وبالمعنى.
2. تعيد ترتيب النتائج حسب الصلة بالسؤال.
3. تفحص كفاية الدليل.
4. إن لم تجد نصاً مناسباً، تقول ذلك صراحةً.
5. الأسئلة عن حالة شخصية تُحال إلى أهل العلم.

**الشرح المولَّد:**
- يكتبه نموذج لغوي محلي جاهز (لم ندرّب نموذجاً من الصفر).
- يظهر دائماً بجانب النص الأصلي.
- يُحذف إذا اقتبس كلاماً غير موجود في النصوص المعروضة.

**أدوات الموقع:**
- **اسألي بصيرة:** سؤال وجواب مع النصوص ومراجعها.
- **تحقّقي من دليل:** تلصقين نصاً منسوباً فتطابقه بصيرة حرفياً مع المخزَّن، دون توليد.
- **المصادر والموثوقية:** المصادر وأعدادها وأساس الحكم على الأحاديث.
- **عن النموذج:** الإعدادات الفعلية للخادم.

**الخصوصية:** لا يوجد حساب ولا تسجيل دخول، والمحادثات تُحفظ في متصفح المستخدمة فقط.

## Contents

- [Team](#team)
- [Quick start](#quick-start)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Data](#data)
- [Evaluation](#evaluation)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Licenses and attribution](#licenses-and-attribution)
- [Known limits](#known-limits)

## Team

| name | role |
|---|---|
| Hoor Fawaz Alotaibi (حور فواز العتيبي) | data and knowledge base: collecting, cleaning and classifying the sources |
| Khalid Fawaz Alotaibi (خالد فواز العتيبي) | AI and backend: retrieval, model integration, linking to the database |
| Danah Fawaz Alotaibi (دانة فواز العتيبي) | frontend and user experience, linking it to the backend, data preparation |

### Timeline

| date | work |
|---|---|
| before Oct 4 | idea and planning only, no code |
| Oct 4 | knowledge base: Quran, tafsir, hadith collection |
| Oct 5 | retrieval, grades and links, evidence-sufficiency test (12/14) |
| Oct 6 | model integration, website, live demo, tests, public repo |

## Quick start

**Requirements:**
- Python 3.11 or newer (tested on 3.12 and 3.13);
- Git LFS;
- about 2 GB of RAM for retrieval only;
- about 8 GB more for the optional local model.

```bash
git clone https://github.com/khaled222K/Baseerah-AI.git && cd Baseerah-AI
git lfs install && git lfs pull          # baseerah.db and embeddings.db are stored with Git LFS
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python scripts/fetch_models.py           # downloads the two retrieval models once
```

**Run the website and the API on one address:**

```bash
BASEERAH_SERVE_FRONTEND=1 BASEERAH_LLM=retrieval uvicorn api:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

`BASEERAH_LLM=retrieval` shows the stored texts only, with no model, key or GPU. It answers in a few seconds and never
shows generated content.

### Optional: AI explanations

You can add AI explanations with a local model (free, no key):
1. Install [Ollama](https://ollama.com).
2. Run `ollama pull aya-expanse:8b` (about 5 GB).
3. Run `cp .env.example .env`. Option A in that file is already set for this model.

Or use the Anthropic API:
1. In `.env`, set `BASEERAH_LLM=anthropic`.
2. Paste your key after `ANTHROPIC_API_KEY=`.

`.env` is git-ignored: never commit it.

| model | measured result | license |
|---|---|---|
| `aya-expanse:8b` (default local) | best Arabic of the tested local models; still misreads some texts (see [docs/BENCHMARK.md](docs/BENCHMARK.md)) | CC-BY-NC 4.0 (non-commercial) |
| `qwen2.5:7b` | 3/3 correct hadith explanations | Apache 2.0 |
| `qwen2.5:3b` | not usable (garbled words, reversed one hadith's meaning) | — |
| `claude-sonnet-5-5` (Anthropic API) | default for `BASEERAH_LLM=anthropic` | Anthropic commercial terms |

On a 4-core CPU without a GPU, the local 8B model takes 30–90 s per answer.

**For a public demo, we recommend retrieval-only mode.** The quotation and script checks catch:
- invented quotes;
- garbled output;
- foreign scripts.

They cannot catch a fluent sentence that misreads a text. That is why the texts are always shown next to the explanation.

## Usage

**Command line:**

```bash
python ask.py "ما حق الجار في الإسلام؟"                    # retrieval only (no model, no key)
python ask.py "وش أركان الإسلام؟" --mode anthropic          # explanation via the Anthropic API
BASEERAH_LLM=openai BASEERAH_BASE_URL=http://localhost:11434/v1 BASEERAH_MODEL=aya-expanse:8b \
  python ask.py "كم عدة المطلقة؟"                           # local OpenAI-compatible server (Ollama, llama.cpp…)
python ask.py "ليس الشديد بالصرعة" --json                   # identifies the hadith being quoted
```

**API:** start it with `uvicorn api:app --port 8000`.

| endpoint | purpose |
|---|---|
| `POST /chat` | the website's question → answer (texts, references, optional explanation) |
| `GET /ask?q=…` / `POST /ask` | the same pipeline, raw output |
| `POST /verify` | compares a pasted text with the stored ayat/hadith, word for word (nothing generated) |
| `POST /explain` | short explanation of one stored hadith (needs an LLM) |
| `GET /sources` | source counts and grade basis |
| `GET /model-info` | the server's live settings (models, thresholds, offline state) |
| `GET /health` | health check |

**Choosing the mode:** without `--mode`, `ask.py` and the API use `BASEERAH_LLM` if it is set, otherwise retrieval-only
mode.

**If the model fails:** if it is unreachable, slow or returns bad output, the texts are still shown, with a notice and no
explanation.

### Settings (environment variables or `.env`)

| variable | default | meaning |
|---|---|---|
| `BASEERAH_LLM` | `retrieval` | `retrieval`, `openai` (any OpenAI-compatible server, e.g. Ollama) or `anthropic` |
| `BASEERAH_BASE_URL` | — | URL of the OpenAI-compatible server, e.g. `http://localhost:11434/v1` |
| `BASEERAH_MODEL` | `claude-sonnet-5-5` | model name for the chosen backend |
| `ANTHROPIC_API_KEY` | — | only for `anthropic` |
| `BASEERAH_LLM_TIMEOUT` | 240 s (local) | per-call timeout for the model |
| `BASEERAH_TIMEOUT_MS` | 90000; 300000 with a local model | how long the website waits for an answer (ms) |
| `BASEERAH_RERANK` | `1` | `0` turns the reranker off |
| `BASEERAH_UNDERSTAND` | `rules` with a local model | how questions are rewritten: `rules`, `anthropic` or `openai` |
| `BASEERAH_EXPLAIN_WORDS` | off with a local model | `1` adds word glosses in "اشرح الحديث" |
| `BASEERAH_FALLBACKS` | `1` | Anthropic server-side refusal fallback |
| `BASEERAH_CORS_ORIGINS` | localhost | allowed website origins, comma-separated |
| `BASEERAH_SERVE_FRONTEND` | off | `1` serves `frontend/` from the API on the same address |
| `BASEERAH_DB`, `BASEERAH_VEC` | `baseerah.db`, `embeddings.db` | database paths |

## How it works

```
question ─► 1 understand ─► 2 identify ─► 3 hybrid retrieval ─► 4 evidence gate ─► 5 optional explanation ─► texts + references
```

1. **Query understanding** (`understand.py`):
   - The question, in Gulf dialect, MSA or English religious terms, becomes formal-Arabic search rewrites and keywords.
   - The default `rules` backend uses a Gulf→MSA lexicon and needs no model.
   - Rewrites are used for search only and are never displayed.
2. **Hadith identification** (`identify.py`):
   - Triggered when the user types part of a hadith or describes one.
   - Candidates are scored with `SequenceMatcher` against the normalized matn.
3. **Hybrid retrieval** (`retrieve.py`):
   - BM25 over `hadith_fts` and `rfts`, plus dense `multilingual-e5-small` search over all 27,208 vectors.
   - The two lists are fused with Reciprocal Rank Fusion (k=60).
   - A multilingual cross-encoder reranks the top 30, scoring each passage against the question and up to 2 rewrites.
4. **Evidence gate** (`evidence.py`):
   - A text is shown only if:
     - its reranker score is at least −2.5; and
     - its cosine similarity is at least 0.92, or at least 0.80 with a shared search word.
   - Otherwise the answer is: «لم أجد نصاً مباشراً مرتبطاً بالسؤال في المصادر المتاحة…».
   - Personal-case questions always get a referral to scholars, and no generated explanation.
5. **Explanation** (`answer.py`, optional):
   - The model may only pick IDs of retrieved texts and write a short explanation.
   - The explanation is dropped if it quotes text that is not in the displayed passages, or contains Latin or CJK letters.
6. **Verification** (`check.py`, `verify.py`):
   - Pasted text is compared with the stored wording.
   - An ayah counts as matched only if its wording is one exact contiguous run.
   - An ayah with a changed word gets a warning and the authentic ayah with its reference.

Details of every setting, fallback and safety check: [docs/AUDIT.md](docs/AUDIT.md).

## Data

| file | contents |
|---|---|
| `baseerah.db` | `records` (6,236 ayat + 6,236 tafsir entries), `hadith` (14,736: Bukhari 7,277 + Muslim 7,459), `weak_hadith`, `hadith_notes` (20), FTS5 indexes `records_fts`, `hadith_fts` |
| `embeddings.db` | `vec(kind, ref_id, v)`: float32 e5 vectors for all 27,208 texts, `meta`, and `rfts` (FTS5 over normalized text) |

**Women-related hadith:** 1,277 hadith are tagged as related to women:
- 875 women-specific;
- 402 general.

**Dorar grades:** 904 hadith carry the grade found on dorar.net.

**Read-only at runtime:** all runtime code opens both databases read-only (`mode=ro`, see `db.py`). Only the maintainer
build steps write:
- `python semantic.py embed`: writes the vectors and `rfts` into `embeddings.db`.
- `python build_hadith_db.py build|dorar`: rebuilds or enriches the `hadith` table. Not needed for normal use.
- `data_build/load_quran.py` and `data_build/load_tafsir.py`:
  - rebuild `records` from `Quran.json` and `Tafsir.csv` into a separate `data_build/baseerah.db`;
  - the `url` column of the shipped database was filled in separately.

**Hadith numbering** follows the hadith-json dataset and can differ from printed editions; the output says so.

## Evaluation

All numbers below come from actual runs of `python evaluate.py` on `eval_set.json`.

**The set has 86 questions:**

| type | count |
|---|---|
| hadith topic questions | 44 |
| ayah questions | 24 |
| quotes or paraphrases of hadith | 10 |
| out of scope | 8 |

- **Language:** 33 are in Gulf dialect and 53 in MSA.
- **Expected IDs:** each expected ID was checked by reading its text in `baseerah.db`.
- **Lower bound:** an expected list can miss other narrations of the same hadith, so the scores are a lower bound.

**Measures:**
- **Recall@k:** share of questions with at least one expected text in the top k (a tafsir hit counts as its ayah).
- **MRR:** computed over the top 10.
- **Margin of error:** with 78 scored questions, it is roughly ±11 points.

### Retrieval (78 scored questions)

| variant | R@1 | R@3 | R@10 | MRR |
|---|---|---|---|---|
| FTS only (BM25) | 0.269 | 0.462 | 0.590 | 0.378 |
| vector only (e5-small) | 0.333 | 0.449 | 0.577 | 0.405 |
| hybrid (RRF) | 0.359 | 0.526 | 0.692 | 0.465 |
| hybrid + reranker | 0.500 | 0.667 | 0.731 | 0.585 |
| **hybrid + reranker + rules rewrites (default)** | **0.526** | **0.667** | **0.769** | **0.607** |

- **Reranker:**
  - 23 questions improve and 12 get worse.
  - It costs about 1.4 s per query on CPU.
- **Rewrites:** the reranker scores each passage against the question and up to 2 rewrites and keeps the best score.
  - Before this change, the default row was R@3 0.679, R@10 0.756, MRR 0.608.
  - End-to-end numbers did not change.
- **Query normalization:** the dense side embeds the query with `clean()`, not `norm()`, because the passages were
  embedded with `clean()`. Using `norm()` drops dense MRR from 0.405 to 0.228.
- **Unseen Gulf dialect is the weakest area:**
  - MRR is about 0.28, against about 0.65 for MSA.
  - This was measured on `eval_gulf_holdout.json`: 19 Gulf questions written after the lexicon.

### End to end, retrieval-only mode (`python evaluate.py --e2e legacy,hybrid+rerank`)

| pipeline | expected text shown (78) | out of scope rejected (8) |
|---|---|---|
| original `semantic_search` (women-specific hadith only) | 27 | 5 |
| hybrid + reranker, no rerank gate | 52 | 4 |
| **hybrid + reranker + gate `T_RERANK=-2.5` (default)** | **47** | **7** |

**Evidence-sufficiency test:** 12/14 correct decisions (answer, abstain or refer) on the questions in `evidence.py eval`.

**How the gate threshold was chosen:** `T_RERANK` was picked on `calib_set.json` (26 questions, 22/26 correct), not on
`eval_set.json`.

### Edge-case benchmark

`benchmark/cases.json` has 17 cases:
- 12 edge cases: false premises, hostile tone, consensus questions, an altered ayah, a request for a hadith that does not
  exist, a personal case, and English questions;
- the site's 5 suggested questions.

**Results** (my judgement against each case's expected behavior):

| mode | strict passes | wrong content |
|---|---|---|
| retrieval-only | 5/17 | never showed invented content |
| `aya-expanse:8b` | 4/17 | wrong or unsupported content in 4 answers |

Full outputs and the fixes they led to: [docs/BENCHMARK.md](docs/BENCHMARK.md).

**To reproduce:** `python scripts/run_benchmark.py [--mode openai]`.

### Fine-tuning (optional experiment, not adopted)

**Training in this project:**
- RAG does not train any model.
- `training/finetune.py` is the only training in this project.
- The training data is 215 synthetic questions (`training/synthetic_questions.jsonl`).
- `training/sample.py` excludes every eval target and any near-duplicate of one.

**Effect of fine-tuning e5-small on these questions:**

| setting | MRR before | MRR after | R@10 before | R@10 after |
|---|---|---|---|---|
| dense search alone | 0.395 | 0.482 | 0.577 | 0.705 |
| default pipeline | 0.608 | 0.623 | 0.756 | 0.769 |
| Gulf hold-out (default pipeline) | 0.278 | 0.257 | 0.368 | 0.368 |

The gain in the default pipeline is within noise, so the base model stays the default.

**To reproduce:**
1. `python training/finetune.py`
2. `python semantic.py embed --model models/e5-small-baseerah --vec embeddings_ft.db`
3. `python evaluate.py --vec embeddings_ft.db`

## Project layout

```
api.py              FastAPI server: /chat /ask /verify /explain /sources /model-info /health
answer.py           full pipeline: understand → retrieve → evidence gate → optional LLM explanation + quote checks
understand.py       question rewriting (Gulf→MSA lexicon, English religious terms, request framing)
identify.py         identifies a quoted or described hadith
retrieve.py         hybrid search (FTS5 BM25 + e5 vectors, RRF) and cross-encoder reranking
semantic.py         e5 embeddings: search and the maintainer `embed` command
evidence.py         evidence gate, referral of personal cases, user messages
explain.py          "اشرح الحديث": grounded explanation of one hadith
check.py, verify.py word-for-word verification of pasted ayat and hadith
db.py               read-only SQLite connections
envfile.py          loads .env; switches Hugging Face to offline when the models are cached
ask.py              command line
evaluate.py         retrieval and end-to-end evaluation
build_hadith_db.py  maintainer tool: builds the hadith table, adds dorar.net grades
baseerah.db, embeddings.db              the data (Git LFS)
eval_set.json, calib_set.json, eval_gulf_holdout.json, eval_metrics.json   evaluation sets and latest metrics
data_build/         Quran.json, Tafsir.csv and their loaders
frontend/           static RTL website (HTML, CSS, vanilla JS, no build step); see docs/FRONTEND.md
benchmark/          edge-case questions and saved outputs
training/           optional fine-tuning experiment (not adopted)
scripts/            fetch_models.py, run_benchmark.py, export_metrics.py
tests/              pytest suite
docs/               AUDIT.md, BENCHMARK.md, FRONTEND.md, DEPLOY_VERCEL.md
vercel.json, render.yaml   website on Vercel; optional full deployment on Render
```

## Tests

```bash
python -m pytest -q                     # pipeline, API, verification, benchmark guards, offline guard
python frontend/tests/ui_test.py        # 39 browser checks (Playwright); see its docstring for the 3 local servers it needs
```

**What the tests lock:**
- every displayed text equals the stored one;
- personal cases are referred;
- altered ayat are flagged;
- the model's failure falls back to the texts;
- the API reports read-only database access.

Latest run: 46 passed.

## Licenses and attribution

**Baseerah's own code and documentation:** MIT License (see [LICENSE](LICENSE)). It does not cover the texts, data or
models below.

**Third-party parts** keep their own licenses:

| component | used for | license / terms |
|---|---|---|
| [hadith-json](https://github.com/AhmedBaset/hadith-json) (Sahih al-Bukhari, Sahih Muslim) | hadith texts and numbering | ISC (per the project's `package.json`) |
| Quran text (Hafs) and Tafsir al-Muyassar: King Fahd Glorious Quran Printing Complex data files | ayat and tafsir | KFGQPC terms of use; texts are used unmodified |
| [dorar.net](https://dorar.net) | grade and link shown for 904 hadith | content belongs to dorar.net; Baseerah stores the grade and links to the source, it does not fetch at runtime |
| [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | dense search | MIT |
| [cross-encoder/mmarco-mMiniLMv2-L12-H384-v1](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1) | reranking | Apache 2.0 |
| `aya-expanse:8b` (Cohere For AI), through Ollama | optional local explanations | CC-BY-NC 4.0: **non-commercial use only** |
| `qwen2.5:7b` (alternative local model) | optional local explanations | Apache 2.0 |
| Anthropic API (optional) | optional explanations | Anthropic commercial terms; needs your own key |
| IBM Plex Sans Arabic, Alexandria (Google Fonts) | website fonts | SIL Open Font License 1.1 |
| Python libraries (`requirements.txt`): FastAPI, sentence-transformers, PyTorch, NumPy… | runtime | each under its own open-source license |

**Commercial use** needs:
- a model other than `aya-expanse` (for example `qwen2.5:7b`, or retrieval-only mode);
- a check of the KFGQPC and dorar.net terms.

## Known limits

- **Corpus:** Bukhari, Muslim, the Quran and al-Muyassar only.
  - There are no fiqh, sīra or history sources.
  - Questions about consensus, scholarly disagreement or history get "no direct text", or loosely related texts.
- **Retrieval-only mode** has no relevance check by a model. A text can appear because it shares a key word with the
  question.
- **The local 8B model can misread a text** while writing fluent Arabic. The texts are always shown next to its
  explanation, and it is labeled "شرح مولَّد بالذكاء الاصطناعي (ليس نصاً شرعياً)".
- **Evaluation sets are small** (86 questions), and the same team wrote the lexicon and the questions.
  - The scores can be optimistic.
  - The Gulf hold-out set is the fairer measure for dialect questions.
- **Live demo:** it runs only while the team's computer, the API and ngrok are on.
