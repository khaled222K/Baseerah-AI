"""Pick hadith for synthetic training questions, excluding eval targets and other narrations of them:
any hadith sharing a 4-word sequence with an eval target matn, or whose words overlap it by >= 50%."""
import json, random, sys
from difflib import SequenceMatcher
sys.path.insert(0, ".")
from build_hadith_db import norm
from db import connect_ro

N, SEED, GRAM, OVERLAP = int(sys.argv[1]) if len(sys.argv) > 1 else 300, 13, 4, 0.5
db = connect_ro("baseerah.db")
items = json.load(open("eval_set.json", encoding="utf-8"))["items"]
targets = {int(u.split(":")[1]) for it in items for u in it["expected"] if u.startswith("hadith:")}
grams = lambda t: {tuple(t[i:i + GRAM]) for i in range(len(t) - GRAM + 1)}
banned, target_words = set(), []
for hid in targets:
    w = norm(db.execute("SELECT matn FROM hadith WHERE id=?", (hid,)).fetchone()[0]).split()
    banned |= grams(w)
    target_words.append(w)


def overlaps(w):
    for t in target_words:
        sm = SequenceMatcher(None, w, t, autojunk=False)
        if sm.real_quick_ratio() >= OVERLAP and sum(b.size for b in sm.get_matching_blocks()) / min(len(w), len(t)) >= OVERLAP:
            return True
    return False
pool = []
for hid, matn in db.execute("SELECT id, matn FROM hadith ORDER BY id"):
    w = norm(matn).split()
    if hid in targets or not 12 <= len(w) <= 90 or grams(w) & banned or overlaps(w):
        continue
    pool.append(hid)
random.Random(SEED).shuffle(pool)
json.dump({"seed": SEED, "excluded_targets": len(targets), "pool": len(pool), "ids": sorted(pool[:N])},
          open("training/sample_ids.json", "w"), indent=0)
print(f"eval targets {len(targets)} | eligible {len(pool)} | sampled {min(N, len(pool))}")
