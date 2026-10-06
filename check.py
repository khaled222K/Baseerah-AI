"""Verify a submitted text (ayah, hadith, or circulated wording) against the stored sources.

Only wording is compared: the share of the submitted words that appear, in order, in a stored hadith matn
or ayah (SequenceMatcher over normalized words). No model decides the verdict, and the returned texts
come verbatim from the database."""
import argparse, json
from difflib import SequenceMatcher
from evidence import hadith_evidence, open_db
from identify import words
from retrieve import get_retriever
from semantic import QURAN_WORDS

T_MATCH = 0.9     # >= this share of the submitted words found in order -> matched
T_PARTIAL = 0.7   # >= this, with MIN_PARTIAL_WORDS matched and a MIN_RUN-word contiguous run -> partial_match
MIN_PARTIAL_WORDS = 4
MIN_RUN = 3
T_RELATED = 0.3   # >= this -> not_matched (shares wording with a stored text but does not match it)
MIN_WORDS = 3
QURAN = "القرآن الكريم (مجمع الملك فهد)"


def score(q, m):
    """(share of q's words found in order in m, longest contiguous run of matched words)."""
    blocks = SequenceMatcher(None, q, m, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(q), max((b.size for b in blocks), default=0)


def join_ya(ws):
    """Stored imlaei text writes the vocative joined ("ياايها"); users often type it apart ("يا ايها")."""
    out = []
    for w in ws:
        if out and out[-1] == "يا":
            out[-1] = "يا" + w
        else:
            out.append(w)
    return out


def unaltered(q, t):
    """True when q's words that match t form one contiguous run with nothing changed, added or dropped inside it.
    Extra words before or after (e.g. "قال تعالى") are allowed; a substituted word inside the quote is not."""
    blocks = [b for b in SequenceMatcher(None, q, t, autojunk=False).get_matching_blocks() if b.size]
    return len(blocks) == 1 and blocks[0].size >= MIN_RUN


def ayah_candidates(r, text, n=100):
    keys = [k for k in r.lexical_records(text, n) if r.rec[k[1]][0] == "ayah"]
    ranked, _ = r.dense(text, 60)
    keys += [k for k in ranked if k[0] == "records" and r.rec[k[1]][0] == "ayah"]
    return list(dict.fromkeys(keys))


def check(text, db_path="baseerah.db", vec_path="embeddings.db"):
    qw = [w for w in words(text) if w not in QURAN_WORDS]
    if len(qw) < MIN_WORDS:
        return {"status": "insufficient_evidence", "reason": "too_short", "coverage": 0.0, "match": None}
    r = get_retriever(db_path, vec_path)
    best = (0.0, 0, 0, None)  # coverage, run, ayah-preferred tie-break, key
    for key in r.lexical_hadith(text, 200) + [k for k in r.dense(text, 60)[0] if k[0] == "hadith"]:
        matn = r.db.execute("SELECT matn FROM hadith WHERE id=?", (key[1],)).fetchone()[0]
        best = max(best, (*score(qw, words(matn)), 0, key), key=lambda x: x[:3])
    for key in ayah_candidates(r, text):
        ts = words(r.db.execute("SELECT text_search FROM records WHERE id=?", (key[1],)).fetchone()[0])
        cov, run = max(score(qw, ts), score(join_ya(qw), ts))
        best = max(best, (cov, run, 1, key), key=lambda x: x[:3])
    cov, run, key = round(best[0], 3), best[1], best[3]
    exact = False
    if key and key[0] == "records":
        # Quran wording must be exact: one changed word (e.g. الصلاة for الصيام) is not a match.
        ts = words(r.db.execute("SELECT text_search FROM records WHERE id=?", (key[1],)).fetchone()[0])
        exact = any(unaltered(v, ts) for v in (words(text), join_ya(words(text))))
    if cov >= T_MATCH and (exact or key[0] == "hadith"):
        status = "matched"
    elif cov >= T_PARTIAL and round(cov * len(qw)) >= MIN_PARTIAL_WORDS and run >= MIN_RUN:
        status = "partial_match"
    elif cov >= T_RELATED:
        status = "not_matched"
    else:
        return {"status": "insufficient_evidence", "reason": "no_source", "coverage": cov, "match": None}
    if status == "not_matched":
        return {"status": status, "coverage": cov, "match": None}
    db = open_db(db_path)
    if key[0] == "hadith":
        match = hadith_evidence(db, key[1], text, None, True)
    else:
        row = db.execute("SELECT reference, text_original, url, surah_no, ayah_no FROM records WHERE id=?",
                         (key[1],)).fetchone()
        match = {"kind": "ayah", "id": key[1], "unit": f"ayah:{int(row[3])}:{int(row[4])}", "ref": row[0],
                 "text": row[1], "url": row[2], "source": QURAN}
    return {"status": status, "coverage": cov, "matched_words": round(cov * len(qw)), "total_words": len(qw),
            "exact": exact, "match": match}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    a = ap.parse_args()
    print(json.dumps(check(a.text), ensure_ascii=False, indent=1, default=str))
