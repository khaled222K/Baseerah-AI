"""Fine-tune multilingual-e5-small on (synthetic question, hadith) pairs with MultipleNegativesRankingLoss.

RAG does not train any model; this optional script is the only training in the project.
Inputs: training/synthetic_questions.jsonl (questions written for a sample of hadith chosen by
training/sample.py, which excludes every eval_set.json target and other narrations of it).
Model selection uses a dev split of the synthetic pairs only; eval_set.json is never read here."""
import argparse, json, random, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import connect_ro
from semantic import clean, MODEL


def passages(db_path, ids):
    db = connect_ro(db_path)
    out = {}
    for hid in ids:
        topic, shown = db.execute("SELECT topic, matn_display FROM hadith WHERE id=?", (hid,)).fetchone()
        out[hid] = "passage: " + clean(f"{topic or ''}. {shown}")
    return out


def dev_recall(model, dev, docs):
    """Recall@1 of dev questions against the passages of all sampled hadith (a small, cheap proxy)."""
    ids = list(docs)
    D = model.encode([docs[i] for i in ids], normalize_embeddings=True, batch_size=32)
    Q = model.encode(["query: " + clean(q) for q, _ in dev], normalize_embeddings=True, batch_size=32)
    top = np.argmax(Q @ D.T, axis=1)
    return float(np.mean([ids[t] == hid for t, (_, hid) in zip(top, dev)]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="training/synthetic_questions.jsonl")
    ap.add_argument("--db", default="baseerah.db")
    ap.add_argument("--out", default="models/e5-small-baseerah")
    ap.add_argument("--max-epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()

    from sentence_transformers import SentenceTransformer, InputExample, losses
    from torch.utils.data import DataLoader
    import torch
    random.seed(a.seed)
    torch.manual_seed(a.seed)

    pairs = [json.loads(l) for l in open(a.pairs, encoding="utf-8")]
    hids = sorted({p["hadith_id"] for p in pairs})
    random.shuffle(hids)
    dev_ids = set(hids[: len(hids) // 5])
    docs = passages(a.db, hids)
    train = [(p["question"], p["hadith_id"]) for p in pairs if p["hadith_id"] not in dev_ids]
    dev = [(p["question"], p["hadith_id"]) for p in pairs if p["hadith_id"] in dev_ids]
    print(f"train pairs {len(train)} | dev pairs {len(dev)} (dev hadith held out entirely)")

    model = SentenceTransformer(MODEL)
    model.max_seq_length = 384
    best = dev_recall(model, dev, docs)
    print(f"epoch 0 (base) dev R@1 = {best:.3f}")
    examples = [InputExample(texts=["query: " + clean(q), docs[h]]) for q, h in train]
    loader = DataLoader(examples, shuffle=True, batch_size=a.batch, drop_last=True)
    loss = losses.MultipleNegativesRankingLoss(model)
    log = [{"epoch": 0, "dev_r1": best}]
    best_epoch = 0
    for ep in range(1, a.max_epochs + 1):
        model.fit(train_objectives=[(loader, loss)], epochs=1, warmup_steps=int(0.1 * len(loader)) if ep == 1 else 0,
                  optimizer_params={"lr": a.lr}, show_progress_bar=False)
        r = dev_recall(model, dev, docs)
        log.append({"epoch": ep, "dev_r1": r})
        print(f"epoch {ep} dev R@1 = {r:.3f}")
        if r > best:
            best, best_epoch = r, ep
            model.save(a.out)
    json.dump({"best_epoch": best_epoch, "log": log, "train_pairs": len(train), "dev_pairs": len(dev),
               "lr": a.lr, "batch": a.batch, "seed": a.seed},
              open("training/finetune_log.json", "w"), indent=1)
    print("saved" if best_epoch else "no epoch beat the base model on dev; nothing saved", a.out)
