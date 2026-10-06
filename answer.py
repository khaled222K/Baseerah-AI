import argparse, json, os, re
import envfile  # noqa: F401  (loads .env before settings are read)
from build_hadith_db import norm
from evidence import assess, MESSAGES, T_LEX, hadith_evidence, open_db
from understand import non_arabic
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
AYAH_EXACT = "النص المكتوب جزء من آية قرآنية، وهذه الآية كما في المصحف مع موضعها."
AYAH_ALTERED = ("تنبيه: الصيغة المكتوبة لا تطابق نص الآية حرفياً؛ فيها كلمة أو أكثر مختلفة عن المصحف. "
                "هذا نص الآية الصحيح كما في المصحف مع موضعها (السورة: الآية)، ولا يُعتمد على الصيغة المكتوبة.")
NON_ARABIC = ("Baseerah searches Arabic sources and answers in Arabic; the texts below are shown in Arabic exactly as stored. "
              "تبحث بصيرة في مصادر عربية وتجيب بالعربية، وتُعرض النصوص كما هي.")
NO_TRANSLATION = ("لا تترجم بصيرة النصوص أو المصطلحات؛ تُعرض النصوص العربية المرتبطة بالمصطلح من مصادرها كما هي. "
                  "Baseerah does not translate; it shows the Arabic source texts related to the term.")
TRANSLATE = re.compile(r"translat|ترجم", re.I)
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
7. إن بُني السؤال على فهم خاطئ (مثل أن المسلمين يعبدون مكاناً أو شخصاً) فصحّحه بلطف وهدوء من النصوص المرفقة فقط، دون اتهام السائل.
8. إن كان في السؤال سخرية أو حدة فلا تجارِها ولا تعلّق عليها، وأجب عن أصل السؤال بهدوء وأدب.
9. لا تقل "أجمع العلماء" أو "اتفق المسلمون" إلا إن نصّ على ذلك نصٌّ مرفق. فرّق بين ما يدل عليه النص صراحة وما هو اجتهاد يختلف فيه العلماء.
10. إن كان في السؤال مصطلح شرعي فاشرح معناه بكلمات يومية بسيطة أولاً ثم اذكر المصطلح، واكتب الشرح بالعربية دائماً ولو كان السؤال بلغة أخرى.
11. إن طلب المستخدم حديثاً بلفظ معيّن ولم يرد هذا اللفظ في النصوص المرفقة فقل إنه لم يُوجد بهذا اللفظ في المصادر المتاحة، ولا تنسبه إلى النبي ﷺ، ثم بيّن ما تدل عليه النصوص المرفقة.
أخرج JSON فقط بهذا الشكل دون أي نص خارجه:
{"relevant": true, "used": ["H1", "T1"], "explanation": "..."}"""


# Models that accept server-side refusal fallback (fallbacks: "default", Claude API only). Set BASEERAH_FALLBACKS=0 to disable.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
LLM_MAX_TOKENS = 16000  # current Claude models think before answering, and thinking counts toward max_tokens


def llm_timeout(backend):
    """Seconds per LLM request. Below the site's request timeout (90 s / 300 s), so a stuck model ends in the
    texts-only fallback instead of the SDK default (600 s with 2 retries)."""
    return float(os.environ.get("BASEERAH_LLM_TIMEOUT", "240" if backend == "openai" else "75"))


def anthropic_call(system, user, max_tokens=LLM_MAX_TOKENS):
    import anthropic
    client = anthropic.Anthropic(timeout=llm_timeout("anthropic"), max_retries=1)  # ANTHROPIC_API_KEY from the environment / .env
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
        client = OpenAI(base_url=os.environ.get("BASEERAH_BASE_URL") or None, api_key=os.environ.get("OPENAI_API_KEY", "local"),
                        timeout=llm_timeout("openai"), max_retries=0)  # a retry would not help a busy local CPU
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:  # every Baseerah prompt asks for JSON; JSON mode makes small local models comply
            r = client.chat.completions.create(model=MODEL, messages=msgs, response_format={"type": "json_object"})
        except Exception:
            r = client.chat.completions.create(model=MODEL, messages=msgs)
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


# Letters from other scripts (Latin, Cyrillic, CJK, Hangul) in an Arabic explanation mean garbled model output.
FOREIGN = re.compile(r"[A-Za-z\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")


def script_ok(text):
    return not FOREIGN.search(text or "")


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
    out["notice"] = " ".join(filter(None, [out["notice"], NO_MODEL]))
    out["error"] = reason
    return out


def quoted_ayah(query, db_path, vec_path):
    """(ayah evidence, exact?) when the user typed (part of) an ayah, possibly with altered words; else (None, None).
    The ayah text comes from the database; the user's wording is never echoed back."""
    from check import check
    r = check(query, db_path, vec_path)
    m = r.get("match")
    if not m or m["kind"] != "ayah" or r["status"] not in ("matched", "partial_match"):
        return None, None
    return m, r.get("exact", False)


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
    # Local models (openai mode) are slow on CPU, so the question rewrite uses the rules unless BASEERAH_UNDERSTAND says otherwise.
    u = understand(query, backend=os.environ.get("BASEERAH_UNDERSTAND") or ("rules" if mode in ("retrieval", "openai") else mode))
    out = {"status": None, "message": None, "texts": [], "explanation": None, "mode": mode,
           "disclosure": DISCLOSURE, "generated_label": GENERATED_LABEL, "notice": None, "error": None,
           "understanding": u}
    notes = [NO_TRANSLATION] if TRANSLATE.search(query) else [NON_ARABIC] if non_arabic(query) else []
    if len(norm(query).split()) >= 3 and not re.search(r"[؟?]", query):
        ayah, exact = quoted_ayah(query, db_path, vec_path)
        if ayah:
            out.update(status="identified", message=AYAH_EXACT if exact else AYAH_ALTERED, texts=[ayah])
            return out
    ident = identified(query, u, db_path, vec_path) if len(norm(query).split()) >= 2 else []
    if ident:
        out.update(status="identified", message=IDENTIFIED, texts=ident)
        return out
    a = assess(query, db_path, vec_path, rewrites=tuple(u["rewrites"]))
    out.update(status=a["status"], message=a["message"], notice=" ".join(notes) or None)
    if a["status"] in ("insufficient", "clarify") or not a["evidence"]:
        return out
    units = pick(a["evidence"])
    if mode == "retrieval":
        out["texts"] = [e for _, e in units]
        out["notice"] = " ".join([*notes, RETRIEVAL_ONLY])
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
    if quotes_ok(verdict["explanation"], out["texts"]) and script_ok(verdict["explanation"]):
        out["explanation"] = verdict["explanation"]
    else:
        out["notice"] = " ".join(filter(None, [out["notice"], BAD_QUOTE]))
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
