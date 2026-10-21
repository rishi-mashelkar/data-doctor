# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-10-21

### Added
- First cut. The diagnose loop end to end: fingerprint an error, match it against
  a local bank, print the fix with provenance, and record feedback.
- The bank, a local DuckDB store of versioned entries with source, confidence, and
  last-verified. Exact and lexical match, offline, no model.
- Seed entries for Airflow, dbt, Spark, and Iceberg.
- Redaction of secrets and emails before an entry is shared.
- CLI: diagnose, search, add, feedback, seed, stats, version.
