"""Query understanding: turn a question (Gulf dialect or MSA) into formal-Arabic search rewrites and keywords.

The LLM backends only rewrite the question: no search tool, and their output is used for retrieval only,
never displayed. The "rules" backend needs no model or key and is the fallback for any LLM failure."""
import argparse, json, os, re
from build_hadith_db import norm, strip_al, fts_query
from semantic import GENERIC

MAX_REWRITES = 3
MAX_REWRITE_WORDS = 25

# Gulf dialect -> MSA, keys in norm() form. Values are search words, not displayed text.
GULF = {
    "وش": "ما", "ايش": "ما", "شنو": "ما", "شو": "ما", "وشو": "ما", "ليش": "لماذا", "شلون": "كيف", "كيفه": "كيف",
    "وين": "اين", "منو": "من", "مين": "من", "ابي": "اريد", "ابغي": "اريد", "ابغا": "اريد", "ودي": "اريد",
    "يبي": "يريد", "يبغي": "يريد", "حرمه": "امراه", "الحرمه": "المراه", "حريم": "نساء", "الحريم": "النساء",
    "عيال": "اولاد", "العيال": "الاولاد", "عيالي": "اولادي", "فلوس": "مال", "الفلوس": "المال", "زين": "حسن",
    "مو": "ليس", "مب": "ليس", "يعصب": "يغضب", "عصبي": "غضوب", "العصبيه": "الغضب", "زعل": "غضب", "الزعل": "الغضب",
    "صايم": "صائم", "صايمه": "صائمه", "ورث": "ميراث", "الورث": "الميراث", "بروحه": "وحده", "بروحي": "وحدي",
    "لين": "حتي", "اللي": "الذي", "للي": "للذي", "هذي": "هذه", "يسوي": "يفعل", "اسوي": "افعل", "سويت": "فعلت", "يقدر": "يستطيع",
    "وايد": "كثير", "يتقسم": "يقسم", "عطست": "عطس", "الدوره": "الحيض", "البريود": "الحيض", "طق": "ضرب",
    "يطق": "يضرب", "عشان": "لان", "علشان": "لان",
    "زوجتي": "زوجه", "رجلي": "زوج", "ريلي": "زوج", "ريال": "رجل", "الريال": "الرجل",
    "اتسحر": "سحور", "نتسحر": "سحور", "يتسحر": "سحور", "فطور": "فطر", "الفطور": "الفطر",
}
FILLER = {"بس", "يعني", "طيب", "سمحت", "يعافيك", "قاعد", "كذا", "ترا",
          # request framing ("أعطني حديثاً يثبت أن ...") that pulls search toward unrelated texts
          "اعطني", "اعطيني", "هات", "اذكر", "اذكري", "حديثا", "احاديث", "يثبت", "تثبت", "ان"}
# Religious terms in English or transliteration -> the Arabic search word, so a non-Arabic question still reaches
# the Arabic texts (the dense model is multilingual, but FTS and the reranker work best on Arabic).
TERMS = {
    "jihad": "الجهاد", "tawhid": "التوحيد", "tawheed": "التوحيد", "monotheism": "التوحيد", "oneness": "التوحيد",
    "prayer": "الصلاه", "prayers": "الصلاه", "salah": "الصلاه", "salat": "الصلاه", "zakat": "الزكاه", "zakah": "الزكاه",
    "charity": "الصدقه", "sadaqah": "الصدقه", "fasting": "الصيام", "fast": "الصيام", "ramadan": "رمضان", "hajj": "الحج",
    "pilgrimage": "الحج", "umrah": "العمره", "hijab": "الحجاب", "veil": "الحجاب", "niqab": "النقاب",
    "riba": "الربا", "usury": "الربا", "interest": "الربا", "alcohol": "الخمر", "wine": "الخمر",
    "marriage": "النكاح", "divorce": "الطلاق", "wife": "الزوجه", "husband": "الزوج", "women": "النساء", "woman": "المراه",
    "neighbor": "الجار", "neighbour": "الجار", "parents": "الوالدين", "mother": "الام", "orphan": "اليتيم",
    "orphans": "اليتامي", "mecca": "مكه", "makkah": "مكه", "kaaba": "الكعبه", "qibla": "القبله",
    "paradise": "الجنه", "jannah": "الجنه", "hell": "النار", "repentance": "التوبه", "tawbah": "التوبه",
    "patience": "الصبر", "honesty": "الصدق", "lying": "الكذب", "backbiting": "الغيبه", "sin": "الذنب",
    "sins": "الذنوب", "shirk": "الشرك", "sharia": "الشريعه", "fatwa": "الفتوي", "sunnah": "السنه", "quran": "القران",
    "inheritance": "الميراث", "modesty": "الحياء", "mercy": "الرحمه", "knowledge": "العلم",
}
# Modern words -> the classical term the sources use (e.g. the hadith say الطهور, not النظافة).
CLASSICAL = {"النظافه": "الطهور", "نظافه": "طهور", "النظيف": "الطاهر", "نظيف": "طاهر",
             "قوامه": "قوامون", "القوامه": "قوامون"}
LATIN = re.compile(r"[A-Za-z]+")

SYSTEM = """أنت تعيد صياغة أسئلة المستخدمين لأغراض البحث في قاعدة نصوص شرعية فقط، ولست مفتياً ولا تملك أداة بحث.
السؤال قد يكون بلهجة خليجية أو بالفصحى.
أخرج JSON فقط بهذا الشكل دون أي نص خارجه:
{"intent": "question", "rewrites": ["..."], "keywords": ["..."]}
- rewrites: من صياغة إلى ثلاث صياغات قصيرة بالعربية الفصحى لنفس السؤال، دون إضافة حكم أو جواب.
- keywords: من كلمتين إلى ست كلمات مفتاحية فصيحة (المصطلحات الشرعية للموضوع).
- intent = "hadith_lookup" إذا كان المستخدم يكتب جزءاً من حديث أو يصف حديثاً بمعناه ليعرف مصدره، وإلا "question".
- لا تكتب نص أي حديث أو آية، ولا تذكر مصادر أو أرقاماً أو أسماء رواة."""

LOOKUP = re.compile(r"(^| )(حديث|الحديث)( |$)")


def non_arabic(query):
    """True when the question is written mostly in Latin letters (English or transliteration)."""
    latin = LATIN.findall(query)
    return len(latin) >= 2 and len(latin) > len(norm(query).split())


def rules(query):
    words = [CLASSICAL.get(w, GULF.get(w, w)) for w in norm(query).split() if w not in FILLER]
    words += list(dict.fromkeys(TERMS[w.lower()] for w in LATIN.findall(query) if w.lower() in TERMS))
    rewrite = " ".join(words)
    keywords = [t for t in re.findall(r'"([^"]+)"', fts_query(rewrite)) if t not in GENERIC]
    intent = "hadith_lookup" if LOOKUP.search(norm(query)) else "question"
    return {"intent": intent, "rewrites": [rewrite] if rewrite and (rewrite != norm(query) or LATIN.search(query)) else [], "keywords": keywords,
            "backend": "rules"}


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
    clip = lambda xs: [str(x).strip() for x in xs if isinstance(x, str) and str(x).strip()]
    rewrites = [r for r in clip(d.get("rewrites", [])) if len(r.split()) <= MAX_REWRITE_WORDS][:MAX_REWRITES]
    keywords = [k for k in clip(d.get("keywords", [])) if len(k.split()) <= 3][:6]
    intent = d.get("intent") if d.get("intent") in ("question", "hadith_lookup") else "question"
    return {"intent": intent, "rewrites": rewrites, "keywords": keywords}


def understand(query, backend=None):
    """{"intent", "rewrites", "keywords", "backend"}; backend: rules | anthropic | openai (default BASEERAH_LLM or rules)."""
    backend = backend or os.environ.get("BASEERAH_UNDERSTAND", os.environ.get("BASEERAH_LLM", "rules"))
    if backend == "rules":
        return rules(query)
    from answer import llm_call
    try:
        d = parse(llm_call(SYSTEM, f"<question>\n{query}\n</question>", backend=backend))
    except Exception as ex:
        d = None
        err = str(ex)
    else:
        err = "رد غير مقروء" if d is None else None
    if d is None:
        out = rules(query)
        out["error"] = err
        return out
    if d["keywords"]:
        d["rewrites"] = d["rewrites"] + [" ".join(d["keywords"])]
    d["backend"] = backend
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--backend", choices=["rules", "anthropic", "openai"], default=None)
    a = ap.parse_args()
    print(json.dumps(understand(a.query, a.backend), ensure_ascii=False, indent=1))
