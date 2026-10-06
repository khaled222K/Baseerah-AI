"""Load KEY=VALUE lines from a local .env file into os.environ (existing variables win).

.env is git-ignored: it is where your API key lives on your machine. Never commit it."""
import os
from pathlib import Path


def load(path=None):
    p = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


# Models loaded at runtime (semantic.MODEL and retrieve.RERANKER; tests/test_offline.py checks they stay in sync).
HF_MODELS = ("intfloat/multilingual-e5-small", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")


def hf_cache():
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub"


def offline_if_cached(models=HF_MODELS):
    """Once both models are in the local Hugging Face cache, turn off all Hub calls (update checks included),
    so a running Baseerah never contacts huggingface.co. An explicit HF_HUB_OFFLINE=0 or 1 is left alone.
    This must run before huggingface_hub is imported, which reads the variable at import time."""
    if "HF_HUB_OFFLINE" in os.environ:
        return os.environ["HF_HUB_OFFLINE"] == "1"
    cache = hf_cache()
    if all(any((cache / f"models--{m.replace('/', '--')}" / "snapshots").glob("*/")) for m in models):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        return True
    return False


load()
offline_if_cached()
