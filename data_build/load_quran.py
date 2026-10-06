"""
load_quran.py

Loads the Quran (King Fahd Complex JSON, Hafs narration) into baseerah.db.

"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
from pathlib import Path

# ---------- Settings ----------
BASE_DIR = Path(__file__).resolve().parent  # Resolve paths relative to this script, not the CWD
JSON_FILE = BASE_DIR / "Quran.json"
DB_FILE = BASE_DIR / "baseerah.db"
EXPECTED_AYAT = 6236
SOURCE_NAME = "quran"

REQUIRED_FIELDS = (
    "sura_no", "sura_name_ar", "aya_no", "page",
    "aya_text_unicode", "aya_text_emlaey",
)

# Tashkeel, Quranic annotation marks, and tatweel
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ALEF_FORMS = re.compile("[إأآٱ]")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("load_quran")


# ---------- Helpers ----------
def normalize(text: str) -> str:
    """Return a search-friendly form: no diacritics, unified letter variants."""
    text = _DIACRITICS.sub("", text)
    text = _ALEF_FORMS.sub("ا", text)
    return text.replace("ى", "ي").replace("ة", "ه")


def load_json(path: Path) -> list[dict]:
    """Read and validate the source file. Raises ValueError on bad input."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        raise ValueError("JSON root must be a non-empty list of ayat.")

    for i, entry in enumerate(data):
        missing = [k for k in REQUIRED_FIELDS if k not in entry]
        if missing:
            raise ValueError(f"Entry #{i} is missing fields: {missing}")
    return data


def create_tables(con: sqlite3.Connection) -> None:
    """Create the shared schema if it does not exist yet."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id            INTEGER PRIMARY KEY,
            source        TEXT NOT NULL,   -- quran / tafsir / hadith / fiqh
            type          TEXT NOT NULL,   -- ayah / hadith / ...
            reference     TEXT NOT NULL,   -- e.g. الفاتحة:1
            surah_no      INTEGER,
            ayah_no       INTEGER,
            page          INTEGER,
            text_original TEXT NOT NULL,   -- exact text: display + quote checking
            text_search   TEXT NOT NULL,   -- normalized text: searching only
            url           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);

        -- FTS5 index over the normalized text (external-content table)
        CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
            text_search, content='records', content_rowid='id'
        );
    """)


def build_rows(data: list[dict]) -> list[tuple]:
    """Map source entries to DB rows."""
    return [
        (
            SOURCE_NAME,
            "ayah",
            f"{d['sura_name_ar'].strip()}:{d['aya_no']}",
            d["sura_no"],
            d["aya_no"],
            d["page"],
            d["aya_text_unicode"],             # keep verbatim (incl. verse marker)
            normalize(d["aya_text_emlaey"]),   # searchable version
            None,
        )
        for d in data
    ]


# ---------- Main ----------
def main() -> int:
    try:
        data = load_json(JSON_FILE)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log.error("Could not read %s: %s", JSON_FILE.name, exc)
        return 1

    rows = build_rows(data)

    con = sqlite3.connect(DB_FILE)
    try:
        with con:  # One transaction: commits on success, rolls back on error
            create_tables(con)
            con.execute("DELETE FROM records WHERE source = ?", (SOURCE_NAME,))
            con.executemany(
                """INSERT INTO records
                   (source, type, reference, surah_no, ayah_no, page,
                    text_original, text_search, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            # Rebuild the full-text index from the records table
            con.execute("INSERT INTO records_fts(records_fts) VALUES ('rebuild')")

        count = con.execute(
            "SELECT COUNT(*) FROM records WHERE source = ?", (SOURCE_NAME,)
        ).fetchone()[0]
    except sqlite3.Error as exc:
        log.error("Database error, nothing was saved: %s", exc)
        return 1
    finally:
        con.close()

    if count != EXPECTED_AYAT:
        log.warning("Loaded %d ayat, expected %d. Check the JSON file.", count, EXPECTED_AYAT)
        return 2

    log.info("Ayat loaded: %d / %d -> OK", count, EXPECTED_AYAT)
    return 0


if __name__ == "__main__":
    sys.exit(main())