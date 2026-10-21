# data-doctor

Diagnose data-pipeline failures against a version-aware knowledge bank, and get the exact fix.

data-doctor reads an error or a log, matches it to a bank of known failures, and shows
the fix with its source, the versions it applies to, and how sure it is. You apply
the fix and tell data-doctor if it worked. The bank gets better with every correction.

It is not another model that guesses at your stack trace. It is a curated,
version-aware bank for data engineering, with an instant local match that runs
offline. v1 covers Airflow, dbt, Spark, and Iceberg.

Status: early. v1 diagnoses and suggests. It never changes your systems.

## Install

```
pip install data-doctor        # not yet published; for now, from source:
pip install -e .
pip install -e ".[ui]"         # also install the web UI
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

## Catch breaks before they happen

`data-doctor check` reads the versions your project pins and warns about known
breaking changes that apply, before an upgrade bites you.

```
data-doctor check .     # reads requirements.txt, pyproject.toml, dbt_project.yml
```

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
   shared terms, engine, and version fit. No model, no network.
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
