"""Rank bank entries against a query fingerprint.

Two tiers. First an instant local match on the exception class, the signature
shape, and token overlap. That needs no model and runs offline, and it is enough
for exact and near matches. Second, an optional semantic tier for the fuzzy cases
the local tier misses, when the same failure is described in different words. The
semantic score only blends into the local score through the same interface. It is
a second signal, never the first, and it is off unless an embedder is passed.
"""

from __future__ import annotations

import operator
import re

from data_doctor.fingerprint import Fingerprint, fingerprint
from data_doctor.models import Entry, Match

__all__ = ["rank", "version_applies"]

_VER = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")
_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le,
        "<": operator.lt, "==": operator.eq}

# How the semantic tier blends in. Cosine from the embedder runs low and narrow
# for short error text, so these map a useful band onto a real contribution. A
# cosine at or below the floor adds nothing. One at the top adds W_SEM, which is
# on a par with the exception-class signal, so a confident semantic match can
# surface an entry the word overlap missed.
_SEM_FLOOR = 0.60
_SEM_TOP = 0.78
_W_SEM = 0.45


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def version_applies(user_version: str, version_range: str) -> bool | None:
    """Best-effort: does the user's version fall in the entry's range?
    Returns True, False, or None when we cannot tell. v1 keeps this light and
    only reads >= and < bounds on major.minor. Public so the changelog check can
    reuse the same version logic the matcher uses."""
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


def _entry_text(entry: Entry) -> str:
    """The text the semantic tier reads for an entry. Title and symptom carry the
    plain-language meaning the model matches against, not just the raw signature."""
    parts = [entry.title, entry.symptom, entry.signature, entry.root_cause]
    return "  ".join(p for p in parts if p)[:1000]


def _semantic_boost(cos: float) -> float:
    if cos <= _SEM_FLOOR:
        return 0.0
    frac = min((cos - _SEM_FLOOR) / (_SEM_TOP - _SEM_FLOOR), 1.0)
    return _W_SEM * frac


def _score(query: Fingerprint, entry: Entry, user_version: str,
           sem_cos: float | None = None) -> Match:
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

    applies = version_applies(user_version, entry.version_range)
    if applies is True:
        score += 0.15
        why.append(f"version fits {entry.version_range}")
    elif applies is False:
        score -= 0.20
        why.append(f"version {user_version} is outside {entry.version_range}")

    score += 0.10 * entry.confidence

    if sem_cos is not None:
        boost = _semantic_boost(sem_cos)
        if boost > 0:
            score += boost
            why.append(f"semantically close ({sem_cos:.2f})")

    return Match(entry=entry, score=round(score, 4), why=why)


def rank(query: Fingerprint, entries: list[Entry], *, user_version: str = "",
         limit: int = 5, min_score: float = 0.15, embedder=None) -> list[Match]:
    """Score every entry and return the best ones, most relevant first.

    Pass an embedder to turn on the semantic tier. It reads meaning, not words, so
    a close match surfaces even when few words are shared. A failure in the
    embedder never breaks a diagnose. It falls back to the lexical score."""
    sims: list[float] | None = None
    if embedder is not None and entries:
        try:
            sims = embedder.similarity(query.raw or query.signature,
                                       [_entry_text(e) for e in entries])
        except Exception:  # noqa: BLE001 — a model hiccup must not break diagnose
            sims = None
    scored = [_score(query, e, user_version, sims[i] if sims is not None else None)
              for i, e in enumerate(entries)]
    scored = [m for m in scored if m.score >= min_score]
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:limit]
