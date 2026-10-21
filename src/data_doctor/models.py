"""Data models for the knowledge bank and for a diagnosis result.

An Entry is one known failure and its fix. It carries provenance (source,
version, confidence, last verified) so a reader can judge how far to trust it.
The model is deliberately store-agnostic. Today it lives in a local DuckDB bank.
Later it can move to a shared memory layer without changing shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

__all__ = ["ENGINES", "Entry", "Match", "now_iso"]

#: The engines data-doctor knows in v1. "other" is the catch-all.
ENGINES = ("airflow", "dbt", "spark", "iceberg", "duckdb", "other")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Entry(BaseModel):
    """One known failure and its fix."""

    id: str
    engine: str = "other"
    title: str
    #: The canonical, normalized error signature we match against.
    signature: str
    symptom: str = ""
    root_cause: str = ""
    fix: str = ""
    #: How to confirm the fix worked. A command or a check, not prose.
    verification: str = ""
    #: Freeform version constraint this entry applies to, e.g. "dbt>=1.8".
    version_range: str = ""
    source: str = ""
    confidence: float = 0.5
    #: "verified" means we reproduced it and confirmed the fix. "reported" means
    #: it came from a source we have not re-checked.
    status: str = "reported"
    scope: str = "private"
    tags: list[str] = Field(default_factory=list)
    successes: int = 0
    failures: int = 0
    #: Optional reproduction spec a verifier can run to confirm the fix. One of the
    #: built-in verifiers (e.g. duckdb_sql, command). None means not reproducible yet.
    repro: dict | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    last_verified: str = ""

    def record(self, worked: bool) -> None:
        """Fold one feedback result into the entry and re-derive confidence."""
        if worked:
            self.successes += 1
        else:
            self.failures += 1
        total = self.successes + self.failures
        # Laplace-smoothed success rate, so one data point does not swing to 0 or 1.
        self.confidence = round((self.successes + 1) / (total + 2), 3)
        self.updated_at = now_iso()
        if worked:
            self.last_verified = self.updated_at


class Match(BaseModel):
    """One ranked candidate for a diagnosis, with the reasons it surfaced."""

    entry: Entry
    score: float
    why: list[str] = Field(default_factory=list)
