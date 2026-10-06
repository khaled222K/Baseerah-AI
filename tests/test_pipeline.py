import pytest
from db import connect_ro
from retrieve import rrf
from understand import rules, parse


def test_rrf_orders_by_fused_rank():
    order, fused = rrf([["a", "b", "c"], ["b", "a"], ["b"]])
    assert order[0] == "b" and set(order) == {"a", "b", "c"}
    assert fused["b"] > fused["a"] > fused["c"]


def test_rules_rewrite_gulf():
    u = rules("وش وصية النبي للي يعصب بسرعة؟")
    assert u["rewrites"] == ["ما وصيه النبي للذي يغضب بسرعه"]
    assert "يغضب" in u["keywords"] and u["intent"] == "question"
    assert rules("حديث ان الصدقة ما تنقص المال")["intent"] == "hadith_lookup"


def test_parse_llm_understanding_is_clipped():
    raw = 'نص {"intent": "x", "rewrites": ["ما حكم الربا", "' + "كلمة " * 40 + '"], "keywords": ["ربا", 3]}'
    d = parse(raw)
    assert d == {"intent": "question", "rewrites": ["ما حكم الربا"], "keywords": ["ربا"]}
    assert parse("no json") is None


@pytest.fixture(scope="module")
def db():
    c = connect_ro("baseerah.db")
    yield c


def test_identify_quote(db):
    from identify import identify
    top = identify("ليس الشديد بالصرعة")["matches"][0]
    assert top["id"] in (5882, 13757, 13758) and top["match"] == "quote"
    assert top["text"] == db.execute("SELECT matn_display FROM hadith WHERE id=?", (top["id"],)).fetchone()[0]


def test_retrieval_mode_texts_are_verbatim(db):
    from answer import answer
    out = answer("ما حق الجار في الإسلام؟", mode="retrieval")
    assert out["status"] in ("answer", "referral") and out["texts"] and out["explanation"] is None
    for e in out["texts"]:
        if e["kind"] == "hadith":
            src = db.execute("SELECT matn_display FROM hadith WHERE id=?", (e["id"],)).fetchone()[0]
        else:
            src = db.execute("SELECT text_original FROM records WHERE reference=? AND source=?",
                             (e["ref"], "quran" if e["kind"] == "ayah" else "tafsir")).fetchone()[0]
        assert e["text"] == src


def test_out_of_scope_says_no_evidence():
    from answer import answer
    from evidence import MESSAGES
    out = answer("ما هي عاصمة فرنسا؟", mode="retrieval")
    assert out["status"] == "insufficient" and out["message"] == MESSAGES["insufficient"] and not out["texts"]
