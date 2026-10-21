# data-doctor

Diagnose data-pipeline failures against a version-aware knowledge bank, and get the exact fix.

data-doctor reads an error or a log, matches it to a bank of known failures, and shows
the fix with its source, the versions it applies to, and how sure it is. You apply
the fix and tell data-doctor if it worked. The bank gets better with every correction.

It is not another model that guesses at your stack trace. It is a curated,
version-aware bank for data engineering, with an instant local match that runs
offline. It covers Airflow, Airbyte, dbt, Spark, Iceberg, and DuckDB.

Status: early. It diagnoses and suggests. It never changes your systems. A fix can
carry a reproduction that data-doctor runs in a sandbox to mark it verified.

## Install

```
pip install data-doctor        # not yet published; for now, from source:
pip install -e .
pip install -e ".[ui]"         # also install the web UI
pip install -e ".[semantic]"   # also install the semantic match tier
```

## Quickstart

```
data-doctor seed                        # load the starter bank
dbt run 2> err.txt                 # capture a failure
data-doctor diagnose err.txt            # get the fix
data-doctor feedback dbt-ref-node-not-found worked
data-doctor stats                       # watch the fix-worked rate
```

You can also pipe an error straight in:

```
spark-submit job.py 2>&1 | data-doctor diagnose --engine spark --version 3.5.0
```

## Triage a whole log

A real log buries a few failures in noise and repeats the same stack trace many
times. `data-doctor triage` reads a log file, a directory of logs, or a piped
stream, splits it into distinct failures, and matches each to the bank. Repeats
collapse into one failure with a count. Failures the bank does not know are listed
so you can add them.

```
data-doctor triage path/to/task.log
data-doctor triage ./logs/                 # scan a directory of logs
kubectl logs mypod | data-doctor triage    # pipe a stream straight in
```

Secrets in a shown snippet are redacted first, because logs hold tokens and
connection strings. This is the first step of reading logs directly. Reading from
cloud log services and orchestrators comes later, off by default and with a token
you bring.

## Catch breaks before they happen

`data-doctor check` reads the versions your project pins and warns about known
breaking changes that apply, before an upgrade bites you.

```
data-doctor check .     # reads requirements.txt, pyproject.toml, dbt_project.yml
```

## Verified fixes

An entry can carry a reproduction. `data-doctor verify` runs it and, if the error
reproduces and the fix runs clean, marks the entry verified.

```
data-doctor verify --all           # run every repro, mark the ones that pass
data-doctor verify duckdb-catalog-table-missing
```

The default verifier runs SQL in a sandboxed in-memory DuckDB, with file and
network access turned off. A second verifier can run a tool like dbt or
spark-submit against your project, but only with `--allow-commands`, and only for
an allowlisted tool. The tool runs nothing on its own.

## Match by meaning

The local match is fast and offline, but it misses a failure described in
different words than the bank entry. The semantic tier reads meaning, not words, so
a close match still surfaces. It is a second signal that blends into the local
score. It never replaces it.

```
pip install -e ".[semantic]"
data-doctor diagnose err.txt --semantic
data-doctor search "jobs keep dying out of memory" --semantic
```

The model is an optional extra, so the core install stays light. The first run
downloads a small model once, then runs offline. When the extra is not installed,
or a model cannot load offline, data-doctor falls back to the local tier with no
error. A model is a fallback here, not the default.

## Web UI

```
pip install -e ".[ui]"
data-doctor serve       # opens on http://127.0.0.1:8322
```

Paste an error, get the ranked fixes, browse and search the bank, and record
whether a fix worked. The UI runs locally against the same bank as the CLI.

## How it works

1. Fingerprint. The error is normalized. Paths, timestamps, and ids are stripped
   so the stable shape is what gets matched.
2. Match. A fast local pass ranks the bank by exception class, signature shape,
   shared terms, engine, and version fit. No model, no network. An optional
   semantic tier adds a meaning-based signal for the fuzzy cases this pass misses.
3. Suggest. You get the root cause, the exact fix, a verify step, the source, the
   version range, and a confidence.
4. Learn. Your feedback moves each entry's confidence and marks what is verified.

## The bank

Each entry is one known failure and its fix, with provenance: source, version
range, confidence, and when it was last verified. Entries are private by default.
When you mark one public, data-doctor redacts secrets and emails from the error first.

Add your own:

```
data-doctor add my-fix.yaml
```

## Commands

| Command | What it does |
| --- | --- |
| diagnose | Match an error (file or stdin) and print the fix |
| triage | Scan a log file or directory and find every known failure in it |
| verify | Run an entry's reproduction and mark it verified if it passes |
| check | Warn about known upgrade risks for a project's pinned versions |
| serve | Run the local web UI |
| search | Match free text against the bank |
| add | Add entries from a YAML file |
| feedback | Record whether a suggested fix worked |
| seed | Load the bundled starter entries |
| stats | Show bank size and the fix-worked rate |

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md). Short version: verified fixes that run
against a tiny local repro, proactive changelog alerts, then connectors for JIRA,
Slack, PagerDuty, and log sources. North star: a data engineer never debugs the
same failure twice.

## Design

See [docs/DESIGN.md](docs/DESIGN.md).

## License

Apache 2.0.
