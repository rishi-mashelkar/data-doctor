# data-doctor

Diagnose data-pipeline failures against a version-aware knowledge bank, and get the exact fix.

data-doctor reads an error or a log, matches it to a bank of known failures, and
shows the fix with its source, the versions it applies to, and how sure it is. You
apply the fix and tell data-doctor whether it worked. The bank gets better with
every correction.

It is not another model that guesses at your stack trace. It is a curated,
version-aware bank for data engineering, with an instant local match that runs
offline. It covers Airflow, Airbyte, dbt, Spark, Iceberg, and DuckDB.

It diagnoses and suggests. It never changes your systems. A fix can carry a
reproduction that data-doctor runs in a sandbox to mark it verified.

## Contents

- [Install](#install)
- [Tutorial: your first diagnosis](#tutorial-your-first-diagnosis)
- [How-to guides](#how-to-guides)
- [How it works](#how-it-works)
- [Commands](#commands)
- [Roadmap](#roadmap)

## Install

```
pip install data-doctor        # not yet published; for now, from source:
pip install -e .
pip install -e ".[ui]"         # add the web UI
pip install -e ".[semantic]"   # add the semantic match tier
```

The core install is small and offline. The extras are optional.

## Tutorial: your first diagnosis

This walkthrough takes about two minutes. It uses the bundled bank, so it needs no
setup beyond the install.

### 1. Load the bank

```
$ data-doctor seed
Loaded 152 seed entries. Bank now holds 152.
```

The bank is a local DuckDB file in ~/.data-doctor. It ships with 152 known
failures across six engines.

### 2. Diagnose an error

Pipe an error in, or point data-doctor at a file. Here is a dbt error:

```
$ echo "Compilation Error in model orders: depends on a node named 'customers' which was not found" \
    | data-doctor diagnose --engine dbt

Diagnosis  (engine: dbt, exception: n/a)

  [dbt-ref-node-not-found]  Compilation Error - depends on a node that was not found
    engine: dbt
    cause:  A ref points at a model name that does not exist. Usual causes are a
            typo, a renamed or deleted model, or a model in a package not installed.
    fix:    Check the ref name against the model file name, not the file path. If
            the model was renamed, update every ref. If it lives in a package, run
            dbt deps. Then dbt compile to confirm the graph resolves.
    verify: dbt compile succeeds and dbt ls shows the referenced model.
    source: https://docs.getdbt.com/reference/dbt-jinja-functions/ref
    trust:  reported, confidence 0.72
    why:    shared terms: compilation, depends, found, named; engine match: dbt
    score:  0.432

  ... two more suggestions follow, ranked lower.
```

Each suggestion shows the root cause, the exact fix, a verify step, the source, and
how sure the bank is. The top match here is the ref error, with its fix.

### 3. Say whether it worked

```
$ data-doctor feedback dbt-ref-node-not-found worked
Recorded. dbt-ref-node-not-found is now confidence 0.813 (1 worked, 0 failed).
```

Confidence rose from 0.72 to 0.813. A worked result raises it, a failed result
lowers it. The bank learns from you.

### 4. Watch the bank improve

```
$ data-doctor stats
Bank: 152 entries, 0 verified.
By engine: airbyte 32, airflow 6, dbt 38, duckdb 3, iceberg 35, spark 38
Feedback: 1 recorded, fix-worked rate 1.0.
```

### 5. Triage a whole log

A real log repeats the same failure and buries it in noise. Triage splits a log
into distinct failures and matches each one.

```
$ data-doctor triage task.log
Scanned the logs. Found 2 distinct failure(s): 2 known, 0 not yet in the bank.

● spark failure (seen once in task.log):
    | pyspark.sql.utils.AnalysisException: cannot resolve column 'amount' ...

  [spark-analysisexception-cannot-resolve-column]  AnalysisException - cannot resolve column
    fix:    Compare the name to the printed input columns. For a post-join
            ambiguity, qualify it with the DataFrame alias ...
    ...
```

That is the loop: diagnose, apply, record, repeat. The rest of this README is
reference.

## How-to guides

### Diagnose from a file, stdin, or a pipe

```
data-doctor diagnose err.txt                                   # a file
dbt run 2> err.txt && data-doctor diagnose err.txt             # capture, then read
spark-submit job.py 2>&1 | data-doctor diagnose --engine spark --version 3.5.0
```

data-doctor guesses the engine from the error. Override it with `--engine`. Pass
`--version` so a version-specific fix ranks higher. Add `--json` for a machine
readable result.

### Catch a break before an upgrade

`data-doctor check` reads the versions your project pins and warns about known
breaking changes that apply, before an upgrade bites you.

```
data-doctor check .     # reads requirements.txt, pyproject.toml, dbt_project.yml
```

It exits 2 when a risk applies, so it fits a pre-upgrade step in CI.

### Verify a fix against a repro

An entry can carry a reproduction. `data-doctor verify` runs it and, if the error
reproduces and the fix runs clean, marks the entry verified.

```
data-doctor verify --all                      # run every repro, mark the passes
data-doctor verify duckdb-catalog-table-missing
```

The default verifier runs SQL in a sandboxed in-memory DuckDB, with file and
network access turned off, so it is safe to run on any entry. A second verifier
runs a tool like dbt or spark-submit against your project. It is off unless you
pass `--allow-commands`, and it only runs an allowlisted tool.

The command verifier can reproduce then fix, like the SQL one. It runs a failing
command first. That must fail. Then it runs the fixed command, which must pass. A
worked example lives in [examples/](examples/), and it runs against a bundled dbt
project:

```
$ data-doctor add examples/entries/dbt-ref-demo.yaml
$ data-doctor verify dbt-ref-node-not-found-demo --allow-commands --project examples/dbt_demo
  ✓ dbt-ref-node-not-found-demo: reproduced the error; the fix runs clean
Verified 1, failed 0, skipped 0.
```

### Match by meaning

The local match is fast and offline, but it misses a failure described in different
words than the bank entry. The semantic tier reads meaning, not words, so a close
match still surfaces. It is a second signal that blends into the local score. It
never replaces it.

```
pip install -e ".[semantic]"
data-doctor diagnose err.txt --semantic
data-doctor search "jobs keep dying out of memory" --semantic
```

The model is an optional extra, so the core install stays light. The first run
downloads a small model once, then runs offline. When the extra is absent, or a
model cannot load offline, data-doctor falls back to the local tier with no error.
A model is a fallback here, not the default.

### Use the web UI

```
pip install -e ".[ui]"
data-doctor serve       # opens on http://127.0.0.1:8322
```

Paste an error, get the ranked fixes, browse and search the bank, and record
whether a fix worked. The UI runs locally against the same bank as the CLI.

### Add your own fix

Each entry is one known failure and its fix, written as YAML. Add it to your bank:

```
data-doctor add my-fix.yaml
```

Entries are private by default. When you mark one public, data-doctor redacts
secrets and emails from the error first.

## How it works

1. Fingerprint. The error is normalized. Paths, timestamps, and ids are stripped.
   The stable shape is what gets matched.
2. Match. A fast local pass ranks the bank by exception class, signature shape,
   shared terms, engine, and version fit. No model, no network. An optional
   semantic tier adds a signal based on meaning, for the fuzzy cases this pass
   misses.
3. Suggest. You get the root cause, the exact fix, a verify step, the source, the
   version range, and a confidence.
4. Learn. Your feedback moves each entry's confidence, and a passed repro marks it
   verified.

Each entry carries provenance: its source, the versions it applies to, a
confidence, and when it was last verified. No blind "try this". See
[docs/DESIGN.md](docs/DESIGN.md) for the full design.

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

Run any command with `-h` for its options.

## Roadmap

The north star: a data engineer never debugs the same failure twice.

**Shipped.**
- Diagnose an error against a local, offline, version-aware bank, with provenance
  and a fix-worked rate that climbs as you give feedback.
- Log triage. Scan a file, a directory, or a piped stream and find every known
  failure in it.
- Verified fixes. Reproduce an error in a sandboxed DuckDB, or run an allowlisted
  tool against your project, and confirm the fix before it is trusted.
- Proactive changelog alerts. Read your pinned versions and warn before an upgrade
  breaks you.
- A semantic match tier for the fuzzy cases the local pass misses.
- A local web UI.

**Next, the connectors (Phase 3).** Each is off by default, needs a token you
bring, and keeps writes suggest-first.
- Read logs from the common sources, a cloud log service or an orchestrator API.
- Change context from JIRA and chat, so a break ties to the ticket or deploy that
  caused it.
- Sit in the incident path. Take an alert from a pager and respond in a channel.

**Later (Phase 4).** With your approval and a dry run, apply the fix. Then prevent:
warn ahead of the change that would have broken you.

The full plan is in [docs/ROADMAP.md](docs/ROADMAP.md).

## License

Apache 2.0.
