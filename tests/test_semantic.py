"""Tests for the semantic match tier.

The blending logic is tested with a fake embedder, so it runs offline and fast
and does not download a model. One test exercises the real fastembed path, but it
skips cleanly when the extra is not installed or a model cannot load offline.
"""

from __future__ import annotations

import pytest

from data_doctor.fingerprint import fingerprint
from data_doctor.matcher import _semantic_boost, rank
from data_doctor.models import Entry


class FakeEmbedder:
    """Return a fixed cosine per entry text, keyed by a marker in the text. Lets
    the blending tests control similarity without a model."""

    def __init__(self, by_marker: dict[str, float]) -> None:
        self.by_marker = by_marker
        self.calls = 0

    def similarity(self, query: str, texts: list[str]) -> list[float]:
        self.calls += 1
        out = []
        for t in texts:
            score = 0.0
            for marker, value in self.by_marker.items():
                if marker in t:
                    score = value
            out.append(score)
        return out


def _entry(entry_id: str, title: str) -> Entry:
    return Entry(id=entry_id, engine="spark", title=title, signature=title)


def test_boost_is_zero_at_or_below_floor():
    assert _semantic_boost(0.60) == 0.0
    assert _semantic_boost(0.40) == 0.0


def test_boost_grows_with_cosine_and_caps():
    low = _semantic_boost(0.66)
    high = _semantic_boost(0.75)
    assert 0 < low < high
    # At and beyond the top anchor the boost is capped at the full weight.
    assert _semantic_boost(0.78) == pytest.approx(_semantic_boost(0.95))


def test_semantic_rescues_a_match_with_no_word_overlap():
    # The query shares no words with the entry, so the lexical tier scores zero.
    entries = [_entry("spark-oom", "MARK executor ran out of heap and was killed")]
    query = fingerprint("the workers keep dying because they run low on memory")
    lexical = rank(query, entries, min_score=0.0)
    assert lexical[0].score == pytest.approx(0.05)  # confidence term only

    emb = FakeEmbedder({"MARK": 0.74})
    rescued = rank(query, entries, embedder=emb)
    assert rescued, "a strong semantic match should surface"
    assert rescued[0].entry.id == "spark-oom"
    assert any("semantically close" in w for w in rescued[0].why)


def test_semantic_reorders_toward_the_closer_meaning():
    entries = [
        _entry("weak", "FARAWAY something unrelated to the error at hand"),
        _entry("strong", "CLOSE the real cause described in other words"),
    ]
    query = fingerprint("an error with no shared words at all here")
    emb = FakeEmbedder({"FARAWAY": 0.61, "CLOSE": 0.77})
    matches = rank(query, entries, embedder=emb, min_score=0.0)
    assert matches[0].entry.id == "strong"


def test_a_failing_embedder_falls_back_to_lexical():
    class Boom:
        def similarity(self, query, texts):
            raise RuntimeError("model exploded")

    entries = [_entry("spark-oom", "executor out of memory OutOfMemoryError")]
    query = fingerprint("executor OutOfMemoryError out of memory")
    # The lexical tier still matches, and no exception escapes.
    matches = rank(query, entries, embedder=Boom())
    assert matches and matches[0].entry.id == "spark-oom"


def test_no_embedder_means_no_semantic_why_line():
    entries = [_entry("spark-oom", "executor OutOfMemoryError out of memory")]
    matches = rank(fingerprint("executor OutOfMemoryError"), entries)
    assert matches
    assert not any("semantically" in w for w in matches[0].why)


def test_real_embedder_ranks_a_fuzzy_match_first():
    pytest.importorskip("fastembed")
    from data_doctor.semantic import load_embedder

    embedder = load_embedder()
    if embedder is None:
        pytest.skip("embeddings model not available offline")

    from data_doctor.seed import load_seed

    entries = load_seed()
    err = "the job keeps dying, workers run out of memory and the container is killed"
    matches = rank(fingerprint(err), entries, embedder=embedder, limit=3)
    assert matches
    assert matches[0].entry.id == "spark-executor-oom"
    assert any("semantically close" in w for w in matches[0].why)
