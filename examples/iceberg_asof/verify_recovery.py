#!/usr/bin/env python3
"""Run the recovery and check it against the golden answer.

Drives reconstruct.py, the golden solver, with the example's own paths, then
compares its output to expected.csv as a multiset of rows. Exit 0 on an exact
match, 1 otherwise. This is the fix step of the reproduce-then-fix repro.

Needs the reader extra: pip install "data-doctor[iceberg-demo]" (pyarrow and
fastavro). No Spark, no JVM, no cloud, no catalog.
"""
import csv
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import reconstruct  # noqa: E402  the golden solver, kept verbatim

_OUT = os.path.join(_HERE, "output", "orders_asof.csv")
reconstruct.TABLE = os.path.join(_HERE, "warehouse", "orders")
reconstruct.OUT = _OUT


def read_csv(path):
    with open(path, newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def main():
    reconstruct.main()
    got_header, got_rows = read_csv(_OUT)
    exp_header, exp_rows = read_csv(os.path.join(_HERE, "expected.csv"))
    if got_header != exp_header:
        print(f"header mismatch: {got_header} vs {exp_header}", file=sys.stderr)
        return 1
    if Counter(map(tuple, got_rows)) != Counter(map(tuple, exp_rows)):
        print(f"row mismatch: recovered {len(got_rows)}, expected {len(exp_rows)}",
              file=sys.stderr)
        return 1
    print(f"recovered {len(got_rows)} rows, exact match to the golden answer",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
