# https://github.com/AhmedBaset/hadith-json
# https://sunnah.com
# https://dorar.net
import argparse, json, re, sqlite3, sys, time, urllib.parse, urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from db import connect_ro

BOOK_AR = {"bukhari": "صحيح البخاري", "muslim": "صحيح مسلم"}
NO_MATCH = "لم يُطابَق"

_TASHKEEL = re.compile(r"[ؗ-ًؚ-ْٰـ]")


def norm(s: str) -> str:
    s = _TASHKEEL.sub("", s)
    s = re.sub("[إأآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[^ء-ي0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_PRE = r"(?<![ء-ي])(?:[وفبك]?لل|[وفبلك]?(?:ال)?)"
_SUF = r"(?:ها|هما|هن|هم|ه|ي|ك|نا)?(?![ء-ي])"
_cache = {}


def has(text: str, kw: str) -> bool:
    if kw not in _cache:
        _cache[kw] = re.compile(_PRE + re.escape(kw) + _SUF)
    return _cache[kw].search(text) is not None


_MATN_START = re.compile(
    r"(?:قال|قالت|يقول)\s+(?:لي\s+)?(?:رسول الله|النبي)(?:\s+صلي الله عليه وسلم)?"
    r"|(?:رسول الله|النبي)(?:\s+صلي الله عليه وسلم)?\s+(?:يقول|قال|يقولون)"
)


STOPPERS = {"قال", "قالت", "ان", "انه", "انها", "سمعت", "سالت", "رايت", "كنت", "كان", "كانت", "يقول", "قلت"}
SAY = {"قال", "قالت", "يقول"}


def _after(toks: list, j: int) -> int:
    if toks[j] in SAY:
        return j + 1
    for s in range(j + 1, min(j + 8, len(toks))):
        if toks[s] in {"النبي", "رسول"}:
            break
        if toks[s] in SAY:
            return s + 1
    return j


def isnad_end(toks: list) -> int:
    window = toks[:60]
    for i in range(len(window) - 1):
        if window[i] == "عن" and window[i + 1] in {"النبي", "رسول"}:
            k = i + 2
            while k < len(toks) and toks[k] in {"الله", "صلي", "عليه", "وسلم"}:
                k += 1
            return k
    window = toks[:45]
    r = 0
    for i in range(len(window) - 1, -1, -1):
        if window[i] != "عن":
            continue
        for j in range(i + 2, min(i + 12, len(toks))):
            if toks[j] in STOPPERS:
                r = _after(toks, j)
                break
        if r:
            break
    if not r:
        last = max((i for i, t in enumerate(window) if t in CHAIN_START), default=-1)
        if last >= 0:
            for j in range(last + 3, min(last + 12, len(toks))):
                if toks[j] in STOPPERS:
                    r = _after(toks, j)
                    break
    while r and r < len(toks) and toks[r] in CHAIN_START:
        for j in range(r + 2, min(r + 10, len(toks))):
            if toks[j] in STOPPERS:
                r = _after(toks, j)
                break
        else:
            break
    return r


def split_matn(full: str):
    pairs = [(o, norm(o)) for o in full.split()]
    pairs = [(o, n) for o, n in pairs if n]
    starts, pos = [], 0
    for _, n in pairs:
        starts.append(pos)
        pos += len(n) + 1
    joined = " ".join(n for _, n in pairs)
    idx = 0
    m = _MATN_START.search(joined)
    if m:
        idx = next((i for i, s in enumerate(starts) if s >= m.end()), len(pairs))
        if len(pairs) - idx < 5:
            idx = 0
    if idx == 0 and pairs and pairs[0][1] in CHAIN_START:
        k = isnad_end([n for _, n in pairs])
        if k and len(pairs) - k >= 5:
            idx = k
    shown =re.sub(r"[‎‏\"“”«»]", "", " ".join(o for o, _ in pairs[idx:]))
    return " ".join(n for _, n in pairs[idx:]), re.sub(r"\s+", " ", shown).strip()


STRONG = ["امراه", "مراه", "نساء", "امراته", "زوجته", "زوجها", "حائض", "حيض", "حيضه", "نفاس",
          "نفساء", "استحاضه", "مستحاضه", "خمار", "جلباب", "ذي محرم", "ذات محرم", "صداق",
          "خلع", "مطلقه", "متوفي عنها", "جاريه", "ثيب", "ازواج النبي", "امهات المؤمنين"]

TOPICS = {
    "الحيض والاستحاضة": ["حائض", "حيض", "حيضه", "استحاضه", "مستحاضه", "نفاس", "نفساء", "طهر", "غسل"],
    "الحجاب والستر": ["خمار", "جلباب", "حجاب", "ستر", "عوره", "تبرج", "زينه", "ازار"],
    "السفر": ["تسافر", "سفر", "محرم", "ذي محرم", "ذات محرم"],
    "الزواج": ["نكاح", "خطبه", "تزوج", "صداق", "مهر", "ولي", "ثيب", "تنكح"],
    "الحقوق الزوجية والحياة الأسرية": ["زوج", "زوجته", "زوجها", "نفقه", "فراش", "عشره", "قسم", "غيره"],
    "الطلاق والخلع والعدة": ["طلاق", "طلق", "خلع", "عده", "ايلاء", "ظهار", "لعان", "متوفي عنها", "احداد", "مطلقه"],
    "العمل والمال": ["مال", "كسب", "عمل", "اجره", "صدقه", "هبه", "ميراث", "نفقه"],
    "الأمومة وتربية الأبناء": ["ام", "امه", "حضانه", "ولد", "ارضاع", "رضاعه", "ابنه", "بنات", "اولاد"],
    "العبادات": ["صلاه", "صيام", "صوم", "زكاه", "حج", "عمره", "وضوء", "مسجد", "اعتكاف", "جنازه", "عيد"],
    "المرأة والمجتمع": ["نساء", "امراه", "مراه", "بيعه", "شهاده", "جهاد", "ولايه"],
    "نساء النبي والصحابيات": ["ازواج النبي", "ازواجه", "نساءه", "امهات المؤمنين", "خديجه", "فاطمه", "حفصه", "ميمونه",
                              "جويريه", "سوده", "صفيه", "زينب", "ام سلمه", "ام حبيبه", "ام سليم", "ام عطيه"],
    "حقوق المرأة وكرامتها": ["استوصوا", "قوارير", "اكرام", "ظلم", "رفقا", "خيركم", "ايذاء", "ضرب"],
}
MONEY_EXCLUDE = ["ربا", "صرف", "ذهب", "فضه", "دينار", "درهم", "بيع", "بيوع", "ثمر", "نخل"]

CHAPTER_HINT = {
    ("bukhari", 6): ("الحيض والاستحاضة", True), ("muslim", 3): ("الحيض والاستحاضة", True),
    ("bukhari", 67): ("الزواج", False), ("muslim", 16): ("الزواج", False),
    ("bukhari", 68): ("الطلاق والخلع والعدة", False), ("muslim", 18): ("الطلاق والخلع والعدة", False),
    ("muslim", 19): ("الطلاق والخلع والعدة", False),
    ("bukhari", 69): ("الحقوق الزوجية والحياة الأسرية", False),
    ("muslim", 17): ("الأمومة وتربية الأبناء", False),
}


def classify(book: str, chapter_id: int, matn: str):
    strong = [k for k in STRONG if has(matn, k)]
    hint = CHAPTER_HINT.get((book, chapter_id))
    if strong or (hint and hint[1]):
        rel = "specific"
    elif hint:
        rel = "general_applicable"
    else:
        return "none", None, []
    scores = {}
    for topic, kws in TOPICS.items():
        hits = [k for k in kws if has(matn, k)]
        if topic == "العمل والمال" and any(has(matn, x) for x in MONEY_EXCLUDE) and not strong:
            hits = []
        if hits or (hint and hint[0] == topic):
            scores[topic] = (len(hits) + (2 if hint and hint[0] == topic else 0), hits)
    if scores:
        topic = max(scores, key=lambda t: scores[t][0])
        kws = scores[topic][1]
    else:
        topic, kws = "المرأة والمجتمع", []
    keywords = list(dict.fromkeys(strong + kws))[:8]
    return rel, topic, keywords


SCHEMA = """
CREATE TABLE hadith(
  id INTEGER PRIMARY KEY, book TEXT, book_chapter TEXT, number_in_book INTEGER,
  narrator_en TEXT, text_ar TEXT, matn TEXT, matn_display TEXT, topic TEXT, keywords TEXT,
  women_relevance TEXT, grade TEXT, grade_source TEXT, is_authentic INTEGER,
  source_ref TEXT, search_text TEXT,
  dorar_grade TEXT, dorar_muhaddith TEXT, dorar_source TEXT, dorar_number TEXT,
  dorar_url TEXT, dorar_link_kind TEXT);
CREATE TABLE IF NOT EXISTS weak_hadith(
  id INTEGER PRIMARY KEY, text_ar TEXT, grade TEXT, muhaddith TEXT, source TEXT,
  reason TEXT, authentic_alternative_id INTEGER REFERENCES hadith(id), search_text TEXT);
CREATE VIRTUAL TABLE hadith_fts USING fts5(search_text, content='hadith', content_rowid='id', tokenize='unicode61');
"""


def download(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    base = "https://raw.githubusercontent.com/A7med3bdulBaset/hadith-json/v1.2.0/db/by_book/the_9_books/"
    for b in ("bukhari", "muslim"):
        urllib.request.urlretrieve(base + b + ".json", data_dir / f"{b}.json")
        print("تم تنزيل", b)


def strip_al(t: str) -> str:
    for p in ("وال", "فال", "بال", "كال", "لل", "ال"):
        if t.startswith(p) and len(t) - len(p) >= 3:
            return t[len(p):]
    return t


def expand(text: str) -> str:
    toks = text.split()
    return " ".join(toks + [s for s in (strip_al(t) for t in toks) if s not in toks])


def build(data_dir: Path, out: Path):
    db = sqlite3.connect(out)
    db.executescript("DROP TABLE IF EXISTS hadith_fts; DROP TABLE IF EXISTS hadith;")
    db.executescript(SCHEMA)
    stats = {}
    for book in ("bukhari", "muslim"):
        d = json.load(open(data_dir / f"{book}.json", encoding="utf-8"))
        chap = {c["id"]: c["arabic"] for c in d["chapters"]}
        for h in d["hadiths"]:
            full = h["arabic"]
            matn, shown = split_matn(full)
            rel, topic, kws = classify(book, h["chapterId"], matn)
            stats[(book, rel)] = stats.get((book, rel), 0) + 1
            en = h.get("english") or {}
            search_text = expand(" ".join(filter(None, [matn, topic or "", " ".join(kws)])))
            db.execute(
                "INSERT INTO hadith(id,book,book_chapter,number_in_book,narrator_en,text_ar,matn,matn_display,topic,"
                "keywords,women_relevance,grade,grade_source,is_authentic,source_ref,search_text) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (h["id"], book, chap.get(h["chapterId"], ""), h["idInBook"], en.get("narrator", ""),
                 re.sub(r"\s+", " ", full).strip(), matn, shown, topic, "،".join(kws), rel,
                 "صحيح", "متفق على صحة ما في الصحيحين", 1,
                 f"{BOOK_AR[book]}، {chap.get(h['chapterId'], '')}", search_text))
    db.execute("INSERT INTO hadith_fts(rowid, search_text) SELECT id, search_text FROM hadith WHERE women_relevance!='none'")
    db.commit()
    for (book, rel), n in sorted(stats.items()):
        print(f"{book:8s} {rel:20s} {n}")
    return db


STOP = {"عن", "عنها", "عنه", "علي", "الي", "في", "من", "ما", "لا", "هل", "كيف", "حكم", "ماهو", "ماذا",
        "هذا", "هذه", "التي", "الذي", "اذا", "ان", "او", "ثم", "كان", "كانت", "بدون", "مع", "عند"}


def fts_query(q: str) -> str:
    toks = [strip_al(t) for t in norm(q).split() if len(t) >= 3 and t not in STOP]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(toks))


def hadith_link(r) -> dict:
    if r["dorar_url"] and r["dorar_link_kind"] == "direct":
        return {"url": r["dorar_url"], "kind": "direct"}
    words = r["matn"].split()
    raw = _TASHKEEL.sub("", r["matn_display"]).split()
    snippet = " ".join(raw[-12:] if words and words[0] in CHAIN_START else raw[:12])
    return {"url": "https://dorar.net/hadith/search?q=" + urllib.parse.quote(snippet), "kind": "search"}


def to_record(r) -> dict:
    has_dorar = r["dorar_grade"] and r["dorar_grade"] != NO_MATCH
    ref = r["source_ref"] + (f"، الصفحة أو الرقم {r['dorar_number']}" if has_dorar and r["dorar_number"] else "")
    return {
        "id": r["id"], "text": r["matn_display"], "narrator_en": r["narrator_en"],
        "topic": r["topic"], "keywords": r["keywords"].split("،") if r["keywords"] else [],
        "grade": {"value": r["grade"], "basis": r["grade_source"],
                  "dorar": ({"grade": r["dorar_grade"], "muhaddith": r["dorar_muhaddith"],
                             "source": r["dorar_source"], "number": r["dorar_number"]} if has_dorar else None)},
        "source": {"ref": ref, "book": BOOK_AR.get(r["book"], r["book"]), "chapter": r["book_chapter"]},
        "link": hadith_link(r), "women_relevance": r["women_relevance"],
    }


def search(db_path: Path, query: str, k: int = 5, include_general: bool = False, as_json: bool = False):
    db = connect_ro(db_path)
    db.row_factory = sqlite3.Row
    rel = "('specific','general_applicable')" if include_general else "('specific')"
    rows = db.execute(
        f"SELECT h.* FROM hadith_fts JOIN hadith h ON h.id=hadith_fts.rowid "
        f"WHERE hadith_fts MATCH ? AND h.women_relevance IN {rel} AND h.is_authentic=1 "
        f"ORDER BY rank LIMIT ?", (fts_query(query), k)).fetchall()
    recs = [to_record(r) for r in rows]
    if as_json:
        print(json.dumps(recs, ensure_ascii=False, indent=2))
        return recs
    for x in recs:
        d = x["grade"]["dorar"]
        dorar = f" | الدرر: {d['grade']} ({d['muhaddith']})" if d else ""
        print(f"[{x['topic']}] {x['source']['ref']}\n  {x['text'][:230]}...\n"
              f"  الحكم: {x['grade']['value']} ({x['grade']['basis']}){dorar}\n"
              f"  الرابط ({x['link']['kind']}): {x['link']['url']}\n")
    if not recs:
        print("لم أجد نصاً مباشراً في المصادر المتاحة.")
    return recs


def export(db_path: Path, out: Path):
    db = connect_ro(db_path)
    db.row_factory = sqlite3.Row
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for r in db.execute("SELECT * FROM hadith WHERE women_relevance='specific' ORDER BY id"):
            rec = to_record(r)
            rec["search_text"] = r["search_text"]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"تم تصدير {n} حديثاً إلى {out}")


DORAR_API = "https://dorar.net/dorar_api.json?skey="
DORAR_SEARCH = "https://dorar.net/hadith/search?q="
CHAIN_START = {"حدثنا", "وحدثنا", "حدثني", "وحدثني", "اخبرنا", "واخبرنا", "اخبرني", "واخبرني", "انبانا"}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "BaseerahAI-hackathon/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("ثبّت المكتبة أولاً: pip install beautifulsoup4")
    return BeautifulSoup(html, "html.parser")


def _clean(s: str) -> str:
    return re.sub(r"^\s*\d+\s*-\s*", "", s).strip()


def dorar_parse(html: str):
    soup = _soup(html)
    out = []
    for hd, info in zip(soup.select(".hadith"), soup.select(".hadith-info")):
        fields, label = {}, None
        for node in info.descendants:
            if hasattr(node, "attrs"):
                if "info-subtitle" in (node.get("class") or []):
                    label = node.get_text(strip=True).rstrip(":")
                    fields[label] = ""
            elif label and "info-subtitle" not in (node.parent.get("class") or []):
                fields[label] += str(node)
        out.append({"text": _clean(hd.get_text(" ", strip=True)),
                    "fields": {k: re.sub(r"\s+", " ", v).strip() for k, v in fields.items()}})
    return out


def _coverage(text: str, words: list) -> float:
    t = norm(_clean(text))
    m = _MATN_START.match(t)
    if m:
        t = t[m.end():].strip()
    t = t.split()
    if not t:
        return 0.0
    blocks = SequenceMatcher(None, t, words, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(t)


def dorar_enrich(db_path: Path, limit: int, delay: float, query: str = "", reset: bool = False):
    db = sqlite3.connect(db_path)
    if reset:
        db.execute("UPDATE hadith SET dorar_grade=NULL, dorar_muhaddith=NULL, dorar_source=NULL, "
                   "dorar_number=NULL, dorar_url=NULL, dorar_link_kind=NULL")
        db.commit()
    if query:
        rows = db.execute(
            "SELECT h.id, h.book, h.matn, h.matn_display FROM hadith_fts JOIN hadith h ON h.id=hadith_fts.rowid "
            "WHERE hadith_fts MATCH ? AND h.women_relevance='specific' AND h.dorar_grade IS NULL "
            "ORDER BY rank LIMIT ?", (fts_query(query), limit)).fetchall()
    else:
        rows = db.execute("SELECT id, book, matn, matn_display FROM hadith WHERE women_relevance='specific' "
                          "AND dorar_grade IS NULL ORDER BY id LIMIT ?", (limit,)).fetchall()
    ok = miss = 0
    for hid, book, matn, shown in rows:
        words = matn.split()
        raw = _TASHKEEL.sub("", shown).split()
        snippet = " ".join(raw[-12:] if words and words[0] in CHAIN_START else raw[:12])
        try:
            items = dorar_parse(json.loads(_get(DORAR_API + urllib.parse.quote(snippet)))["ahadith"]["result"])
        except Exception as e:
            print(f"توقفت عند الحديث {hid}: {e}")
            break
        cands = [(it, _coverage(it["text"], words)) for it in items
                 if BOOK_AR[book] in it["fields"].get("المصدر", "")]
        cands = [(it, s) for it, s in cands if s >= 0.9]
        pick = max(cands, key=lambda x: (x[1], len(x[0]["text"])), default=None)
        search_url = DORAR_SEARCH + urllib.parse.quote(snippet)
        if pick:
            it = pick[0]
            f = it["fields"]
            url, kind = search_url, "search"
            db.execute("UPDATE hadith SET dorar_grade=?, dorar_muhaddith=?, dorar_source=?, dorar_number=?, "
                       "dorar_url=?, dorar_link_kind=? WHERE id=?",
                       (f.get("خلاصة حكم المحدث"), f.get("المحدث"), f.get("المصدر"),
                        f.get("الصفحة أو الرقم"), url, kind, hid))
            ok += 1
        else:
            db.execute("UPDATE hadith SET dorar_grade=?, dorar_url=?, dorar_link_kind='search' WHERE id=?",
                       (NO_MATCH, search_url, hid))
            miss += 1
        db.commit()
        time.sleep(delay)
    print(f"انتهى. مطابَق: {ok} | لم يُطابَق: {miss}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["download", "build", "search", "dorar", "export"])
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default=None)
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--query", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--general", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.cmd == "download":
        download(Path(a.data_dir))
    elif a.cmd == "build":
        build(Path(a.data_dir), Path(a.out or a.db))
    elif a.cmd == "search":
        search(Path(a.db), a.query, k=a.k, include_general=a.general, as_json=a.json)
    elif a.cmd == "export":
        export(Path(a.db), Path(a.out or "hadith.jsonl"))
    else:
        dorar_enrich(Path(a.db), a.limit, a.delay, a.query, a.reset)
