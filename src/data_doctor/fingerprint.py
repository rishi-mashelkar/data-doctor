"""Turn a raw error or log into a stable fingerprint.

Errors are noisy. The same failure prints a different path, timestamp, or id
every time. We strip the volatile parts so the stable shape is what we match on.
This is what makes the match fast and the bank free of near-duplicates.
"""

from __future__ import annotations

import re

__all__ = ["Fingerprint", "detect_engine", "fingerprint"]

# Order matters. Replace the most specific patterns first.
_SCRUB = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE), "<uuid>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"(?:/[\w.\-]+)+/?"), "<path>"),
    (re.compile(r"[A-Za-z]:\\[\\\w.\-]+"), "<path>"),
    (re.compile(r"\bline\s+\d+\b", re.IGNORECASE), "line <n>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b\d{4,}\b"), "<num>"),
]

# An exception or error class is the strongest single token in most stack traces.
_EXCEPTION = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Error|Exception|Warning|Failure))\b")

_ENGINE_HINTS = {
    "airflow": ("airflow", "dag ", "dagbag", "scheduler", "executor", "task_instance", "mwaa"),
    "dbt": ("dbt", "compilation error", "profiles.yml", "dbt_project", "ref(", "source(", "macro"),
    "spark": ("spark", "pyspark", "py4j", "executor lost", "analysisexception", "sparkcontext"),
    "iceberg": ("iceberg", "snapshot", "nosuchtable", "manifest", "metadata.json", "catalog"),
}


class Fingerprint:
    """The stable shape of an error, plus the tokens and hints used to match it."""

    def __init__(self, raw: str, signature: str, tokens: set[str],
                 exception: str, engine_hint: str) -> None:
        self.raw = raw
        self.signature = signature
        self.tokens = tokens
        self.exception = exception
        self.engine_hint = engine_hint


def _normalize(text: str) -> str:
    out = text
    for pattern, repl in _SCRUB:
        out = pattern.sub(repl, out)
    return re.sub(r"\s+", " ", out).strip()


def _tokens(signature: str) -> set[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_.]{2,}", signature.lower())
    return {w for w in words if w not in _STOP}


_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "was", "has", "not",
    "error", "exception", "traceback", "caused", "most", "recent", "call", "last",
    "<path>", "<num>", "<ts>", "<uuid>", "<addr>", "<ip>", "line",
}


def detect_engine(text: str) -> str:
    low = text.lower()
    best, score = "other", 0
    for engine, hints in _ENGINE_HINTS.items():
        hits = sum(1 for h in hints if h in low)
        if hits > score:
            best, score = engine, hits
    return best


def fingerprint(text: str) -> Fingerprint:
    """Build a Fingerprint from a raw error or log snippet."""
    signature = _normalize(text)
    exc_match = _EXCEPTION.search(text)
    exception = exc_match.group(1) if exc_match else ""
    return Fingerprint(
        raw=text,
        signature=signature,
        tokens=_tokens(signature),
        exception=exception,
        engine_hint=detect_engine(text),
    )
