"""Copy measured results from evaluate.py runs (runs/*.json) into eval_metrics.json, served by GET /model-info.
Numbers are copied from the run files, never typed by hand. Re-run after re-evaluating."""
import json, sys
from pathlib import Path

RUNS = Path(sys.argv[1] if len(sys.argv) > 1 else "runs")
pick = lambda m: {k: m[k] for k in ("R@1", "R@3", "R@10", "MRR", "n")}
allr = json.load(open(RUNS / "all.json"))["report"]
rules = json.load(open(RUNS / "rules.json"))["report"]
gulf = json.load(open(RUNS / "gulf_rules.json"))["report"]
e2e = json.load(open(RUNS / "e2e_gate.json"))
legacy, cur = e2e["legacy"], e2e["hybrid+rerank"]
out = {
    "eval_set": "eval_set.json (78 scored questions with verified expected IDs + 8 out-of-scope questions)",
    "definitions": {"R@k": "نسبة الأسئلة التي ظهر فيها حديث أو آية متوقعة ضمن أول k نتائج",
                    "MRR": "متوسط مقلوب ترتيب أول نتيجة صحيحة ضمن أول 10 نتائج (1 = الأولى دائمًا)"},
    "retrieval": [
        {"variant": "fts", **pick(allr["fts"]["overall"])},
        {"variant": "vector", **pick(allr["vector"]["overall"])},
        {"variant": "hybrid", **pick(allr["hybrid"]["overall"])},
        {"variant": "hybrid+rerank", **pick(allr["hybrid+rerank"]["overall"])},
        {"variant": "hybrid+rerank+rewrites (default)", **pick(rules["hybrid+rerank"]["overall"])},
    ],
    "gulf_holdout": {"variant": "default", **pick(gulf["hybrid+rerank"]["overall"])},
    "end_to_end": {
        "default": {"expected_text_shown": cur["hit_pos"], "positives": cur["n_pos"],
                    "out_of_scope_rejected": cur["abstain_neg"], "out_of_scope": cur["n_neg"]},
        "original_pipeline": {"expected_text_shown": legacy["hit_pos"], "positives": legacy["n_pos"],
                              "out_of_scope_rejected": legacy["abstain_neg"], "out_of_scope": legacy["n_neg"]},
    },
    "caveats": [
        "عينة صغيرة (78 سؤالًا)، وهامش الخطأ نحو ±11 نقطة مئوية.",
        "قوائم الإجابات المتوقعة قد لا تشمل كل روايات الحديث، فالنتائج حدّ أدنى.",
        "أسئلة الاختبار كتبها مطوّر النظام نفسه، ولم تُختبر بعد على أسئلة مستخدمين حقيقيين.",
        "اللهجة الخليجية غير المرئية أضعف بكثير من الفصحى.",
        "لم يُقَس وضع الشرح المولَّد بالنموذج اللغوي.",
    ],
}
json.dump(out, open("eval_metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out["retrieval"][-1], ensure_ascii=False), out["end_to_end"]["default"])
