from answer import flat, quotes_ok
from build_hadith_db import norm
from db import connect_ro
from verify import MARKS, note_of


def ayah(db, s, a):
    return db.execute("SELECT text_original, text_search FROM records WHERE source='quran' "
                      "AND surah_no=? AND ayah_no=?", (s, a)).fetchone()


def test_note_of_shape():
    db = connect_ro("baseerah.db")
    n = note_of(db, 301)
    assert n["text"] and n["source"] == "الدرر السنية، شرح الحديث"
    assert note_of(db, 1) is None


def test_marks_keep_words_whole():
    db = connect_ro("baseerah.db")
    orig, search = ayah(db, 1, 2)
    assert flat(orig) == "الحمد لله رب العلمين"
    rows = db.execute("SELECT text_original, text_search FROM records WHERE source='quran'").fetchall()
    same = sum(len(flat(o).split()) == len(norm(s).split()) for o, s in rows)
    assert same >= 6170, same  # remaining ayat differ in Uthmani vs imlaei spelling, not in marks


def test_quotes_ok_uses_marks():
    db = connect_ro("baseerah.db")
    orig, _ = ayah(db, 1, 2)
    texts = [{"text": orig}]
    assert quotes_ok(f"قال تعالى ﴿{orig}﴾", texts)
    assert quotes_ok("«رب العلمين»", texts)
    assert not quotes_ok("«رب السماوات والأرض»", texts)
    assert MARKS.sub("", "ـ") == ""
