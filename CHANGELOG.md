# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- 79 seed entries for Airbyte, dbt, PySpark, and Iceberg. Ids are new and
  status stays reported. The bank now holds 104.

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
