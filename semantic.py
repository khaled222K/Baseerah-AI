import argparse, functools, re, sqlite3, sys, time
import numpy as np
from db import connect_ro

MODEL = "intfloat/multilingual-e5-small"
VEC_DB = "embeddings.db"
TASHKEEL = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
SKIP_COLS = re.compile(r"url|link|path|uuid|hash", re.I)


def clean(t):
    return re.sub(r"\s+", " ", TASHKEEL.sub("", str(t or ""))).strip()


def records_columns(db):
    cols = [r[1] for r in db.execute("PRAGMA table_info(records)")]
    rows = db.execute("SELECT * FROM records LIMIT 300").fetchall()
    avg = {}
    for i, c in enumerate(cols):
        vals = [r[i] for r in rows if isinstance(r[i], str)]
        if vals:
            avg[c] = sum(len(v) for v in vals) / len(vals)
    return cols, avg


def text_columns(db, override=None):
    if override:
        return override
    _, avg = records_columns(db)
    return [c for c, a in avg.items() if a > 15 and not SKIP_COLS.search(c)]


def show(db_path):
    db = connect_ro(db_path)
    cols, avg = records_columns(db)
    print("أعمدة جدول records:")
    for c in cols:
        print(f"  {c}  (متوسط الطول: {avg.get(c, 0):.0f})")
    print("الأعمدة النصية اللي بتدخل في البحث:", "، ".join(text_columns(db)))
    for r in db.execute("SELECT * FROM records LIMIT 3"):
        print({c: (str(v)[:70] if v is not None else None) for c, v in zip(cols, r)})
    print("عدد السجلات:", db.execute("SELECT count(*) FROM records").fetchone()[0])


@functools.lru_cache(maxsize=2)
def load_model(name):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(name)


def prefix(model_name, kind):
    return f"{kind}: " if "e5" in model_name.lower() else ""


def open_vec(path):
    v = sqlite3.connect(path, timeout=60)
    v.execute("CREATE TABLE IF NOT EXISTS vec(kind TEXT, ref_id INTEGER, v BLOB, PRIMARY KEY(kind, ref_id))")
    v.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
    return v


def collect(db, text_cols, hadith_scope="all"):
    items = []
    where = "" if hadith_scope == "all" else " WHERE women_relevance!='none'"
    for hid, shown, topic in db.execute("SELECT id, matn_display, topic FROM hadith" + where):
        items.append(("hadith", hid, clean(f"{topic or ''}. {shown}")))
    if text_cols:
        cols = ", ".join(f'"{c}"' for c in text_cols)
        merge = "text_search" in text_cols and "text_original" in text_cols
        for row in db.execute(f"SELECT rowid, {cols} FROM records"):
            vals = dict(zip(text_cols, row[1:]))
            if merge:
                txt = vals["text_search"] or vals["text_original"] or ""
                txt = " ".join([txt] + [str(v) for c, v in vals.items() if v and c not in ("text_search", "text_original")])
            else:
                txt = " ".join(str(x) for x in row[1:] if x)
            items.append(("records", row[0], clean(txt)[:1500]))
    return items


def embed(db_path, vec_path, model_name, text_cols, batch, hadith_scope="all"):
    db = connect_ro(db_path, timeout=60)
    cols = text_columns(db, text_cols)
    print("أعمدة records المستخدمة:", "، ".join(cols))
    items = collect(db, cols, hadith_scope)
    vdb = open_vec(vec_path)
    ensure_rfts(vdb, db)
    db.close()
    old = vdb.execute("SELECT v FROM meta WHERE k='model'").fetchone()
    if old and old[0] != model_name:
        sys.exit(f"الملف {vec_path} مبني بنموذج ثاني ({old[0]}). احذفه أو غيّر --vec")
    vdb.execute("INSERT OR REPLACE INTO meta VALUES('model', ?)", (model_name,))
    done = {(k, i) for k, i in vdb.execute("SELECT kind, ref_id FROM vec")}
    todo = [it for it in items if (it[0], it[1]) not in done]
    print(f"الإجمالي: {len(items)} | جاهز من قبل: {len(items) - len(todo)} | المتبقي: {len(todo)}")
    if not todo:
        return
    model = load_model(model_name)
    model.max_seq_length = 384
    pre = prefix(model_name, "passage")
    t0 = time.time()
    for s in range(0, len(todo), batch):
        part = todo[s:s + batch]
        vecs = model.encode([pre + t for _, _, t in part], batch_size=batch, normalize_embeddings=True,
                            show_progress_bar=False)
        vdb.executemany("INSERT OR REPLACE INTO vec VALUES(?,?,?)",
                        [(k, i, np.asarray(v, dtype=np.float32).tobytes()) for (k, i, _), v in zip(part, vecs)])
        if (s // batch) % 10 == 9 or s + batch >= len(todo):
            vdb.commit()
            n = min(s + batch, len(todo))
            rate = n / (time.time() - t0)
            print(f"{n}/{len(todo)}  (باقي حوالي {int((len(todo) - n) / rate / 60)} دقيقة)")
    vdb.commit()
    print("انتهى.")


def load_vectors(vdb, kind):
    rows = vdb.execute("SELECT ref_id, v FROM vec WHERE kind=?", (kind,)).fetchall()
    if not rows:
        return [], np.zeros((0, 1), dtype=np.float32)
    return [r[0] for r in rows], np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])


GENERIC = {"حكم", "احكام", "حكمه", "يجوز", "يجب", "ماذا", "لماذا", "كيف", "هل", "معني", "تعريف", "اريد", "ابي"}
QURAN_WORDS = {"قران", "ايه", "ايات", "الايات", "كريم", "سوره", "قرانيه"}


def terms_query(query, skip=()):
    from build_hadith_db import fts_query
    terms = [t for t in re.findall(r'"([^"]+)"', fts_query(query)) if t not in GENERIC and t not in skip]
    return " OR ".join(f'"{t}"' for t in terms)


def fts_ids(db, query, n):
    q = terms_query(query)
    if not q:
        return []
    try:
        return [r[0] for r in db.execute(
            "SELECT h.id FROM hadith_fts JOIN hadith h ON h.id=hadith_fts.rowid "
            "WHERE hadith_fts MATCH ? AND h.women_relevance='specific' ORDER BY rank LIMIT ?", (q, n))]
    except Exception:
        return []


def ensure_rfts(vdb, db):
    from build_hadith_db import norm, strip_al
    vdb.execute("CREATE VIRTUAL TABLE IF NOT EXISTS rfts USING fts5(txt, tokenize='unicode61')")
    if vdb.execute("SELECT count(*) FROM rfts").fetchone()[0]:
        return
    names = [r[1] for r in db.execute("PRAGMA table_info(records)")]
    cols = [c for c in names if c in ("text_search", "text_original")] or text_columns(db)
    pick = "text_search" if "text_search" in cols else cols[0]
    fallback = "text_original" if "text_original" in cols else pick
    rows = db.execute(f'SELECT rowid, "{pick}", "{fallback}" FROM records').fetchall()
    vdb.executemany("INSERT INTO rfts(rowid, txt) VALUES(?,?)",
                    [(r, " ".join(strip_al(t) for t in norm(a or b or "").split())) for r, a, b in rows])
    vdb.commit()


def records_fts_ids(vdb, query, n):
    q = terms_query(query, QURAN_WORDS)
    if not q:
        return []
    try:
        return [r[0] for r in vdb.execute("SELECT rowid FROM rfts WHERE rfts MATCH ? ORDER BY rank LIMIT ?", (q, n))]
    except Exception:
        return []


def semantic_search(db_path, vec_path, query, k=5, pool=30):
    db = connect_ro(db_path, timeout=60)
    vdb = connect_ro(vec_path, timeout=60)
    model_name = vdb.execute("SELECT v FROM meta WHERE k='model'").fetchone()[0]
    model = load_model(model_name)
    q = model.encode([prefix(model_name, "query") + clean(query)], normalize_embeddings=True)[0].astype(np.float32)

    ids, mat = load_vectors(vdb, "hadith")
    allowed = {r[0] for r in db.execute("SELECT id FROM hadith WHERE women_relevance='specific'")}
    keep = [j for j, i in enumerate(ids) if i in allowed]
    ids = [ids[j] for j in keep]
    sims = mat[keep] @ q if keep else np.array([])
    order = np.argsort(-sims)[:pool]
    sem = [(ids[j], float(sims[j])) for j in order]
    score_of = dict(sem)
    fused = {}
    for rank, (i, _) in enumerate(sem):
        fused[i] = fused.get(i, 0) + 1 / (60 + rank)
    lex_h = fts_ids(db, query, pool)
    for rank, i in enumerate(lex_h):
        fused[i] = fused.get(i, 0) + 1 / (60 + rank)
        if i not in score_of and i in ids:
            score_of[i] = float(sims[ids.index(i)])
    top = sorted(fused, key=fused.get, reverse=True)[:k]
    hadith = []
    for i in top:
        r = db.execute("SELECT topic, source_ref, matn_display, grade, dorar_grade, dorar_muhaddith, dorar_url "
                       "FROM hadith WHERE id=?", (i,)).fetchone()
        hadith.append({"id": i, "similarity": round(score_of.get(i, 0.0), 3), "topic": r[0], "source": r[1],
                       "text": r[2], "grade": r[3], "dorar_grade": r[4], "dorar_muhaddith": r[5], "link": r[6],
                       "lex": i in lex_h})

    rids, rmat = load_vectors(vdb, "records")
    records = []
    if rids:
        rs = rmat @ q
        if not vdb.execute("SELECT 1 FROM sqlite_master WHERE name='rfts'").fetchone():
            raise RuntimeError(f"فهرس rfts غير موجود في {vec_path}. شغّل: python semantic.py embed")
        names = [d[0] for d in db.execute("SELECT * FROM records LIMIT 0").description]
        kinds = dict(db.execute("SELECT rowid, type FROM records")) if "type" in names else {}
        pos = {rid: j for j, rid in enumerate(rids)}
        fused = {}
        for rank, j in enumerate(np.argsort(-rs)[:pool]):
            fused[rids[j]] = fused.get(rids[j], 0) + 1 / (60 + rank)
        lex_r = records_fts_ids(vdb, query, pool)
        for rank, rid in enumerate(lex_r):
            if rid in pos:
                fused[rid] = fused.get(rid, 0) + 1 / (60 + rank)
        count = {}
        for rid in sorted(fused, key=fused.get, reverse=True):
            kind = kinds.get(rid)
            if count.get(kind, 0) >= k:
                continue
            count[kind] = count.get(kind, 0) + 1
            row = db.execute("SELECT * FROM records WHERE rowid=?", (rid,)).fetchone()
            records.append({"id": rid, "type": kind, "lex": rid in lex_r, "similarity": round(float(rs[pos[rid]]), 3),
                            "fields": {n: v for n, v in zip(names, row)}})
    return {"hadith": hadith, "records": records}


def print_results(res):
    print("\n=== الأحاديث ===")
    for h in res["hadith"]:
        print(f"\n[{h['topic']}] تشابه {h['similarity']} | {h['source']}")
        print("  " + h["text"][:300])
        dorar = f" | الدرر: {h['dorar_grade']} ({h['dorar_muhaddith']})" if h["dorar_grade"] and h["dorar_muhaddith"] else ""
        print(f"  الحكم: {h['grade']}{dorar}")
    print("\n=== القرآن والتفسير ===")
    for r in res["records"]:
        f = r["fields"]
        text = f.get("text_search") or f.get("text_original") or ""
        print(f"\n[{r['type']}] تشابه {r['similarity']} | {f.get('reference')}")
        print("  " + str(text)[:250])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["show", "embed", "search"])
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--vec", default=VEC_DB)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--text-cols", default="")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--hadith-scope", choices=["all", "women"], default="all")
    ap.add_argument("--query", default="")
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args()
    if a.cmd == "show":
        show(a.db)
    elif a.cmd == "embed":
        embed(a.db, a.vec, a.model, [c for c in a.text_cols.split(",") if c], a.batch, a.hadith_scope)
    else:
        print_results(semantic_search(a.db, a.vec, a.query, a.k))
