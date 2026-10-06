"""Retrieval evaluation on eval_set.json: Recall@1/3/10 and MRR@10 per variant.

Recall@k here is the share of questions with at least one expected unit in the top k (hit rate).
Units: hadith:<id> or ayah:<surah>:<ayah>; a tafsir record counts as its ayah.
Only items with verified=true and a non-empty expected list are scored."""
import argparse, json, time
from retrieve import get_retriever, Retriever

KS = (1, 3, 10)
VARIANTS = {
    "fts": dict(mode="fts"),
    "vector": dict(mode="vector"),
    "hybrid": dict(mode="hybrid"),
    "hybrid+rerank": dict(mode="hybrid", rerank=True),
}


def load_items(path, types=None):
    items = json.load(open(path, encoding="utf-8"))["items"]
    scored = [it for it in items if it.get("verified") is True and it["expected"]]
    if types:
        scored = [it for it in scored if it["type"] in types]
    return scored, len(items) - len([it for it in items if it.get("verified") is True])


def ranked_units(hits):
    out = []
    for h in hits:
        if h["unit"] not in out:
            out.append(h["unit"])
    return out


def first_rank(units, expected):
    exp = set(expected)
    return next((i + 1 for i, u in enumerate(units) if u in exp), None)


def score(ranks):
    n = len(ranks)
    m = {f"R@{k}": round(sum(1 for r in ranks if r and r <= k) / n, 3) for k in KS}
    m["MRR"] = round(sum(1 / r for r in ranks if r and r <= max(KS)) / n, 3)
    m["n"] = n
    return m


def run(retriever, items, kw, rewrites_fn=None, depth=30):
    ranks, per = [], []
    t0 = time.time()
    for it in items:
        rw = rewrites_fn(it["question"]) if rewrites_fn else ()
        hits = retriever.search(it["question"], k=depth, rewrites=rw, **kw)
        r = first_rank(ranked_units(hits), it["expected"])
        ranks.append(r)
        per.append({"id": it["id"], "rank": r})
    return ranks, per, round((time.time() - t0) / max(len(items), 1), 3)


def breakdown(items, per):
    rank = {p["id"]: p["rank"] for p in per}
    groups = {}
    for it in items:
        for g in (it["type"], it["dialect"], "hadith" if it["expected"][0].startswith("hadith") else "ayah"):
            groups.setdefault(g, []).append(rank[it["id"]])
    return {g: score(r) for g, r in sorted(groups.items())}


def e2e(items, search, rerank):
    """Full pipeline in retrieval mode: does it abstain on negatives, and do the shown texts contain an expected unit?"""
    import evidence
    from answer import answer
    evidence.SEARCH, evidence.RERANK = search, rerank
    out = {"answered_pos": 0, "hit_pos": 0, "n_pos": 0, "abstain_neg": 0, "n_neg": 0, "per_item": []}
    for it in items:
        o = answer(it["question"], mode="retrieval")
        shown = {u for u in (unit_of(e) for e in o["texts"]) if u}
        if it["type"] == "negative":
            out["n_neg"] += 1
            out["abstain_neg"] += o["status"] == "insufficient"
        else:
            out["n_pos"] += 1
            out["answered_pos"] += o["status"] in ("answer", "referral", "identified")
            out["hit_pos"] += bool(shown & set(it["expected"]))
        out["per_item"].append({"id": it["id"], "status": o["status"], "hit": bool(shown & set(it["expected"]))})
    return out


def unit_of(e):
    if e["kind"] == "hadith":
        return f"hadith:{e['id']}"
    return e.get("unit")


def table(rows):
    head = "| variant | n | R@1 | R@3 | R@10 | MRR | s/query |\n|---|---|---|---|---|---|---|"
    lines = [f"| {name} | {m['n']} | {m['R@1']} | {m['R@3']} | {m['R@10']} | {m['MRR']} | {m['sec']} |" for name, m in rows]
    return "\n".join([head, *lines])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="eval_set.json")
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--vec", default="embeddings.db")
    ap.add_argument("--variants", default="fts,vector,hybrid,hybrid+rerank")
    ap.add_argument("--types", default="topic,quote,paraphrase")
    ap.add_argument("--dense-norm", action="store_true", help="embed norm(query) instead of clean(query)")
    ap.add_argument("--rewrites", choices=["none", "rules", "llm"], default="none")
    ap.add_argument("--out", default="")
    ap.add_argument("--e2e", default="", help="comma list of search configs: legacy,hybrid,hybrid+rerank")
    a = ap.parse_args()
    if a.e2e:
        items = [it for it in json.load(open(a.eval, encoding="utf-8"))["items"] if it.get("verified") is True]
        res = {}
        for cfg in a.e2e.split(","):
            res[cfg] = e2e(items, "legacy" if cfg == "legacy" else "hybrid", cfg.endswith("rerank"))
            m = res[cfg]
            print(f"{cfg:14s} positives answered {m['answered_pos']}/{m['n_pos']} | expected text shown "
                  f"{m['hit_pos']}/{m['n_pos']} | negatives abstained {m['abstain_neg']}/{m['n_neg']}")
        if a.out:
            json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        raise SystemExit
    items, skipped = load_items(a.eval, set(a.types.split(",")))
    print(f"scored items: {len(items)} | excluded (unverified): {skipped}")
    r = get_retriever(a.db, a.vec, "all", a.dense_norm)
    if r.missing:
        print(f"warning: {r.missing} hadith have no vector yet")
    rw = None
    if a.rewrites != "none":
        from understand import understand
        rw = lambda q: understand(q, backend="rules" if a.rewrites == "rules" else None)["rewrites"]
    rows, report = [], {}
    for name in a.variants.split(","):
        Retriever.qvec.cache_clear()
        ranks, per, sec = run(r, items, VARIANTS[name], rw)
        m = score(ranks)
        m["sec"] = sec
        rows.append((name, m))
        report[name] = {"overall": m, "breakdown": breakdown(items, per), "per_item": per}
    print(table(rows))
    for name, rep in report.items():
        print(f"\n{name} by group:")
        for g, m in rep["breakdown"].items():
            print(f"  {g:10s} n={m['n']:3d} R@1={m['R@1']} R@3={m['R@3']} R@10={m['R@10']} MRR={m['MRR']}")
    if a.out:
        json.dump({"args": vars(a), "report": report}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
