"""Hybrid retrieval over the local databases: FTS5 (BM25) + dense e5 vectors, fused with
Reciprocal Rank Fusion, with an optional cross-encoder reranker. Fully local and read-only."""
import argparse, functools
import numpy as np
from build_hadith_db import norm
from db import connect_ro
from semantic import load_model, prefix, clean, terms_query, QURAN_WORDS

RRF_K = 60
POOL = 50
RERANK_POOL = 30
RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
MODES = ("fts", "vector", "hybrid")


def rrf(lists, k=RRF_K):
    fused = {}
    for ranked in lists:
        for rank, key in enumerate(ranked):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused, key=fused.get, reverse=True), fused


@functools.lru_cache(maxsize=2)
def load_reranker(name):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(name, max_length=512)


class Retriever:
    def __init__(self, db_path="baseerah.db", vec_path="embeddings.db", scope="all", dense_norm=False):
        self.db = connect_ro(db_path)
        self.vdb = connect_ro(vec_path)
        self.scope = scope
        self.dense_norm = dense_norm
        self.model_name = self.vdb.execute("SELECT v FROM meta WHERE k='model'").fetchone()[0]
        where = "" if scope == "all" else " WHERE women_relevance='specific'"
        self.allowed = {r[0] for r in self.db.execute("SELECT id FROM hadith" + where)}
        self.rec = {r[0]: (r[1], r[2], r[3]) for r in
                    self.db.execute("SELECT id, type, surah_no, ayah_no FROM records")}
        keys, mats = [], []
        for kind in ("hadith", "records"):
            rows = self.vdb.execute("SELECT ref_id, v FROM vec WHERE kind=? ORDER BY ref_id", (kind,)).fetchall()
            if kind == "hadith":
                rows = [r for r in rows if r[0] in self.allowed]
            keys += [(kind, r[0]) for r in rows]
            mats += [np.frombuffer(r[1], dtype=np.float32) for r in rows]
        self.keys = keys
        self.row = {key: j for j, key in enumerate(keys)}
        self.mat = np.vstack(mats)
        self.missing = len(self.allowed) - sum(1 for k, _ in keys if k == "hadith")

    @functools.lru_cache(maxsize=512)
    def qvec(self, query):
        text = norm(query) if self.dense_norm else clean(query)
        m = load_model(self.model_name)
        return m.encode([prefix(self.model_name, "query") + text], normalize_embeddings=True)[0].astype(np.float32)

    def sim(self, key, query):
        j = self.row.get(key)
        return float(self.mat[j] @ self.qvec(query)) if j is not None else 0.0

    def dense(self, query, n=POOL):
        sims = self.mat @ self.qvec(query)
        top = np.argpartition(-sims, min(n, len(sims) - 1))[:n]
        top = top[np.argsort(-sims[top])]
        return [self.keys[j] for j in top], {self.keys[j]: float(sims[j]) for j in top}

    def lexical_hadith(self, query, n=POOL):
        q = terms_query(query)
        if not q:
            return []
        rows = self.db.execute("SELECT rowid FROM hadith_fts WHERE hadith_fts MATCH ? ORDER BY rank LIMIT ?",
                               (q, n * 3)).fetchall()
        return [("hadith", r[0]) for r in rows if r[0] in self.allowed][:n]

    def lexical_records(self, query, n=POOL):
        q = terms_query(query, QURAN_WORDS)
        if not q:
            return []
        return [("records", r[0]) for r in
                self.vdb.execute("SELECT rowid FROM rfts WHERE rfts MATCH ? ORDER BY rank LIMIT ?", (q, n))]

    def passage(self, key):
        kind, i = key
        if kind == "hadith":
            topic, shown = self.db.execute("SELECT topic, matn_display FROM hadith WHERE id=?", (i,)).fetchone()
            return clean(f"{topic or ''}. {shown}")
        return clean(self.db.execute("SELECT text_original FROM records WHERE id=?", (i,)).fetchone()[0])

    def unit(self, key):
        kind, i = key
        if kind == "hadith":
            return f"hadith:{i}"
        _, s, a = self.rec[i]
        return f"ayah:{int(s)}:{int(a)}"

    def search(self, query, k=10, mode="hybrid", rerank=False, rewrites=(), reranker=RERANKER):
        """Ranked hits for query (plus optional formal-Arabic rewrites, fused as extra RRF lists)."""
        assert mode in MODES
        lists, sims, lex = [], {}, set()
        for q in dict.fromkeys([query, *rewrites]):
            if mode in ("fts", "hybrid"):
                for ranked in (self.lexical_hadith(q), self.lexical_records(q)):
                    lists.append(ranked)
                    lex.update(ranked)
            if mode in ("vector", "hybrid"):
                ranked, s = self.dense(q)
                lists.append(ranked)
                for key, v in s.items():
                    sims[key] = max(sims.get(key, -1.0), v)
        order, fused = rrf(lists)
        rr = {}
        if rerank and order:
            pool = order[:RERANK_POOL]
            scores = load_reranker(reranker).predict([(query, self.passage(key)) for key in pool])
            rr = dict(zip(pool, map(float, scores)))
            order = sorted(pool, key=rr.get, reverse=True) + order[RERANK_POOL:]
        hits = []
        for key in order[:k]:
            kind = "hadith" if key[0] == "hadith" else self.rec[key[1]][0]
            sim = sims[key] if key in sims else self.sim(key, query)
            hits.append({"key": key, "kind": kind, "id": key[1], "unit": self.unit(key), "rrf": round(fused[key], 5),
                         "similarity": round(sim, 3), "lex": key in lex,
                         "rerank": round(rr[key], 3) if key in rr else None})
        return hits


def hybrid_search(db_path, vec_path, query, k=5, rewrites=(), rerank=False, scope="all", mode="hybrid"):
    """Same result shape as semantic.semantic_search, so evidence.assess can use either."""
    r = get_retriever(db_path, vec_path, scope)
    hits = r.search(query, k=POOL, mode=mode, rerank=rerank, rewrites=rewrites)
    names = [d[0] for d in r.db.execute("SELECT * FROM records LIMIT 0").description]
    hadith, records, count = [], [], {}
    for h in hits:
        if h["kind"] == "hadith":
            if len(hadith) >= k:
                continue
            row = r.db.execute("SELECT topic, source_ref, matn_display, grade, dorar_grade, dorar_muhaddith, dorar_url "
                               "FROM hadith WHERE id=?", (h["id"],)).fetchone()
            hadith.append({"id": h["id"], "similarity": h["similarity"], "topic": row[0], "source": row[1],
                           "text": row[2], "grade": row[3], "dorar_grade": row[4], "dorar_muhaddith": row[5],
                           "link": row[6], "lex": h["lex"], "rerank": h["rerank"]})
        elif count.get(h["kind"], 0) < k:
            count[h["kind"]] = count.get(h["kind"], 0) + 1
            row = r.db.execute("SELECT * FROM records WHERE id=?", (h["id"],)).fetchone()
            records.append({"id": h["id"], "type": h["kind"], "lex": h["lex"], "similarity": h["similarity"],
                            "rerank": h["rerank"], "fields": dict(zip(names, row))})
    return {"hadith": hadith, "records": records}


@functools.lru_cache(maxsize=4)
def get_retriever(db_path="baseerah.db", vec_path="embeddings.db", scope="all", dense_norm=False):
    return Retriever(db_path, vec_path, scope, dense_norm)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--vec", default="embeddings.db")
    ap.add_argument("--mode", choices=MODES, default="hybrid")
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--scope", choices=["all", "women"], default="all")
    ap.add_argument("-k", type=int, default=10)
    a = ap.parse_args()
    r = get_retriever(a.db, a.vec, a.scope)
    for h in r.search(a.query, a.k, a.mode, a.rerank):
        text = r.passage(h["key"])
        print(f"{h['unit']:14s} {h['kind']:7s} rrf={h['rrf']} sim={h['similarity']} lex={h['lex']} rr={h['rerank']}\n  {text[:160]}")
