"""Explain one hadith with the LLM, grounded only in that hadith's stored text (and its stored note, if any).

The hadith is read from the database by ID; the client never supplies the text. The generated explanation
is shown only if it passes checks against the source: every quotation must be in the text, no numbers or
hadith collections that the text does not contain, and word glosses only for words that occur in it."""
import argparse, json, re
import os
from answer import llm_call, flat, quotes_ok, script_ok, DISCLOSURE, GENERATED_LABEL
from build_hadith_db import strip_al
from evidence import hadith_evidence, open_db

SYSTEM = """أنت مساعد يشرح معنى حديث نبوي واحد لقارئ عادي، ولست مفتياً.
تُعطى نص الحديث كما هو في قاعدة البيانات، وقد يُرفق معه توضيح مخزن من مصدر معتمد.
القواعد:
1. اشرح ما يدل عليه لفظ الحديث المرفق فقط، بعربية فصيحة مبسطة، في ثلاث إلى ست جمل.
2. إن رُفق توضيح فاستند إليه في بيان المعنى ولا تخالفه.
3. لا تستنبط أحكاماً فقهية جديدة، ولا تفتِ في حالات شخصية. إن كانت في المعنى مسألة خلافية فقل إنها تحتاج الرجوع إلى أهل العلم دون أن تقطع بقول.
4. لا تذكر أحاديث أو آيات أخرى، ولا أسماء رواة أو كتب أو أرقاماً غير موجودة في النص المرفق.
5. إن اقتبست من الحديث فانقل الكلمات حرفياً من النص المرفق بين «».
6. في words اذكر من كلمة إلى خمس كلمات غريبة وردت في نص الحديث نفسه مع معناها المختصر.
7. إن كان النص المرفق ناقصاً أو مجرد إسناد أو إحالة إلى حديث آخر ولا يحمل معنى يُشرح، فاجعل ok=false.
أخرج JSON فقط بهذا الشكل دون أي نص خارجه:
{"ok": true, "explanation": "...", "words": [{"word": "...", "meaning": "..."}]}"""

UNAVAILABLE = "شرح الحديث بالذكاء الاصطناعي غير مفعّل على الخادم حالياً."
REJECTED = "لم يُعرض الشرح المولَّد لأنه لم يجتز فحص الاستناد إلى نص الحديث، ويُعرض الحديث كما هو."
NOT_EXPLAINABLE = "النص المخزن لهذا الحديث لا يكفي لشرحه (قد يكون إسناداً أو إحالة إلى رواية أخرى)."
FAILED = "تعذّر الاتصال بالنموذج حالياً، فلم يُعدّ الشرح."
GROUNDED_ON = "نص الحديث المعروض"
# Other collections the model must not cite unless the stored text itself names them (normalized forms).
# Ordinary words such as "مسلم" (a Muslim) or "الحاكم" (the ruler) are deliberately not listed.
COLLECTIONS = ["الترمذي", "ابو داود", "ابي داود", "النسائي", "ابن ماجه", "مسند احمد", "رواه احمد", "الموطا",
               "الدارمي", "البيهقي", "الطبراني", "المستدرك", "ابن حبان", "ابن خزيمه", "الدارقطني"]
DIGITS = re.compile(r"[0-9٠-٩۰-۹]+")


def _digits(t):
    return {d.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")) for d in DIGITS.findall(t or "")}


def norm_words(t):
    """Normalized words without attached ال/بال/وال/لل prefixes, so "الصرعة" matches "بالصرعة"."""
    return [strip_al(w) for w in flat(t).split()]


def grounded(text, source_text):
    """Reasons the generated text is not grounded in source_text (empty list = ok)."""
    problems = []
    if not quotes_ok(text, [{"text": source_text}]):
        problems.append("quote")
    if _digits(text) - _digits(source_text):
        problems.append("number")
    src = flat(source_text)
    if any(c in flat(text) and c not in src for c in COLLECTIONS):
        problems.append("collection")
    if not script_ok(text):
        problems.append("script")
    return problems


def parse(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    words = [w for w in d.get("words", []) if isinstance(w, dict) and isinstance(w.get("word"), str)
             and isinstance(w.get("meaning"), str) and w["word"].strip() and w["meaning"].strip()]
    return {"ok": d.get("ok") is True, "explanation": str(d.get("explanation", "")).strip(), "words": words[:5]}


_CACHE = {}
CACHE_MAX = 512
FINAL = {"explained", "rejected", "not_explainable", "not_found"}  # transient failures are not cached


def _explain(hadith_id, backend, db_path):
    db = open_db(db_path)
    if not db.execute("SELECT 1 FROM hadith WHERE id=?", (hadith_id,)).fetchone():
        return {"status": "not_found"}
    e = hadith_evidence(db, hadith_id, "", None, False)
    note = e["note"] if e.get("note") and e["note"]["text"] else None
    base = {"hadith_id": hadith_id, "reference": f"{e['ref']}، رقم {e['number']}", "text": e["text"],
            "stored_note": note, "label": GENERATED_LABEL, "disclosure": DISCLOSURE,
            "grounded_on": [GROUNDED_ON] + ([f"توضيح ({note['source']})"] if note else [])}
    if backend == "retrieval":
        return {**base, "status": "unavailable", "message": UNAVAILABLE, "explanation": None, "words": []}
    source = e["text"] + ("\n" + note["text"] if note else "")
    user = f"<hadith>\n{e['text']}\n</hadith>" + (f"\n\n<note source=\"{note['source']}\">\n{note['text']}\n</note>" if note else "")
    try:
        d = parse(llm_call(SYSTEM, user, backend=backend))
    except Exception as ex:  # network, auth, refusal, truncation
        return {**base, "status": "error", "message": FAILED, "explanation": None, "words": [], "error": str(ex)}
    if d is None:
        return {**base, "status": "error", "message": FAILED, "explanation": None, "words": [], "error": "unparseable reply"}
    if not d["ok"] or not d["explanation"]:
        return {**base, "status": "not_explainable", "message": NOT_EXPLAINABLE, "explanation": None, "words": []}
    problems = grounded(d["explanation"], source)
    text_words = set(norm_words(e["text"]))
    # Word glosses were the least reliable part with small local models, so they are off by default in openai mode.
    glosses = os.environ.get("BASEERAH_EXPLAIN_WORDS", "0" if backend == "openai" else "1") == "1"
    words = [w for w in d["words"] if glosses
             and all(t in text_words for t in norm_words(w["word"])) and not grounded(w["meaning"], source)]
    if problems:
        return {**base, "status": "rejected", "message": REJECTED, "explanation": None, "words": [], "problems": problems}
    return {**base, "status": "explained", "message": None, "explanation": d["explanation"], "words": words}


def explain(hadith_id, backend, db_path="baseerah.db"):
    from answer import MODEL
    key = (int(hadith_id), backend, MODEL, db_path)
    if key not in _CACHE:
        r = _explain(int(hadith_id), backend, db_path)
        if r["status"] not in FINAL:
            return r
        if len(_CACHE) >= CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = r
    return _CACHE[key]


if __name__ == "__main__":
    from ask import default_mode
    ap = argparse.ArgumentParser()
    ap.add_argument("hadith_id", type=int)
    ap.add_argument("--mode", default=None)
    a = ap.parse_args()
    print(json.dumps(explain(a.hadith_id, a.mode or default_mode()), ensure_ascii=False, indent=1))
