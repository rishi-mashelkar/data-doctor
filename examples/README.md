# Examples

Worked examples of the command verifier. A command repro runs an allowlisted tool,
like dbt or spark-submit, against a project to confirm a fix. It is off by default.
You turn it on with --allow-commands, and the tool must be installed.

## dbt

A minimal dbt project with the DuckDB adapter. One model refs another, and a var
toggles the ref between fixed and broken. The repro parses it broken first, which
must fail, then fixed, which must pass.

```
pip install dbt-duckdb
data-doctor add examples/entries/dbt-ref-demo.yaml
data-doctor verify dbt-ref-node-not-found-demo --allow-commands --project examples/dbt_demo
```

## Spark

A tiny Spark job that selects a column and exits clean. It needs a working Spark
install. Without one, data-doctor skips the repro rather than failing it.

```
data-doctor add examples/entries/spark-job-demo.yaml
data-doctor verify spark-job-runs-demo --allow-commands --project examples/spark_demo
```
