import argparse, json, os, re
import envfile  # noqa: F401  (loads .env before settings are read)
from build_hadith_db import norm
from evidence import assess, MESSAGES, T_LEX, hadith_evidence, open_db
from verify import MARKS

MAX_HADITH, MAX_TAFSIR, MAX_AYAH = 3, 2, 2
BACKEND = os.environ.get("BASEERAH_LLM", "anthropic")
MODEL = os.environ.get("BASEERAH_MODEL", "claude-sonnet-5-5")
QUOTE_MIN_WORDS = 1
QUOTES = re.compile(r"«([^»]+)»|\"([^\"]+)\"|“([^”]+)”|﴿([^﴾]+)﴾")
NO_MODEL = "تعذّر الاتصال بالنموذج، فتُعرض النصوص المرتبطة بالسؤال بمراجعها دون شرح مولَّد."
BAD_QUOTE = "حُذف الشرح المولَّد لأنه تضمّن اقتباساً غير موجود في النصوص المعروضة، وتُعرض النصوص كما هي."
DISCLOSURE = "هذه الإجابة من أداة مدعومة بالذكاء الاصطناعي وليست من مختص شرعي."
GENERATED_LABEL = "شرح مولَّد بالذكاء الاصطناعي (ليس نصاً شرعياً)"
RETRIEVAL_ONLY = "وضع الاسترجاع فقط: تُعرض النصوص المرتبطة بالسؤال بمراجعها كما هي دون شرح مولَّد."
IDENTIFIED = "يبدو أن المكتوب جزء من حديث أو وصفٌ له، وهذه أقرب المطابقات من القاعدة كما هي."
MODES = ("retrieval", "anthropic", "openai")

SYSTEM = """أنت مساعد بحثي يعرض النصوص الشرعية المتاحة له فقط، ولست مفتياً.
تُعطى سؤالاً ونصوصاً مرقّمة من قاعدة بيانات موثوقة (أحاديث من الصحيحين، وآيات، وتفسير). النصوص ستُعرض للمستخدم كما هي من القاعدة، فلا تنقلها ولا تعيد كتابتها.
مهمتك:
1. قرر هل النصوص المرفقة تجيب عن السؤال مباشرة. إن لم تجب أو كان الارتباط بعيداً أو بمجرد تشابه كلمة، اجعل relevant=false.
2. اختر معرّفات النصوص التي تدعم الجواب فقط في used، ولا تخترع معرّفات.
3. اكتب في explanation شرحاً موجزاً (من جملتين إلى أربع) بعربية فصيحة مبسطة يربط النصوص المختارة بالسؤال، دون أن تضيف حكماً أو معلومة غير موجودة فيها. إن كانت المسألة خلافية فأشر إلى ذلك بإيجاز دون أن تقطع بقول.
4. إن كان السؤال عن حالة شخصية فلا تحكم على الحالة، واذكر أنها تحتاج الرجوع إلى أهل العلم.
5. لا تذكر اسم راوٍ أو كتاباً أو رقماً غير موجود في النصوص المرفقة.
6. اشرح ما يدل عليه لفظ النص المرفق فيما يخص السؤال فقط، دون استنتاج أحكام جديدة. إن رُفق توضيح مع حديث فهو المرجع في بيان معناه فانقله بإيجاز.
أخرج JSON فقط بهذا الشكل دون أي نص خارجه:
{"relevant": true, "used": ["H1", "T1"], "explanation": "..."}"""


# Models that accept server-side refusal fallback (fallbacks: "default", Claude API only). Set BASEERAH_FALLBACKS=0 to disable.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
LLM_MAX_TOKENS = 16000  # current Claude models think before answering, and thinking counts toward max_tokens


def anthropic_call(system, user, max_tokens=LLM_MAX_TOKENS):
    import anthropic
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from the environment / .env
    kw = dict(model=MODEL, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    if MODEL in FALLBACK_MODELS and os.environ.get("BASEERAH_FALLBACKS", "1") != "0":
        try:
            r = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        except TypeError:  # older SDK without a typed `fallbacks` argument: send the same field in the body
            r = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"}, **kw)
    else:
        r = client.messages.create(**kw)
    if r.stop_reason == "refusal":
        raise RuntimeError(f"model declined ({getattr(r.stop_details, 'category', None)})")
    if r.stop_reason == "max_tokens":
        raise RuntimeError("model output was cut off at max_tokens")
    return "".join(b.text for b in r.content if b.type == "text")


def llm_call(system, user, backend=None):
    if (backend or BACKEND) == "openai":
        from openai import OpenAI
        client = OpenAI(base_url=os.environ.get("BASEERAH_BASE_URL") or None, api_key=os.environ.get("OPENAI_API_KEY", "local"))
        r = client.chat.completions.create(model=MODEL, messages=[
            {"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content
    return anthropic_call(system, user)


def pick(evidence):
    units, counts = [], {"hadith": 0, "tafsir": 0, "ayah": 0}
    limit = {"hadith": MAX_HADITH, "tafsir": MAX_TAFSIR, "ayah": MAX_AYAH}
    prefix = {"hadith": "H", "tafsir": "T", "ayah": "A"}
    for e in evidence:
        k = e["kind"]
        if counts[k] >= limit[k]:
            continue
        counts[k] += 1
        units.append((f"{prefix[k]}{counts[k]}", e))
    return units


def build_context(units):
    parts = []
    for uid, e in units:
        if e["kind"] == "hadith":
            n = e.get("note")
            if n and n["text"]:
                note = f"\nتوضيح ({n['source']}): {n['text']}"
            else:
                note = ""
            parts.append(f"[{uid}] حديث | {e['ref']} | الحكم: {e['grade']}\n{e['text']}{note}")
        elif e["kind"] == "tafsir":
            ay = f"\nالآية ({e['ayah']['ref']}): {e['ayah']['text']}" if e.get("ayah") else ""
            parts.append(f"[{uid}] تفسير ({e['source']}) | {e['ref']}{ay}\n{e['text'][:900]}")
        else:
            parts.append(f"[{uid}] آية | {e['ref']}\n{e['text']}")
    return "\n\n".join(parts)


def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    return {"relevant": d.get("relevant") is True, "used": [u for u in d.get("used", []) if isinstance(u, str)],
            "explanation": str(d.get("explanation", "")).strip()}


def flat(t):
    return norm(MARKS.sub("", t or ""))


def corpus(texts):
    parts = []
    for e in texts:
        parts.append(flat(e["text"]))
        if e.get("ayah"):
            parts.append(flat(e["ayah"]["text"]))
        if e.get("note") and e["note"]["text"]:
            parts.append(flat(e["note"]["text"]))
    return " | ".join(parts)


def quotes_ok(explanation, texts):
    source = corpus(texts)
    for m in QUOTES.finditer(explanation or ""):
        q = flat(next(g for g in m.groups() if g))
        if len(q.split()) >= QUOTE_MIN_WORDS and q not in source:
            return False
    return True


def records_only(out, units, reason):
    out["texts"] = [e for _, e in units]
    out["explanation"] = None
    out["notice"] = NO_MODEL
    out["error"] = reason
    return out


def identified(query, u, db_path, vec_path):
    """Hadith the user quotes or paraphrases, as evidence entries straight from the database, or []."""
    if u["intent"] != "hadith_lookup" and re.search(r"[؟?]", query):
        return []
    from identify import identify
    found = identify(query, db_path, vec_path)
    quote = [m for m in found["matches"] if m["match"] == "quote"]
    if not quote and u["intent"] != "hadith_lookup":
        return []
    chosen = quote or [m for m in found["matches"][:1] if m["similarity"] >= T_LEX]
    db = open_db(db_path)
    return [dict(hadith_evidence(db, m["id"], query, m["similarity"], m["match"] == "quote"),
                 match=m["match"], numbering_note=found["numbering_note"]) for m in chosen]


def answer(query, db_path="baseerah.db", vec_path="embeddings.db", mode=None):
    """mode: retrieval (no LLM) | anthropic | openai. Defaults to BASEERAH_LLM."""
    mode = mode or BACKEND
    from understand import understand
    u = understand(query, backend="rules" if mode == "retrieval" else mode)
    out = {"status": None, "message": None, "texts": [], "explanation": None, "mode": mode,
           "disclosure": DISCLOSURE, "generated_label": GENERATED_LABEL, "notice": None, "error": None,
           "understanding": u}
    ident = identified(query, u, db_path, vec_path) if len(norm(query).split()) >= 2 else []
    if ident:
        out.update(status="identified", message=IDENTIFIED, texts=ident)
        return out
    a = assess(query, db_path, vec_path, rewrites=tuple(u["rewrites"]))
    out.update(status=a["status"], message=a["message"])
    if a["status"] in ("insufficient", "clarify"):
        return out
    units = pick(a["evidence"])
    if mode == "retrieval":
        out["texts"] = [e for _, e in units]
        out["notice"] = RETRIEVAL_ONLY
        return out
    try:
        verdict = parse(llm_call(SYSTEM, f"<question>\n{query}\n</question>\n\n<texts>\n{build_context(units)}\n</texts>",
                                 backend=mode))
    except Exception as ex:
        return records_only(out, units, str(ex))
    if not verdict:
        return records_only(out, units, "رد غير مقروء")
    valid = {uid for uid, _ in units}
    used = [u for u in verdict["used"] if u in valid]
    if not verdict["relevant"] or not used:
        out.update(status="insufficient", message=MESSAGES["insufficient"])
        return out
    out["texts"] = [e for uid, e in units if uid in used]
    if quotes_ok(verdict["explanation"], out["texts"]):
        out["explanation"] = verdict["explanation"]
    else:
        out["notice"] = BAD_QUOTE
    return out


def render(o):
    print(f"\nالحالة: {o['status']}\n{o['message']}")
    if o["texts"]:
        print("\n=== النصوص الشرعية (من القاعدة كما هي) ===")
        for e in o["texts"]:
            if e["kind"] == "hadith":
                d = f" | الدرر: {e['dorar']['grade']} ({e['dorar']['muhaddith']})" if e["dorar"] else ""
                num = f"، رقم {e['number']}" if e.get("number") else ""
                print(f"\n[حديث] {e['ref']}{num}\n  {e['text']}\n  الحكم: {e['grade']}{d}\n  الرابط: {e['link']['url']}")
                if e.get("numbering_note"):
                    print(f"  ({e['numbering_note']})")
                if e.get("note") and e["note"]["text"]:
                    print(f"  التوضيح ({e['note']['source']}): {e['note']['text']}")
            else:
                ay = e.get("ayah") or (e if e["kind"] == "ayah" else None)
                if ay:
                    print(f"\n[آية] {ay['ref']}\n  {ay['text']}\n  الرابط: {ay['url']}")
                if e["kind"] == "tafsir":
                    print(f"\n[تفسير] {e['source']} | {e['ref']}\n  {e['text'][:600]}\n  الرابط: {e['url']}")
        if o["explanation"]:
            print(f"\n=== {o['generated_label']} ===\n{o['explanation']}")
    if o.get("notice"):
        print(f"\n{o['notice']}")
    print(f"\n{o['disclosure']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--vec", default="embeddings.db")
    ap.add_argument("--mode", choices=MODES, default=None)
    a = ap.parse_args()
    render(answer(a.query, a.db, a.vec, a.mode))
