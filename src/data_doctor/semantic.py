"""The optional semantic match tier.

The lexical matcher is fast and offline, but it misses a failure described in
different words than the bank entry. An error that says "job keeps dying, out of
memory" shares few words with an entry titled "executor OOM, container killed",
yet they are the same failure. This tier reads meaning, not words, so the close
match still surfaces.

It is a second signal, never the first. The lexical tier runs first and always.
The semantic score only blends into the lexical score and can lift a good match
the word overlap missed.

The embeddings model is an optional extra. Install it with
`pip install data-doctor[semantic]`. When the extra is absent, or a model cannot
load offline, data-doctor falls back to the lexical tier with no error. The core
install stays light and fully offline, and a model is a fallback, not the default.
"""

from __future__ import annotations

import math
from functools import lru_cache

__all__ = ["Embedder", "available", "load_embedder"]

#: The default model. Small, CPU only, and good enough for short error text.
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def available() -> bool:
    """Is the embeddings extra installed?"""
    try:
        import fastembed  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _unit(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class Embedder:
    """Embed short texts into unit vectors and compare them by cosine.

    The model loads on first use, not on construction, so importing this costs
    nothing. Each text is embedded once per process and cached, so the same bank
    entry is not re-embedded across many diagnoses. The web UI reuses the cache."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._cache: dict[str, list[float]] = {}

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return a unit vector per text. Cached texts cost nothing."""
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            model = self._load()
            for text, vec in zip(missing, model.embed(missing), strict=True):
                self._cache[text] = _unit([float(x) for x in vec])
        return [self._cache[t] for t in texts]

    def similarity(self, query: str, texts: list[str]) -> list[float]:
        """Cosine of the query against each text, in the same order."""
        if not texts:
            return []
        q = self.embed([query])[0]
        return [_dot(q, v) for v in self.embed(texts)]


@lru_cache(maxsize=4)
def load_embedder(model_name: str = _DEFAULT_MODEL) -> Embedder | None:
    """Return a ready embedder, or None when one cannot be loaded.

    This never raises. A missing extra, a missing model, or no network on the
    first download all return None, and the caller stays on the lexical tier. The
    model loads here, once, so a failure shows up at load time, not mid-diagnose.
    The result is cached per process, so a failure is not retried on every call."""
    if not available():
        return None
    embedder = Embedder(model_name)
    try:
        embedder.embed(["warm up"])
    except Exception:  # noqa: BLE001 — any load failure means fall back to lexical
        return None
    return embedder
