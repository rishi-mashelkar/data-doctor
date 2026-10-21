"""Read a log and pull the distinct failures out of it.

A real log is noise around a few errors. A task log repeats the same stack trace,
interleaves two failures, and buries them in INFO lines. This module splits a log
into error blocks, so each real failure becomes one thing to match against the bank.

It reads a file, a directory of logs, or stdin. It does not reach the network. The
network log sources, like a cloud log service or an orchestrator API, are future
sources behind this same shape. They stay off by default and need a token you bring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from data_doctor.fingerprint import Fingerprint, fingerprint

__all__ = ["LogError", "extract_errors", "read_sources", "split_errors"]

#: File names a directory scan treats as logs.
_LOG_GLOBS = ("*.log", "*.txt", "*.out", "*.err")

# A line that opens a new log record. When one of these appears, the current
# error block has ended. A leading timestamp or a bracketed level is the signal.
_NEW_RECORD = re.compile(
    r"^\s*(?:\[?\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"  # 2026-10-21 03:12:01
    r"|\[(?:INFO|DEBUG|TRACE|WARN|WARNING|NOTICE)\b)",     # [INFO] ...
    re.IGNORECASE,
)

# A level token that marks a line as the start of a failure.
_LEVEL = re.compile(r"(?:^|[\s\[\]])(ERROR|FATAL|CRITICAL|SEVERE)(?:[\s\[\]:]|$)")

# An exception or error class, the strongest single anchor in a stack trace.
# Kept in step with the fingerprint detector on purpose.
_EXCEPTION = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception|Warning|Failure)\b")

_TRACEBACK = "Traceback (most recent call last)"


def _is_anchor(line: str) -> bool:
    """Does this line start a failure worth capturing?"""
    if _TRACEBACK in line:
        return True
    if _EXCEPTION.search(line):
        return True
    return bool(_LEVEL.search(line))


def _is_continuation(line: str) -> bool:
    """Does this line belong to the error block that is open above it?"""
    if not line.strip():
        return False
    return not _NEW_RECORD.match(line)


def split_errors(text: str, *, context_before: int = 0, max_block_lines: int = 60) -> list[str]:
    """Split a raw log into error blocks, one per failure.

    An anchor line opens a block. The block runs through the stack trace that
    follows, up to the next log record, a blank line, or a line cap. The anchor is
    the start by default, so an INFO line above it stays out and two copies of the
    same failure collapse to one. Set context_before to keep lines ahead of it."""
    lines = text.splitlines()
    blocks: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if not _is_anchor(lines[i]):
            i += 1
            continue
        start = max(0, i - context_before)
        j = i + 1
        while j < n and _is_continuation(lines[j]) and (j - i) < max_block_lines:
            j += 1
        block = "\n".join(lines[start:j]).strip()
        if block:
            blocks.append(block)
        # Jump past the block so a nested "Caused by" is not re-anchored.
        i = max(j, i + 1)
    return blocks


@dataclass
class LogError:
    """One distinct failure found in the logs, and how often it appeared."""

    origin: str
    block: str
    fingerprint: Fingerprint
    count: int = 1
    origins: list[str] = field(default_factory=list)


def extract_errors(sources: list[tuple[str, str]]) -> list[LogError]:
    """Pull distinct failures from one or more (origin, text) log sources.

    Identical failures collapse into one LogError with a count, so a stack trace
    repeated fifty times is one thing to fix, not fifty. Order follows first sight."""
    seen: dict[str, LogError] = {}
    order: list[LogError] = []
    for origin, text in sources:
        for block in split_errors(text):
            fp = fingerprint(block)
            key = fp.signature or block
            found = seen.get(key)
            if found is None:
                item = LogError(origin=origin, block=block, fingerprint=fp, origins=[origin])
                seen[key] = item
                order.append(item)
            else:
                found.count += 1
                if origin not in found.origins:
                    found.origins.append(origin)
    return order


def read_sources(path: str | None, *, stdin_text: str | None = None) -> list[tuple[str, str]]:
    """Read a log file, a directory of logs, or stdin into (origin, text) pairs."""
    if path is None or path == "-":
        return [("stdin", stdin_text or "")]
    p = Path(path)
    if p.is_dir():
        files: list[Path] = []
        for pattern in _LOG_GLOBS:
            files.extend(p.rglob(pattern))
        out = []
        for f in sorted(set(files)):
            try:
                out.append((str(f.relative_to(p)), f.read_text(errors="replace")))
            except OSError:
                continue
        return out
    return [(p.name, p.read_text(errors="replace"))]
