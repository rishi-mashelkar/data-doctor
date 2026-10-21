"""Load the bundled seed entries that ship with data-doctor.

The seed is a starting bank so the tool is useful on day one, not empty. Entries
are marked status "reported" and scope "public". They come from docs and field
experience, not from a reproduction inside data-doctor yet. Feedback and the verify
step move them to "verified" over time.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from data_doctor.models import Entry

__all__ = ["load_seed", "seed_dir"]


def seed_dir() -> Path:
    return Path(__file__).parent / "seed"


def load_seed() -> list[Entry]:
    entries: list[Entry] = []
    for path in sorted(seed_dir().glob("*.yaml")):
        rows = yaml.safe_load(path.read_text()) or []
        for row in rows:
            entries.append(Entry(**row))
    return entries
