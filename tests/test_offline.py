import os
import envfile
from retrieve import RERANKER
from semantic import MODEL


def test_offline_guard_lists_the_runtime_models():
    assert set(envfile.HF_MODELS) == {MODEL, RERANKER}


def test_offline_guard_respects_an_explicit_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    assert envfile.offline_if_cached() is False and os.environ["HF_HUB_OFFLINE"] == "0"


def test_offline_guard_needs_both_models_cached(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    (tmp_path / f"models--{MODEL.replace('/', '--')}" / "snapshots" / "abc").mkdir(parents=True)
    assert envfile.offline_if_cached() is False and "HF_HUB_OFFLINE" not in os.environ
    (tmp_path / f"models--{RERANKER.replace('/', '--')}" / "snapshots" / "def").mkdir(parents=True)
    assert envfile.offline_if_cached() is True and os.environ["HF_HUB_OFFLINE"] == "1"


def test_runtime_databases_refuse_writes():
    import sqlite3
    import pytest
    from db import connect_ro
    for path in ("baseerah.db", "embeddings.db"):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connect_ro(path).execute("CREATE TABLE audit_probe(x)")
