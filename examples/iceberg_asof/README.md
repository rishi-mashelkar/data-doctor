# Recover a lost Iceberg snapshot

A table read fine at 09:30. Then routine maintenance ran, and now the same read
fails. Nobody can tell Finance which rows the morning close saw.

This example reproduces that failure. It shows data-doctor diagnosing it. Then it
runs the recovery and checks the result against a reference answer we trust.

It needs no Spark, no JVM, and no cloud catalog. It runs on a local copy of the
table. Run the commands below from the repo root.

## Why it is hard

Scheduled maintenance expired the snapshot behind the 09:30 state. expire_snapshots
deleted it and its manifest list. A reader can no longer reach that state. Spark
cannot find anything older than the target time. DuckDB iceberg_scan returns 0 rows.

The fix is to rebuild the lost state by hand from what survived. That path has many
traps. One commit crashed and never landed, but its file is still there. A manifest
rewrite merged entries from before and after the target time. Some files came from
an old Hive table and carry no field ids. The v2 delete rules key on the data
sequence number, not the file sequence number.

Get one rule wrong and the row count is plausible but wrong. This is why frontier
models miss it. They return a clean number that is not the answer.

The answer is 1375 rows. They come from snapshot 1418591960033102530, read against
schema 3.

## Run it

First install the reader extra. It adds pyarrow and fastavro. The recovery needs no
other tools.

```
pip install "data-doctor[iceberg-demo]"
```

### 1. Reproduce the failure

A normal reader loads the newest metadata and tries to time travel to 09:30. The
snapshot is gone, so the read fails.

```
$ python3 examples/iceberg_asof/naive_read.py
Cannot find a snapshot older than 2026-03-14T09:30:00Z
DuckDB iceberg_scan returns 0 rows for the as-of query
$ echo $?
1
```

### 2. Diagnose it

Load the bank, add this example's entry, then pipe the error into data-doctor.

```
$ data-doctor seed
Loaded 152 seed entries. Bank now holds 152.
$ data-doctor add examples/entries/iceberg-asof-demo.yaml
Added 1 entry.
$ python3 examples/iceberg_asof/naive_read.py 2>&1 | data-doctor diagnose --engine iceberg

Diagnosis  (engine: iceberg, exception: n/a)

  [iceberg-asof-expired-snapshot]  Time travel fails after expire_snapshots removed the target snapshot
    engine: iceberg  ·  applies to: Apache Iceberg v2, checked against Java Iceberg 1.9.2
    cause:  Scheduled maintenance expired the snapshot you are reading ...
    fix:    Rebuild the state by hand from what survived. First find the committed
            metadata chain ... Apply the v2 delete rules exactly ... Project to the
            schema that was current at your target time, not the newest one.
    source: https://iceberg.apache.org/spec/#scan-planning
    trust:  reported, confidence 0.8
    score:  0.405

  ... two more suggestions follow, ranked lower.
```

The top match is this failure, with the full recovery recipe in its fix. The
general snapshot-expired entry ranks below it.

### 3. Verify the fix

data-doctor runs the repro. It reproduces the failure, runs the recovery, and
checks the result against the reference answer.

```
$ data-doctor verify iceberg-asof-expired-snapshot --allow-commands --project examples/iceberg_asof
  ✓ iceberg-asof-expired-snapshot: reproduced the error; the fix runs clean
Verified 1, failed 0, skipped 0.
```

Under the hood, the repro runs two scripts. naive_read.py must fail first. Then
verify_recovery.py runs the recovery and compares every row to expected.csv. A pass
means the error was real and the fix resolves it.

## What is in here

| Path | What it is |
| --- | --- |
| warehouse/orders | The table on local disk, with its metadata and data files |
| incident.md | The on-call note: the timeline and what Finance needs |
| naive_read.py | Reproduces the failure, the standard path cannot reach 09:30 |
| reconstruct.py | The reference solver, reads the files and rebuilds the lost state |
| verify_recovery.py | Runs the recovery and checks it against expected.csv |
| expected.csv | The reference answer, 1375 rows |

The entry for this failure lives in
[../entries/iceberg-asof-demo.yaml](../entries/iceberg-asof-demo.yaml).

## What data-doctor does here

data-doctor does not solve the table for you. It matches the error to the fix, and
hands you the exact recipe with its source. The bundled scripts then prove that
recipe on real files, so you can trust the recipe before you run it on your own
table.
