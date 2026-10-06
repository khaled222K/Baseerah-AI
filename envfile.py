"""Load KEY=VALUE lines from a local .env file into os.environ (existing variables win).

.env is git-ignored: it is where your API key lives on your machine. Never commit it."""
import os
from pathlib import Path


def load(path=None):
    p = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


load()
