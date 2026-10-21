"""The local web UI.

A small FastAPI app over the same bank and matcher the CLI uses. One static page,
no build step, no framework. It serves the page and a few JSON endpoints. FastAPI
and uvicorn are an optional extra, so the core install stays light.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data_doctor.fingerprint import fingerprint
from data_doctor.matcher import rank
from data_doctor.store import Bank

__all__ = ["build_app"]

_STATIC = Path(__file__).parent / "static"


def _match_dict(m: Any) -> dict:
    e = m.entry
    return {
        "id": e.id, "title": e.title, "engine": e.engine, "root_cause": e.root_cause,
        "fix": e.fix, "verification": e.verification, "version_range": e.version_range,
        "source": e.source, "confidence": e.confidence, "status": e.status,
        "why": m.why, "score": m.score,
    }


def build_app(home: Path | None = None):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="data-doctor", docs_url=None, redoc_url=None)
    app.state.home = home

    def bank() -> Bank:
        return Bank(home=app.state.home)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC / "index.html").read_text()

    @app.post("/api/diagnose")
    def diagnose(payload: dict) -> JSONResponse:
        text = (payload.get("text") or "").strip()
        if not text:
            return JSONResponse({"error": "no text"}, status_code=400)
        fp = fingerprint(text)
        engine = (payload.get("engine") or fp.engine_hint) or "other"
        limit = int(payload.get("limit") or 3)
        with bank() as b:
            candidates = b.all(engine=engine if engine != "other" else None) or b.all()
            matches = rank(fp, candidates, user_version=payload.get("version") or "", limit=limit)
        return JSONResponse({
            "engine": engine, "exception": fp.exception,
            "matches": [_match_dict(m) for m in matches],
        })

    @app.get("/api/bank")
    def list_bank(q: str = "", engine: str = "") -> JSONResponse:
        with bank() as b:
            entries = b.all(engine=engine or None)
            if q:
                matches = rank(fingerprint(q), entries, limit=50, min_score=0.05)
                entries = [m.entry for m in matches]
        return JSONResponse({
            "entries": [{"id": e.id, "title": e.title, "engine": e.engine,
                         "fix": e.fix, "status": e.status, "confidence": e.confidence,
                         "version_range": e.version_range, "source": e.source}
                        for e in entries],
        })

    @app.get("/api/stats")
    def stats() -> JSONResponse:
        with bank() as b:
            return JSONResponse(b.stats())

    @app.post("/api/feedback")
    def feedback(payload: dict) -> JSONResponse:
        with bank() as b:
            entry = b.record_feedback(payload.get("id", ""), bool(payload.get("worked")))
        if entry is None:
            return JSONResponse({"error": "no such entry"}, status_code=404)
        return JSONResponse({"id": entry.id, "confidence": entry.confidence,
                             "successes": entry.successes, "failures": entry.failures})

    return app
