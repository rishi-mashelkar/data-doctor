"""Scrub secrets and personal data out of an error before it is shared.

An error log is a common place to leak a token, a connection string, or an email.
Before an entry is marked shareable, run it through here. Private entries you keep
to yourself are left untouched. Only sharing triggers redaction.
"""

from __future__ import annotations

import re

__all__ = ["redact"]

_RULES = [
    # Credentials in a connection string: scheme://user:pass@host
    (re.compile(r"(\w+://[^:\s/]+:)[^@\s]+(@)"), r"\1<redacted>\2"),
    # AWS access key id.
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted-aws-key>"),
    # Bearer / authorization tokens.
    (re.compile(r"(?i)\b(bearer|token|authorization)\s+[A-Za-z0-9._\-]{12,}"), r"\1 <redacted>"),
    # key=value secrets.
    (re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?key|token)"
                r"(\s*[:=]\s*)\S+"), r"\1\2<redacted>"),
    # Email addresses.
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<redacted-email>"),
    # Long hex blobs that look like keys.
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "<redacted-hex>"),
]


def redact(text: str) -> tuple[str, int]:
    """Return the scrubbed text and the number of replacements made."""
    out = text
    count = 0
    for pattern, repl in _RULES:
        out, n = pattern.subn(repl, out)
        count += n
    return out, count
