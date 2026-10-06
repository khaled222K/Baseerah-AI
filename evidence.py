import argparse, re, sqlite3
from build_hadith_db import norm, strip_al, hadith_link, fts_query
from semantic import semantic_search, GENERIC
from verify import note_of

DB = "baseerah.db"
VEC = "embeddings.db"
TAFSIR_NAME = "التفسير الميسر (مجمع الملك فهد)"
T_LEX = 0.80
T_HIGH = 0.92
PERSONAL = [
    "انا", "عندي", "حصل لي", "صار لي", "صارلي", "زوجي", "زوجتي", "حالتي", "وضعي", "هل يجوز لي",
    "هل يصح لي", "هل علي", "صلاتي", "صيامي", "حجي", "عمرتي", "ماذا افعل", "وش اسوي", "ايش اسوي",
    "اطلقني", "طلقني", "طلقتها", "اهلي", "ابوي", "امي",
]
MESSAGES = {
    "answer": "وُجدت نصوص مرتبطة بالسؤال. تُعرض كما هي مع مصدرها وحكمها، والتوسع فيها شرحٌ مولَّد وليس نصاً شرعياً.",
    "referral": "وُجدت نصوص عامة مرتبطة بالموضوع، لكن السؤال يخص حالة شخصية، ولا يستقل النظام بالفتوى. يُرجى سؤال أهل العلم أو جهة الفتوى المختصة.",
    "clarify": "السؤال قصير ولا يكفي لتحديد المقصود. يرجى كتابة سؤالك بجملة كاملة.",
    "insufficient": "لم أجد نصاً مباشراً مرتبطاً بالسؤال في المصادر المتاحة، ولن أجتهد في الجواب. يمكن إعادة صياغة السؤال أو سؤال أهل العلم.",
}


def is_personal(query):
    q = " " + norm(query) + " "
    return any(f" {p} " in q for p in PERSONAL)


def ayah_of(db, surah, ayah):
    r = db.execute("SELECT reference, text_original, url FROM records WHERE source='quran' "
                   "AND CAST(surah_no AS INTEGER)=? AND CAST(ayah_no AS INTEGER)=?", (int(surah), int(ayah))).fetchone()
    return {"kind": "ayah", "ref": r[0], "text": r[1], "url": r[2], "source": "القرآن الكريم (مجمع الملك فهد)"} if r else None


def coverage(query, text):
    terms = [t for t in re.findall(r'"([^"]+)"', fts_query(query)) if t not in GENERIC]
    if not terms:
        return 0.0
    words = {strip_al(w) for w in norm(text or "").split()}
    return round(sum(t in words for t in terms) / len(terms), 2)


def accepted(item):
    return item["similarity"] >= T_HIGH or (item["lex"] and item["similarity"] >= T_LEX)


def assess(query, db_path=DB, vec_path=VEC, k=5):
    if len(norm(query).split()) < 2:
        return {"status": "clarify", "message": MESSAGES["clarify"], "evidence": [], "raw": []}
    res = semantic_search(db_path, vec_path, query, k)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    evidence, seen = [], set()
    for h in res["hadith"]:
        if not accepted(h):
            continue
        row = db.execute("SELECT * FROM hadith WHERE id=?", (h["id"],)).fetchone()
        dorar = None
        if row["dorar_grade"] and row["dorar_grade"] != "لم يُطابَق":
            dorar = {"grade": row["dorar_grade"], "muhaddith": row["dorar_muhaddith"]}
        evidence.append({"kind": "hadith", "ref": h["source"], "text": h["text"], "topic": h["topic"],
                         "grade": row["grade"], "grade_basis": row["grade_source"], "dorar": dorar,
                         "link": hadith_link(row), "note": note_of(db, h["id"]), "similarity": h["similarity"], "lex": h["lex"],
                         "coverage": coverage(query, h["text"])})
    for r in res["records"]:
        f = r["fields"]
        if r["type"] == "tafsir" and accepted(r):
            ay = ayah_of(db, f["surah_no"], f["ayah_no"])
            evidence.append({"kind": "tafsir", "ref": f["reference"], "text": f["text_original"], "url": f["url"],
                             "source": TAFSIR_NAME, "similarity": r["similarity"], "lex": r["lex"],
                             "coverage": coverage(query, f["text_search"]), "ayah": ay})
        elif r["type"] == "ayah" and r["lex"] and r["similarity"] >= T_LEX and ("ayah", f["reference"]) not in seen:
            seen.add(("ayah", f["reference"]))
            evidence.append({"kind": "ayah", "ref": f["reference"], "text": f["text_original"], "url": f["url"],
                             "source": "القرآن الكريم (مجمع الملك فهد)", "similarity": r["similarity"], "lex": True,
                             "coverage": coverage(query, f["text_search"])})
    if not evidence:
        status = "insufficient"
    elif is_personal(query):
        status = "referral"
    else:
        status = "answer"
    raw = [(x["similarity"], x["lex"]) for x in res["hadith"]] + [(x["similarity"], x["lex"]) for x in res["records"] if x["type"] == "tafsir"]
    return {"status": status, "message": MESSAGES[status], "evidence": evidence, "raw": raw}


EVAL = [
    ("حكم الحائض والصلاة", "answer"),
    ("هل يجوز للحائض قراءة القرآن", "answer"),
    ("حكم سفر المرأة بدون محرم", "answer"),
    ("حقوق الزوجة على زوجها", "answer"),
    ("عدة المطلقة", "answer"),
    ("ما هو الخلع", "answer"),
    ("الدورة الشهرية هل تمنع الصيام", "answer"),
    ("حكم لبس الحجاب", "answer"),
    ("ما هي عاصمة فرنسا", "insufficient"),
    ("كيف اطبخ الكبسة", "insufficient"),
    ("سعر الذهب اليوم", "insufficient"),
    ("حكم الزكاة في الاسهم", "insufficient"),
    ("انا حائض ونزل مني دم بعد الطهر هل صلاتي صحيحة", "referral"),
    ("زوجي طلقني وانا حامل هل تلزمني العدة", "referral"),
]


def run_eval(db_path, vec_path):
    ok = 0
    for q, want in EVAL:
        a = assess(q, db_path, vec_path)
        got = a["status"]
        ok += got == want
        ev = a["evidence"]
        kinds = " ".join(f"{k}:{sum(1 for e in ev if e['kind'] == k)}" for k in ("hadith", "tafsir", "ayah"))
        top = sorted(a["raw"], reverse=True)[:3]
        raw = " ".join(f"{s}{'*' if lx else ''}" for s, lx in top)
        print(f"{'✓' if got == want else '✗'} {q} | المتوقع: {want} | الناتج: {got} | {kinds} | أعلى الدرجات: {raw}")
    print(f"\nصحيح: {ok} من {len(EVAL)}")


def show(a):
    print(f"\nالحالة: {a['status']}\n{a['message']}")
    for e in a["evidence"]:
        print(f"\n[{e['kind']}] {e['ref']} | تشابه {e['similarity']} | كلمات: {e['lex']} | تغطية: {e['coverage']}")
        print("  " + (e["text"] or "")[:250])
        if e["kind"] == "hadith":
            d = f" | الدرر: {e['dorar']['grade']} ({e['dorar']['muhaddith']})" if e["dorar"] else ""
            print(f"  الحكم: {e['grade']}{d} | {e['link']['url']}")
            if e.get("note") and e["note"]["text"]:
                print(f"  التوضيح ({e['note']['source']}): {e['note']['text']}")
        else:
            print(f"  المصدر: {e['source']} | {e['url']}")
        if e.get("ayah"):
            print(f"  الآية: {e['ayah']['ref']} | {e['ayah']['text']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["ask", "eval"])
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--vec", default=VEC)
    ap.add_argument("--t-lex", type=float, default=T_LEX)
    ap.add_argument("--t-high", type=float, default=T_HIGH)
    a = ap.parse_args()
    T_LEX, T_HIGH = a.t_lex, a.t_high
    if a.cmd == "eval":
        run_eval(a.db, a.vec)
    else:
        show(assess(a.query, a.db, a.vec))
