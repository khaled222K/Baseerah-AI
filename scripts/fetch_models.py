"""Download the embedding and reranker models at build time so the service can run with HF_HUB_OFFLINE=1
(no calls to huggingface.co at runtime). Set HF_HOME to a directory that ships with the build."""
import os
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
from sentence_transformers import SentenceTransformer, CrossEncoder
from retrieve import RERANKER
from semantic import MODEL

SentenceTransformer(MODEL)
CrossEncoder(RERANKER)
print("cached:", MODEL, RERANKER, "in", os.environ.get("HF_HOME", "~/.cache/huggingface"))
