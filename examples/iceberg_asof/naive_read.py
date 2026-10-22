#!/usr/bin/env python3
"""Reproduce the failure: the standard path cannot reach the 09:30 state.

A reader loads the table's newest metadata and tries to time travel to the
as-of time. Maintenance expired that snapshot, so no snapshot at or before the
as-of time still exists. This mirrors what real tools report: Spark fails with
"Cannot find a snapshot older than ...", and DuckDB iceberg_scan returns 0 rows.

Exit 1 when the as-of read cannot be reached, which is the failure we diagnose.
Standard library only, so the failure reproduces with no extra install.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.environ.get("DDOC_TABLE", os.path.join(_HERE, "warehouse", "orders"))
AS_OF = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)


def newest_metadata():
    """The table's current metadata, which a normal reader would open."""
    files = glob.glob(os.path.join(TABLE, "metadata", "*.metadata.json"))
    metas = [json.load(open(f)) for f in files]
    return max(metas, key=lambda m: m["last-updated-ms"])


def main():
    ms = int(AS_OF.timestamp() * 1000)
    meta = newest_metadata()
    live = {s["snapshot-id"] for s in meta.get("snapshots", [])}
    # Time travel resolves against the snapshot log, and the snapshot must still
    # exist. Expiry removed the ones at or before the as-of time.
    reachable = [e for e in meta.get("snapshot-log", [])
                 if e["timestamp-ms"] <= ms and e["snapshot-id"] in live]
    stamp = AS_OF.strftime("%Y-%m-%dT%H:%M:%S")
    if not reachable:
        print(f"Cannot find a snapshot older than {stamp}Z", file=sys.stderr)
        print("DuckDB iceberg_scan returns 0 rows for the as-of query", file=sys.stderr)
        return 1
    print(f"reached snapshot {reachable[-1]['snapshot-id']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
