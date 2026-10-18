"""Reading and writing the three JSONL files.

Each file holds one JSON object per line. Writes go to a temporary file that is
then renamed over the original, so a crash mid-write never leaves half a file.
"""

import json
import os
import tempfile
from pathlib import Path

FILES = {"exercises": "exercises.jsonl", "sessions": "sessions.jsonl", "sets": "sets.jsonl"}


def data_dir():
    """The data folder: $LIFTLOG_DATA if set (tests use this), else <repo>/data."""
    override = os.environ.get("LIFTLOG_DATA")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data"


def read(name):
    path = data_dir() / FILES[name]
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{FILES[name]} line {n} is not valid JSON: {e}")
    return rows


def write(name, rows):
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / FILES[name]
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(", ", ": ")) + "\n")
    os.replace(tmp, path)


def load_all():
    return {name: read(name) for name in FILES}
