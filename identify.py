"""Identify the hadith a user quotes or paraphrases. Candidates come from FTS (BM25) and dense search;
quotes are scored with SequenceMatcher over normalized words of the matn. The displayed text is
matn_display from the database, never model output."""
import argparse, json
from difflib import SequenceMatcher
from build_hadith_db import norm, strip_al, BOOK_AR
from retrieve import get_retriever
from understand import rules

# Framing words users put around a quote ("حديث معناه ..."); dropped before matching.
FRAME = {"حديث", "الحديث", "معناه", "معني", "اللي", "الذي", "يقول", "فيه", "نصه", "ورد", "هل", "صحيح", "وش", "ما",
         "مصدر", "رقم", "اريد", "ابي", "ابغي", "عن"}
T_QUOTE = 0.8
MIN_QUOTE_WORDS = 3
NUMBERING_NOTE = "الرقم بحسب ترقيم مصدر البيانات (hadith-json) وقد يختلف عن ترقيم الطبعات المشهورة."


def words(text):
    return [strip_al(w) for w in norm(text).split()]


def coverage(q, m):
    if not q:
        return 0.0
    return sum(b.size for b in SequenceMatcher(None, q, m, autojunk=False).get_matching_blocks()) / len(q)


def identify(text, db_path="baseerah.db", vec_path="embeddings.db", n=3, pool=200):
    r = get_retriever(db_path, vec_path)
    qw = [w for w in words(text) if w not in FRAME]
    cands = {key[1] for key in r.lexical_hadith(text, pool)}
    sims = {}
    for q in [text, *rules(text)["rewrites"]]:
        ranked, s = r.dense(q, 60)
        for key in ranked:
            if key[0] == "hadith":
                cands.add(key[1])
                sims[key[1]] = max(sims.get(key[1], -1.0), s[key])
    scored = []
    for hid in cands:
        row = r.db.execute("SELECT matn FROM hadith WHERE id=?", (hid,)).fetchone()
        scored.append((round(coverage(qw, words(row[0])), 3), sims.get(hid, 0.0), hid))
    scored.sort(reverse=True)
    quote = len(qw) >= MIN_QUOTE_WORDS and scored and scored[0][0] >= T_QUOTE
    if not quote:
        scored.sort(key=lambda x: (x[1], x[0]), reverse=True)
    out = []
    for cov, sim, hid in scored[:n]:
        h = r.db.execute("SELECT id, book, number_in_book, source_ref, matn_display, grade FROM hadith WHERE id=?",
                         (hid,)).fetchone()
        out.append({"id": h[0], "book": BOOK_AR.get(h[1], h[1]), "number": h[2], "ref": f"{h[3]}، رقم {h[2]}",
                    "text": h[4], "grade": h[5], "coverage": cov, "similarity": round(sim, 3),
                    "match": "quote" if quote and cov >= T_QUOTE else "paraphrase"})
    return {"matches": out, "numbering_note": NUMBERING_NOTE}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("-n", type=int, default=3)
    a = ap.parse_args()
    print(json.dumps(identify(a.text, n=a.n), ensure_ascii=False, indent=1))
