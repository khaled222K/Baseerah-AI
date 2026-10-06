"""CLI: python ask.py "سؤالك" [--mode retrieval|anthropic|openai] [--json]

Modes: retrieval = local texts only, no LLM (default when BASEERAH_LLM is unset);
anthropic = explanation via the Anthropic API (ANTHROPIC_API_KEY);
openai = explanation via a local OpenAI-compatible server (BASEERAH_BASE_URL, e.g. Ollama or llama.cpp)."""
import argparse, json, os
from answer import answer, render, MODES


def default_mode():
    return os.environ.get("BASEERAH_LLM") or "retrieval"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--mode", choices=MODES, default=None)
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--vec", default="embeddings.db")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = answer(a.query, a.db, a.vec, a.mode or default_mode())
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        render(out)
