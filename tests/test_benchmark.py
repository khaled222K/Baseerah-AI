"""Deterministic checks (retrieval-only mode, no model) for the edge cases in benchmark/cases.json.
Generated explanations are not tested here; scripts/run_benchmark.py records them (docs/BENCHMARK.md)."""
import json
import pytest
from answer import answer, AYAH_ALTERED, AYAH_EXACT, NON_ARABIC, NO_TRANSLATION
from build_hadith_db import norm
from check import check
from db import connect_ro
from evidence import assess, word_count, MESSAGES
from understand import rules, non_arabic

CASES = {c["id"]: c["query"] for c in json.load(open("benchmark/cases.json", encoding="utf-8"))["cases"]}


@pytest.fixture(scope="module")
def db():
    return connect_ro("baseerah.db")


def stored(db, e):
    """The displayed text is exactly the stored one."""
    if e["kind"] == "hadith":
        return db.execute("SELECT matn_display FROM hadith WHERE id=?", (e["id"],)).fetchone()[0] == e["text"]
    return db.execute("SELECT count(*) FROM records WHERE text_original=?", (e["text"],)).fetchone()[0] > 0


def test_personal_case_is_referred():  # case 5
    o = answer(CASES[5], mode="retrieval")
    assert o["status"] == "referral" and "أهل العلم" in o["message"]


def test_personal_case_without_evidence_is_still_referred():
    a = assess("انا حائض ونزل مني دم بعد الطهر هل صلاتي صحيحة")
    assert a["status"] == "referral"
    assert a["message"] in (MESSAGES["referral"], MESSAGES["referral_none"])


def test_requested_hadith_is_never_fabricated(db):  # case 6
    o = answer(CASES[6], mode="retrieval")
    assert all(stored(db, e) for e in o["texts"])
    assert not any("النظافه من الايمان" in norm(e["text"]) for e in o["texts"])


def test_non_arabic_questions_are_searched():  # cases 8 and 12
    assert word_count(CASES[12]) >= 2 and non_arabic(CASES[12])
    assert rules(CASES[12])["rewrites"] == ["الجهاد"]
    o = answer(CASES[12], mode="retrieval")
    assert o["status"] != "clarify" and NON_ARABIC in o["notice"]
    o = answer(CASES[8], mode="retrieval")
    assert o["status"] != "clarify" and NO_TRANSLATION in o["notice"]


def test_altered_ayah_is_flagged_and_corrected(db):  # case 11
    o = answer(CASES[11], mode="retrieval")
    assert o["status"] == "identified" and o["message"] == AYAH_ALTERED
    (e,) = o["texts"]
    assert e["kind"] == "ayah" and e["unit"] == "ayah:2:183" and stored(db, e)
    assert CASES[11] not in o["message"]


def test_exact_ayah_is_identified():
    o = answer("يا أيها الذين آمنوا كتب عليكم الصيام كما كتب على الذين من قبلكم", mode="retrieval")
    assert o["status"] == "identified" and o["message"] == AYAH_EXACT and o["texts"][0]["unit"] == "ayah:2:183"


def test_verify_requires_exact_quran_wording():
    altered = check(CASES[11])
    assert altered["status"] == "partial_match" and altered["exact"] is False
    exact = check("قال تعالى وأحل الله البيع وحرم الربا")
    assert exact["exact"] is True and exact["match"]["unit"] == "ayah:2:275"
    assert check("وأحل الله البيع وحرم الربا")["status"] == "matched"


def test_questions_are_not_mistaken_for_quotes():  # cases 1, 9: questions go through retrieval, not identification
    for i in (1, 9):
        assert answer(CASES[i], mode="retrieval")["status"] in ("answer", "insufficient")


def test_unreachable_model_falls_back_to_texts_quickly(monkeypatch):
    """Mode A fallback: with the LLM down, the retrieved texts are still shown, without an explanation."""
    import time
    from answer import NO_MODEL
    monkeypatch.setenv("BASEERAH_BASE_URL", "http://127.0.0.1:9/v1")  # nothing listens here
    t0 = time.time()
    o = answer("ما حق الجار في الإسلام؟", mode="openai")
    assert o["texts"] and o["explanation"] is None and NO_MODEL in o["notice"] and o["error"]
    assert time.time() - t0 < 60


def test_personal_case_never_gets_a_generated_ruling(monkeypatch):
    """Case 5: in LLM mode the referral shows texts only; the model is not even called."""
    import answer as A
    monkeypatch.setattr(A, "llm_call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")))
    o = A.answer(CASES[5], mode="openai")
    assert o["status"] == "referral" and o["explanation"] is None and o["texts"]


def test_asterisk_quotes_are_checked():
    from answer import quotes_ok
    src = [{"text": "وَجَعَلَهَا كَلِمَةَۢ بَاقِيَةࣰ فِي عَقِبِهِۦ لَعَلَّهُمۡ يَرۡجِعُونَ"}]
    assert quotes_ok("كما قال *وجعلها كلمة باقية في عقبه*", src)
    assert not quotes_ok("كما قال *كلمة غير موجودة*", src)
