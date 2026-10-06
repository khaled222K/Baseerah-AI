"""FastAPI endpoint: uvicorn api:app --port 8000, then GET /ask?q=...&mode=retrieval (or POST /ask {"q": ...})."""
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from answer import answer, MODES
from ask import default_mode

DB = os.environ.get("BASEERAH_DB", "baseerah.db")
VEC = os.environ.get("BASEERAH_VEC", "embeddings.db")
app = FastAPI(title="Baseerah")


class Ask(BaseModel):
    q: str
    mode: str | None = None


@app.on_event("startup")
def warm():
    from retrieve import get_retriever
    get_retriever(DB, VEC).qvec("بسم الله")


def run(q, mode):
    mode = mode or default_mode()
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    if not q.strip():
        raise HTTPException(400, "q is empty")
    return answer(q, DB, VEC, mode)


@app.get("/ask")
def ask_get(q: str, mode: str | None = None):
    return run(q, mode)


@app.post("/ask")
def ask_post(body: Ask):
    return run(body.q, body.mode)
