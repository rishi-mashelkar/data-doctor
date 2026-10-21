"""The bank. A local DuckDB store of known failures and their fixes.

This is the small memory layer at the heart of data-doctor. Entries are versioned by
their updated_at and carry provenance and a confidence that feedback moves over
time. v1 loads candidates into Python and ranks there, which is fast for a bank of
this size. A vector tier can be added later without changing this interface.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Self

import duckdb

from data_doctor.models import Entry

__all__ = ["Bank", "default_home"]

_COLUMNS = [
    "id", "engine", "title", "signature", "symptom", "root_cause", "fix",
    "verification", "version_range", "source", "confidence", "status", "scope",
    "tags", "successes", "failures", "created_at", "updated_at", "last_verified",
]


def default_home() -> Path:
    """Where the bank lives. Override with DATA_DOCTOR_HOME."""
    return Path(os.environ.get("DATA_DOCTOR_HOME", str(Path.home() / ".data-doctor")))


class Bank:
    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / "bank.duckdb"
        self._con = duckdb.connect(str(self.path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id VARCHAR PRIMARY KEY,
                engine VARCHAR, title VARCHAR, signature VARCHAR, symptom VARCHAR,
                root_cause VARCHAR, fix VARCHAR, verification VARCHAR,
                version_range VARCHAR, source VARCHAR, confidence DOUBLE,
                status VARCHAR, scope VARCHAR, tags VARCHAR,
                successes INTEGER, failures INTEGER,
                created_at VARCHAR, updated_at VARCHAR, last_verified VARCHAR
            )
            """
        )

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- writes ---------------------------------------------------------------

    def upsert(self, entry: Entry) -> None:
        row = entry.model_dump()
        row["tags"] = json.dumps(row.get("tags") or [])
        placeholders = ", ".join("?" for _ in _COLUMNS)
        self._con.execute(
            f"INSERT OR REPLACE INTO entries ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
            [row[c] for c in _COLUMNS],
        )

    def upsert_many(self, entries: list[Entry]) -> int:
        for e in entries:
            self.upsert(e)
        return len(entries)

    def record_feedback(self, entry_id: str, worked: bool) -> Entry | None:
        entry = self.get(entry_id)
        if entry is None:
            return None
        entry.record(worked)
        self.upsert(entry)
        return entry

    # -- reads ----------------------------------------------------------------

    def _to_entry(self, row: tuple) -> Entry:
        data = dict(zip(_COLUMNS, row, strict=True))
        data["tags"] = json.loads(data["tags"]) if data["tags"] else []
        return Entry(**data)

    def get(self, entry_id: str) -> Entry | None:
        row = self._con.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM entries WHERE id = ?", [entry_id]
        ).fetchone()
        return self._to_entry(row) if row else None

    def all(self, engine: str | None = None) -> list[Entry]:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM entries"
        params: list = []
        if engine and engine != "other":
            sql += " WHERE engine = ?"
            params.append(engine)
        return [self._to_entry(r) for r in self._con.execute(sql, params).fetchall()]

    def count(self) -> int:
        return self._con.execute("SELECT count(*) FROM entries").fetchone()[0]

    def stats(self) -> dict:
        total = self.count()
        verified = self._con.execute(
            "SELECT count(*) FROM entries WHERE status = 'verified'"
        ).fetchone()[0]
        by_engine = dict(
            self._con.execute(
                "SELECT engine, count(*) FROM entries GROUP BY engine ORDER BY engine"
            ).fetchall()
        )
        s, f = self._con.execute(
            "SELECT coalesce(sum(successes),0), coalesce(sum(failures),0) FROM entries"
        ).fetchone()
        applied = s + f
        accuracy = round(s / applied, 3) if applied else None
        return {
            "total": total, "verified": verified, "by_engine": by_engine,
            "feedback_count": applied, "fix_worked_rate": accuracy,
        }
