import json
import os
from pathlib import Path


def load_seen(path: Path) -> set[str] | None:
    """Return seen video ids, or None when no state file exists yet (first run)."""
    try:
        return set(json.loads(path.read_text()))
    except FileNotFoundError:
        return None


def save_seen(path: Path, ids: set[str]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(ids)))
    os.replace(tmp, path)
