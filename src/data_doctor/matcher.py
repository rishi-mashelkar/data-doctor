"""Rank bank entries against a query fingerprint.

Two tiers. First an instant local match on the exception class, the signature
shape, and token overlap. That needs no model and runs offline. A semantic tier
can slot in later behind the same interface, for the fuzzy cases the local tier
misses. v1 ships the local tier only, and it is enough for exact and near matches.
"""

from __future__ import annotations

import operator
import re

from data_doctor.fingerprint import Fingerprint, fingerprint
from data_doctor.models import Entry, Match

__all__ = ["rank"]

_VER = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le,
        "<": operator.lt, "==": operator.eq}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _version_applies(user_version: str, version_range: str) -> bool | None:
    """Best-effort: does the user's version fall in the entry's range?
    Returns True, False, or None when we cannot tell. v1 keeps this light and
    only reads >= and < bounds on major.minor."""
    if not user_version or not version_range:
        return None
    uv = _VER.search(user_version)
    if not uv:
        return None
    user = (int(uv.group(1)), int(uv.group(2)))
    ok = True
    seen = False
    for op, mv in re.findall(r"(>=|<=|>|<|==)\s*(\d+\.\d+(?:\.\d+)?)", version_range):
        m = _VER.search(mv)
        bound = (int(m.group(1)), int(m.group(2)))
        seen = True
        if not _OPS[op](user, bound):
            ok = False
    return ok if seen else None


def _score(query: Fingerprint, entry: Entry, user_version: str) -> Match:
    ef = fingerprint(entry.signature)
    why: list[str] = []
    score = 0.0

    if query.exception and query.exception.lower() in entry.signature.lower():
        score += 0.40
        why.append(f"same exception: {query.exception}")

    # Signature containment is a strong signal both ways.
    if len(ef.signature) > 12 and ef.signature.lower() in query.signature.lower():
        score += 0.30
        why.append("known signature appears in the error")

    overlap = _jaccard(query.tokens, ef.tokens)
    if overlap > 0:
        score += 0.35 * overlap
        shared = sorted(query.tokens & ef.tokens)[:4]
        if shared:
            why.append("shared terms: " + ", ".join(shared))

    if entry.engine != "other" and entry.engine == query.engine_hint:
        score += 0.15
        why.append(f"engine match: {entry.engine}")

    applies = _version_applies(user_version, entry.version_range)
    if applies is True:
        score += 0.15
        why.append(f"version fits {entry.version_range}")
    elif applies is False:
        score -= 0.20
        why.append(f"version {user_version} is outside {entry.version_range}")

    score += 0.10 * entry.confidence
    return Match(entry=entry, score=round(score, 4), why=why)


def rank(query: Fingerprint, entries: list[Entry], *, user_version: str = "",
         limit: int = 5, min_score: float = 0.15) -> list[Match]:
    """Score every entry and return the best ones, most relevant first."""
    scored = [_score(query, e, user_version) for e in entries]
    scored = [m for m in scored if m.score >= min_score]
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:limit]
