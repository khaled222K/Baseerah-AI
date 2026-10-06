"""Hadith explanation: grounding checks run on the generated text (LLM replaced by a stub)."""
import json
import pytest
import explain
from db import connect_ro

HID = 5882  # "ليس الشديد بالصرعة إنما الشديد الذي يملك نفسه عند الغضب"


@pytest.fixture(autouse=True)
def fresh_cache():
    explain._CACHE.clear()
    yield
    explain._CACHE.clear()


def stub(monkeypatch, payload):
    calls = []
    def fake(system, user, backend=None):
        calls.append(user)
        return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(explain, "llm_call", fake)
    return calls


def test_grounded_explanation_is_returned_with_stored_text(monkeypatch):
    calls = stub(monkeypatch, {"ok": True, "explanation": "القوة الحقيقية في «يملك نفسه عند الغضب» لا في غلبة الناس.",
                               "words": [{"word": "الصرعة", "meaning": "الذي يصرع الناس كثيرا"},
                                         {"word": "كلمة غير موجودة", "meaning": "..."}]})
    r = explain.explain(HID, "anthropic")
    assert r["status"] == "explained" and "يملك نفسه" in r["explanation"]
    assert [w["word"] for w in r["words"]] == ["الصرعة"]          # gloss for a word not in the hadith is dropped
    stored = connect_ro("baseerah.db").execute("SELECT matn_display FROM hadith WHERE id=?", (HID,)).fetchone()[0]
    assert r["text"] == stored and stored in calls[0]              # the model gets the DB text, verbatim


@pytest.mark.parametrize("bad,problem", [
    ("قال النبي «من كظم غيظا وهو قادر» وهذا معنى الحديث.", "quote"),   # quotation not in the hadith
    ("ورد هذا في الحديث رقم 6116 من الصحيح.", "number"),               # number not in the text
    ("وقد رواه الترمذي أيضا بلفظ قريب.", "collection"),                 # another collection named
])
def test_ungrounded_explanation_is_rejected(monkeypatch, bad, problem):
    stub(monkeypatch, {"ok": True, "explanation": bad, "words": []})
    r = explain.explain(HID, "anthropic")
    assert r["status"] == "rejected" and r["explanation"] is None and problem in r["problems"]


def test_ordinary_words_are_not_mistaken_for_collections():
    assert explain.grounded("على المسلم أن يملك نفسه، وكذلك الحاكم والمحكوم.", "ليس الشديد بالصرعة") == []


def test_not_explainable_unparseable_and_failure(monkeypatch):
    stub(monkeypatch, {"ok": False, "explanation": ""})
    assert explain.explain(HID, "anthropic")["status"] == "not_explainable"
    explain._CACHE.clear()
    stub(monkeypatch, "not json at all")
    assert explain.explain(HID, "anthropic")["status"] == "error"
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(explain, "llm_call", boom)
    r = explain.explain(HID, "anthropic")
    assert r["status"] == "error" and r["explanation"] is None
    assert (HID, "anthropic") not in {k[:2] for k in explain._CACHE}   # failures are not cached


def test_retrieval_mode_and_missing_hadith(monkeypatch):
    calls = stub(monkeypatch, {"ok": True, "explanation": "x"})
    assert explain.explain(HID, "retrieval")["status"] == "unavailable" and not calls
    assert explain.explain(999999, "anthropic")["status"] == "not_found"


def test_stored_note_is_passed_and_returned(monkeypatch):
    calls = stub(monkeypatch, {"ok": True, "explanation": "شرح موجز.", "words": []})
    r = explain.explain(301, "anthropic")          # hadith 301 has a stored note in hadith_notes
    assert r["stored_note"]["text"] and r["stored_note"]["text"] in calls[0]


def test_garbled_script_is_rejected(monkeypatch):
    stub(monkeypatch, {"ok": True, "explanation": "القوة في ضبط النفس، والعبatchا هنا معناها.", "words": []})
    assert "script" in explain.explain(HID, "anthropic")["problems"]


def test_word_glosses_off_by_default_for_local_models(monkeypatch):
    monkeypatch.delenv("BASEERAH_EXPLAIN_WORDS", raising=False)
    stub(monkeypatch, {"ok": True, "explanation": "شرح موجز.", "words": [{"word": "الصرعة", "meaning": "معنى"}]})
    assert explain.explain(HID, "openai")["words"] == []
    explain._CACHE.clear()
    assert explain.explain(HID, "anthropic")["words"]
