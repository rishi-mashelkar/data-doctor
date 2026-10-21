# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.5.0] - 2026-10-21

### Added
- Log triage. `data-doctor triage` scans a log file, a directory of logs, or a
  piped stream, splits it into distinct failures, and matches each to the bank.
  A stack trace repeated fifty times collapses to one failure with a count.
  Failures not yet in the bank are listed so you can add them. This is the first
  step of reading logs directly. Secrets in a shown snippet are redacted first.
- 48 seed entries for Airbyte, dbt, PySpark, and Iceberg. Ids are new and
  status stays reported. The bank now holds 152.

## [0.4.0] - 2026-10-21

### Added
- A semantic match tier. It reads the meaning of an error, not just its words, so
  a close match surfaces even when the error is described in different words than
  the bank entry. It is a second signal that blends into the lexical score, and it
  is off unless you ask for it with `--semantic` (or a checkbox in the web UI). The
  embeddings model is an optional extra (`pip install data-doctor[semantic]`). When
  the extra is absent, or a model cannot load offline, data-doctor falls back to the
  lexical tier with no error. The core install stays light and fully offline.
- Airbyte as an engine, plus more dbt, Spark, and Iceberg failures. New ids stay
  reported. The bank now holds 104 across six engines.

## [0.3.0] - 2026-10-21

### Added
- Verified fixes. An entry can carry a reproduction that `data-doctor verify`
  runs. If the error reproduces and the fix runs clean, the entry is marked
  verified, with a confidence floor and a date. The default verifier runs SQL in a
  sandboxed in-memory DuckDB with file and network access off. A command verifier
  can run an allowlisted tool (dbt, spark-submit, …) against a project, but only
  with `--allow-commands`.
- A DuckDB engine with three real, reproducible entries, all verified in the
  sandbox. The bank now holds 25 across five engines.

## [0.2.0] - 2026-10-21

### Added
- Proactive changelog alerts. `data-doctor check` reads the versions a project
  pins in requirements.txt, pyproject.toml, or dbt_project.yml, and warns about
  known breaking changes in the bank that apply to those versions. Exits 2 when a
  risk applies, so it fits a pre-upgrade CI step.
- A local web UI. `data-doctor serve` opens a one-page app to diagnose an error,
  browse and search the bank, and record feedback. FastAPI and uvicorn are an
  optional extra (`pip install data-doctor[ui]`), so the core install stays light.
- Six more seed entries, including upgrade-tagged ones for Airflow, dbt, and Spark
  that power the changelog alerts. The bank now holds 22.

## [0.1.0] - 2026-10-21

### Added
- First cut. The diagnose loop end to end: fingerprint an error, match it against
  a local bank, print the fix with provenance, and record feedback.
- The bank, a local DuckDB store of versioned entries with source, confidence, and
  last-verified. Exact and lexical match, offline, no model.
- Seed entries for Airflow, dbt, Spark, and Iceberg.
- Redaction of secrets and emails before an entry is shared.
- CLI: diagnose, search, add, feedback, seed, stats, version.
