"""Contract tests for the endpoints the web frontend uses (frontend/js/api.js normalizers)."""
import pytest
from fastapi.testclient import TestClient
from db import connect_ro


@pytest.fixture(scope="module")
def client():
    import api
    with TestClient(api.app) as c:
        yield c


def test_chat_answered_sources_are_verbatim(client):
    d = client.post("/chat", json={"question": "ما حق الجار في الإسلام؟"}).json()
    assert d["status"] == "answered" and d["sources"]
    db = connect_ro("baseerah.db")
    for s in d["sources"]:
        assert set(s) >= {"id", "type", "name", "reference", "text", "url"}
        if s["type"] == "hadith":
            hid = int(s["id"].split("-")[1])
            assert s["text"] == db.execute("SELECT matn_display FROM hadith WHERE id=?", (hid,)).fetchone()[0]


def test_chat_off_topic_is_insufficient(client):
    d = client.post("/chat", json={"question": "ما هي عاصمة فرنسا؟"}).json()
    assert d["status"] == "insufficient_evidence" and d["sources"] == [] and d["answer"] is None


def test_chat_rejects_empty_and_long_without_trace(client):
    for body in ({"question": ""}, {"question": "س" * 1001}, {}):
        r = client.post("/chat", json=body)
        assert r.status_code == 422 and r.json()["status"] == "error" and "Traceback" not in r.text


@pytest.mark.parametrize("text,status", [
    ("لا إكراه في الدين", "matched"),
    ("إنما الأعمال بالنيات وإنما لكل امرئ ما نوى", "matched"),
    ("من حسن إسلام المرء تركه ما لا يعنيه", "not_matched"),   # not in the two Sahihs
    ("اطلبوا العلم ولو في الصين", "not_matched"),             # must not be attributed to a stored hadith
    ("كيف حالك", "insufficient_evidence"),
])
def test_verify_statuses(client, text, status):
    d = client.post("/verify", json={"text": text}).json()
    assert d["status"] == status and d["message"]
    assert bool(d["sources"]) == (status == "matched")


def test_sources_and_model_info(client):
    cats = {c["key"]: c for c in client.get("/sources").json()["categories"]}
    assert cats["quran"]["count"] == 6236 and cats["hadith"]["count"] == 14736 and cats["tafsir"]["count"] == 6236
    m = client.get("/model-info").json()
    assert m["retrieval"]["embedding_model"] == "intfloat/multilingual-e5-small"
    assert m["evaluation"] is None or m["evaluation"]["retrieval"][-1]["MRR"] > 0
