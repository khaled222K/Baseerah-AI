import sqlite3
from pathlib import Path


def connect_ro(path, **kw):
    """Open a SQLite file read-only (mode=ro). Runtime code must use this, never sqlite3.connect."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"قاعدة البيانات غير موجودة: {p}")
    kw.setdefault("check_same_thread", False)
    return sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True, **kw)
