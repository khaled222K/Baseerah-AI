"""Run the edge-case benchmark (benchmark/cases.json) through answer.answer() and save the real outputs.

  python scripts/run_benchmark.py                       # retrieval-only mode (no model)
  BASEERAH_LLM=openai BASEERAH_BASE_URL=http://localhost:11434/v1 BASEERAH_MODEL=aya-expanse:8b \\
      python scripts/run_benchmark.py --mode openai      # with the local model

Writes benchmark/results-<mode>.json. Nothing is graded automatically here: the expected behavior of each case
is a judgement call, so docs/BENCHMARK.md records the outputs next to the expectation."""
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def ref(e):
    if e["kind"] == "hadith":
        return f"hadith {e['id']} ({e['ref']}، رقم {e['number']})"
    return f"{e['kind']} {e['ref']}"


def main():
    from answer import answer, MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="retrieval", choices=["retrieval", "anthropic", "openai"])
    ap.add_argument("--cases", default=str(ROOT / "benchmark" / "cases.json"))
    ap.add_argument("--only", default="", help="comma list of case ids")
    a = ap.parse_args()
    cases = json.load(open(a.cases, encoding="utf-8"))["cases"]
    only = {int(x) for x in a.only.split(",") if x}
    results = []
    for c in cases:
        if only and c["id"] not in only:
            continue
        t0 = time.time()
        o = answer(c["query"], str(ROOT / "baseerah.db"), str(ROOT / "embeddings.db"), a.mode)
        r = {"id": c["id"], "query": c["query"], "expect": c["expect"], "status": o["status"], "message": o["message"],
             "notice": o["notice"], "texts": [ref(e) for e in o["texts"]], "explanation": o["explanation"],
             "error": o["error"], "seconds": round(time.time() - t0, 1)}
        results.append(r)
        print(f"#{c['id']} {r['status']} ({r['seconds']}s) {c['query']}\n   texts: {r['texts']}\n   "
              f"message: {r['message']}\n   notice: {r['notice']}\n   explanation: {r['explanation']}\n", flush=True)
    out = ROOT / "benchmark" / f"results-{a.mode}.json"
    json.dump({"mode": a.mode, "model": None if a.mode == "retrieval" else MODEL, "results": results},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
