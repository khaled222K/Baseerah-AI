"""
load_tafsir.py

Loads Tafsir Al-Muyassar (King Fahd Complex CSV) into baseerah.db.

"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sqlite3
import sys
from html.parser import HTMLParser
from pathlib import Path

# ---------- Settings ----------
BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "Tafsir.csv"
DB_FILE = BASE_DIR / "baseerah.db"
EXPECTED_ROWS = 6236
SOURCE_NAME = "tafsir"

REQUIRED_COLUMNS = ("sura_no", "sura_name_ar", "aya_no", "page", "aya_tafseer")

_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ALEF_FORMS = re.compile("[إأآٱ]")
_WHITESPACE = re.compile(r"\s+")
_LEADING_MARKER = re.compile(r"^\[\d+\]\s*")  # e.g. "[1] " at the start

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("load_tafsir")


# ---------- Text cleaning ----------
class _TafsirCleaner(HTMLParser):
    """Collects text while skipping everything inside <span class='aya'>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._skip_depth:
            if tag == "span":
                self._skip_depth += 1  # nested span inside the ayah block
        elif tag == "span" and "aya" in (dict(attrs).get("class") or "").split():
            self._skip_depth = 1

    def handle_endtag(self, tag):
        if tag == "span" and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def clean_tafsir(raw: str) -> str:
    """Convert the HTML tafsir field to clean plain text."""
    parser = _TafsirCleaner()
    parser.feed(raw)
    parser.close()
    text = _WHITESPACE.sub(" ", parser.text()).strip()
    return _LEADING_MARKER.sub("", text).strip()


def normalize(text: str) -> str:
    """Search-friendly form: no diacritics, unified letter variants."""
    text = _DIACRITICS.sub("", text)
    text = _ALEF_FORMS.sub("ا", text)
    return text.replace("ى", "ي").replace("ة", "ه")


# ---------- Input ----------
def read_rows(path: Path) -> list[tuple]:
    """Read and validate the CSV. Raises ValueError on malformed input."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        rows = []
        for line_no, entry in enumerate(reader, start=2):
            try:
                surah, ayah, page = (
                    int(entry["sura_no"]), int(entry["aya_no"]), int(entry["page"])
                )
            except ValueError as exc:
                raise ValueError(f"Line {line_no}: invalid number ({exc})") from exc

            text = clean_tafsir(entry["aya_tafseer"])
            if not text:
                raise ValueError(f"Line {line_no}: tafsir is empty after cleaning")

            rows.append((
                SOURCE_NAME,
                "tafsir",
                f"{entry['sura_name_ar'].strip()}:{ayah}",  # same format as Quran refs
                surah, ayah, page,
                text,                 # verbatim cleaned text (used for quote checking)
                normalize(text),      # searchable form
                None,
            ))
    return rows


# ---------- Output ----------
def save(rows: list[tuple]) -> int:
    """Replace the tafsir rows in one transaction. Returns the stored count."""
    con = sqlite3.connect(DB_FILE)
    try:
        with con:  # commit on success, rollback on error
            con.execute("DELETE FROM records WHERE source = ?", (SOURCE_NAME,))
            con.executemany(
                """INSERT INTO records
                   (source, type, reference, surah_no, ayah_no, page,
                    text_original, text_search, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            con.execute("INSERT INTO records_fts(records_fts) VALUES ('rebuild')")

        # Integrity check: every tafsir row should match a Quran ayah
        orphans = con.execute(
            """SELECT COUNT(*) FROM records t
               WHERE t.source = ? AND NOT EXISTS (
                   SELECT 1 FROM records q
                   WHERE q.source = 'quran'
                     AND q.surah_no = t.surah_no AND q.ayah_no = t.ayah_no)""",
            (SOURCE_NAME,),
        ).fetchone()[0]
        if orphans:
            log.warning("%d tafsir rows have no matching Quran ayah.", orphans)

        return con.execute(
            "SELECT COUNT(*) FROM records WHERE source = ?", (SOURCE_NAME,)
        ).fetchone()[0]
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Tafsir Al-Muyassar into baseerah.db")
    parser.add_argument("--preview", type=int, metavar="N",
                        help="print N cleaned rows and exit without writing")
    args = parser.parse_args()

    try:
        rows = read_rows(CSV_FILE)
    except (OSError, csv.Error, ValueError) as exc:
        log.error("Could not read %s: %s", CSV_FILE.name, exc)
        return 1

    if args.preview:
        for row in rows[: args.preview]:
            print(f"[{row[2]}] {row[6][:300]}\n")
        return 0

    try:
        count = save(rows)
    except sqlite3.Error as exc:
        log.error("Database error, nothing was saved: %s", exc)
        return 1

    if count != EXPECTED_ROWS:
        log.warning("Loaded %d rows, expected %d.", count, EXPECTED_ROWS)
        return 2

    log.info("Tafsir loaded: %d / %d -> OK", count, EXPECTED_ROWS)
    return 0


if __name__ == "__main__":
    sys.exit(main())