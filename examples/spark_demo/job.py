"""A tiny Spark job for the command-repro example.

It builds a two-row DataFrame, selects a column that exists, and exits 0. Point a
command repro at it with spark-submit to confirm a Spark environment runs a job
end to end. It needs a working Spark install, so it is not run in CI.
"""

from __future__ import annotations

import sys


def main() -> int:
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("data-doctor-demo").getOrCreate()
    try:
        df = spark.createDataFrame([(1, 100), (2, 200)], ["order_id", "amount"])
        count = df.select("amount").count()
        print(f"selected amount for {count} rows")
        return 0 if count == 2 else 1
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
