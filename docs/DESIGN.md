# data-doctor design (v1)

## What it is

A diagnosis tool for data-pipeline failures. It reads an error, matches it to a
bank of known failures, and returns the fix with provenance. It learns from your
feedback. It covers Airflow, Airbyte, dbt, Spark, Iceberg, and DuckDB.

It is not a model that guesses. The value is the bank and the match, not a
large-model call. The match runs offline.

## The loop

1. Ingest. Read an error from a file or stdin.
2. Fingerprint. Normalize the error. Strip paths, timestamps, ids, and addresses.
   Pull out the exception class and the engine hint. The stable shape is what we
   match on, so the same failure always lands on the same entry.
3. Match. Rank the bank by five signals: the exception class, whether a known
   signature appears in the error, shared terms, the engine, and version fit. This
   is a fast local pass. No network, no model.
4. Suggest. Return the root cause, the exact fix, a verify step, the source, the
   version range, and a confidence.
5. Learn. Feedback moves each entry's confidence and records what is verified.

## Components

- fingerprint. Normalization and the engine and exception detectors.
- store. The bank, a local DuckDB file of entries. Reads, writes, feedback, stats.
- matcher. The ranking described above, plus the optional semantic tier.
- semantic. The optional embeddings tier. Off unless you ask for it.
- models. The Entry and Match shapes.
- redact. Secret and email scrubbing, applied before an entry is shared.
- seed. The bundled starter entries, one YAML file per engine.
- cli. The command line that wires it together.

## The bank is a small memory layer

The store is a minimal memory layer, scoped to one job. Entries are versioned by
their updated time and carry provenance, a confidence, and a last-verified field.
The data model is kept store-agnostic on purpose. Today it is one DuckDB file.
Later the same model can move to a shared, cross-project memory layer without
changing shape. v1 keeps it local and simple.

## Match, honestly

The matcher ranks on exact and lexical signals first. That is enough for exact and
near matches, and it runs offline with no model.

A semantic tier runs behind the same interface, for the fuzzy cases the local pass
misses. It handles the same failure described in different words. It reads meaning
through an embeddings model. It then blends a bounded boost into the lexical score.
It is a second signal, never the first, so a match still needs some real evidence
to surface.

The semantic tier stays optional on purpose. The model is an extra you install,
not a core dependency. The tier is off unless you ask for it. When the extra is
absent, or a model cannot load offline, the tool falls back to the lexical tier
with no error. So the core install stays small and fully offline, and a model is a
fallback, not the default.

## Trust

Every entry states its source, the versions it applies to, and a confidence.
Seed entries ship as reported, not verified. Reported means it came from a source
we have not reproduced inside data-doctor. Feedback and, later, a repro step move an
entry to verified. The tool suggests. It never changes your systems in v1.

## Out of scope for v1

Applying fixes on their own. Running a repro. Scraping the web or forums. JIRA,
Slack, PagerDuty, and reading logs from live systems. All of these are on the
roadmap, off by default when they land.
