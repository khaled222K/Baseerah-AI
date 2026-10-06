import re

# Tashkeel, Quranic annotation marks and tatweel: the set data_build/load_quran.py strips when it
# builds text_search, plus Arabic Extended-A marks (U+08D3-U+08FF, e.g. open tanween) that the
# Uthmani text in records.text_original uses. norm() turns any mark it doesn't know into a space,
# which splits words, so answer.flat() removes these first to compare quotes with source text.
MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ࣓-ࣿـ]")


def note_of(db, hadith_id):
    """Explanatory note for a hadith from hadith_notes, or None when it has none."""
    r = db.execute("SELECT note, source, url FROM hadith_notes WHERE hadith_id=?", (hadith_id,)).fetchone()
    if not r:
        return None
    return {"text": r[0], "source": r[1], "url": r[2] or None}
