"""Proactive changelog alerts.

Read the versions a project pins, then warn about known breaking changes in the
bank that apply to those versions. This moves data-doctor from reactive to
preventive: you hear about the dbt or Spark change before it breaks your run.

v1 reads the common pin files and matches bank entries tagged "upgrade". It maps
each engine to the package names a project would pin. No engine is imported and
nothing runs. It only reads files.
"""

from __future__ import annotations

import re
from pathlib import Path

from data_doctor.matcher import version_applies
from data_doctor.models import Entry

__all__ = ["Alert", "alerts", "detect_versions"]

# Engine to the distribution names a project pins for it.
_ENGINE_PACKAGES = {
    "airflow": {"apache-airflow", "airflow"},
    "airbyte": {"airbyte"},
    "dbt": {"dbt-core", "dbt", "dbt-snowflake", "dbt-bigquery", "dbt-redshift", "dbt-postgres"},
    "spark": {"pyspark", "spark"},
    "iceberg": {"pyiceberg", "iceberg"},
}

_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:==|>=|~=|>)\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)")


class Alert:
    """One upgrade risk that applies to the detected versions."""

    def __init__(self, package: str, version: str, entry: Entry) -> None:
        self.package = package
        self.version = version
        self.entry = entry


def _scan_requirements(text: str, out: dict[str, str]) -> None:
    for line in text.splitlines():
        m = _REQ_LINE.match(line)
        if m:
            out.setdefault(m.group(1).lower(), m.group(2))


def _scan_pyproject(text: str, out: dict[str, str]) -> None:
    # Light touch: match "name==1.2" or "name>=1.2" style deps inside the file.
    for name, ver in re.findall(
        r'"([A-Za-z0-9_.\-]+)\s*(?:==|>=|~=|>)\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)', text
    ):
        out.setdefault(name.lower(), ver)


def _scan_dbt_project(text: str, out: dict[str, str]) -> None:
    # dbt_project.yml often pins require-dbt-version.
    m = re.search(r"require-dbt-version:\s*[\"']?[>=~ ]*([0-9]+\.[0-9]+(?:\.[0-9]+)?)", text)
    if m:
        out.setdefault("dbt-core", m.group(1))


def detect_versions(project: Path) -> dict[str, str]:
    """Map a pinned package name to its version, read from the usual files."""
    project = Path(project)
    out: dict[str, str] = {}
    scans = [
        ("requirements.txt", _scan_requirements),
        ("requirements-dev.txt", _scan_requirements),
        ("pyproject.toml", _scan_pyproject),
        ("dbt_project.yml", _scan_dbt_project),
    ]
    for name, scan in scans:
        f = project / name
        if f.exists():
            scan(f.read_text(), out)
    return out


def alerts(versions: dict[str, str], entries: list[Entry]) -> list[Alert]:
    """Upgrade-tagged entries whose version range covers a detected version."""
    found: list[Alert] = []
    for entry in entries:
        if "upgrade" not in entry.tags or not entry.version_range:
            continue
        packages = _ENGINE_PACKAGES.get(entry.engine, set())
        for pkg, ver in versions.items():
            if pkg in packages and version_applies(ver, entry.version_range) is True:
                found.append(Alert(pkg, ver, entry))
                break
    return found
