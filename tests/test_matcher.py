from data_doctor.fingerprint import fingerprint
from data_doctor.matcher import rank
from data_doctor.seed import load_seed


def test_dbt_ref_error_matches_the_right_seed():
    entries = load_seed()
    err = ("Compilation Error in model orders (models/orders.sql)\n"
           "  depends on a node named 'customers' which was not found")
    matches = rank(fingerprint(err), entries, user_version="", limit=3)
    assert matches, "expected at least one match"
    assert matches[0].entry.id == "dbt-ref-node-not-found"


def test_spark_exception_matches_by_class():
    entries = load_seed()
    err = "pyspark.sql.utils.AnalysisException: cannot resolve column 'amount' given input columns"
    matches = rank(fingerprint(err), entries, limit=3)
    assert matches[0].entry.id == "spark-analysisexception-cannot-resolve-column"
    assert any("exception" in w for w in matches[0].why)


def test_version_outside_range_is_penalized():
    entries = load_seed()
    err = "deprecation: the tests config is renamed to data_tests"
    # min_score 0 so both keep the entry and we can compare raw scores.
    on = rank(fingerprint(err), entries, user_version="1.8.2", limit=1, min_score=0.0)
    off = rank(fingerprint(err), entries, user_version="1.6.0", limit=1, min_score=0.0)
    # Same entry, but the in-range version should score higher than the out-of-range one.
    assert on[0].entry.id == "dbt-18-tests-renamed-data-tests"
    assert on[0].score > off[0].score


def test_new_entries_rank_ahead_of_older_ones():
    entries = load_seed()
    cases = {
        "airbyte-postgres-cdc-lsn-behind":
            "Airbyte sync: Saved offset is before Replication slot's confirmed_flush_lsn, Airbyte will trigger sync from scratch",
        "dbt-contract-mismatch":
            "Compilation Error in model dim_customers: This model has an enforced contract that failed. data_type mismatch_reason assert_columns_equivalent",
        "dbt-dag-cycle":
            "Found a cycle: model.jaffle.orders --> model.jaffle.customers --> model.jaffle.orders",
        "spark-ansi-arithmetic-overflow":
            "org.apache.spark.SparkArithmeticException: [ARITHMETIC_OVERFLOW] integer overflow. Use 'try_add' to tolerate overflow and return NULL instead.",
        "spark-implicit-cartesian":
            "org.apache.spark.sql.AnalysisException: Detected implicit cartesian product for INNER join. Join condition is missing or trivial.",
        "iceberg-commit-state-unknown":
            "org.apache.iceberg.exceptions.CommitStateUnknownException: Cannot determine whether the commit was successful or not. Retrying an already successful operation will result in duplicate records",
        "iceberg-no-such-namespace":
            "org.apache.iceberg.exceptions.NoSuchNamespaceException: Namespace does not exist: prod.analytics",
    }
    for entry_id, err in cases.items():
        matches = rank(fingerprint(err), entries, limit=3)
        assert matches, entry_id
        assert matches[0].entry.id == entry_id, (entry_id, matches[0].entry.id, matches[0].score)


def test_unrelated_error_returns_nothing():
    entries = load_seed()
    matches = rank(fingerprint("the printer is out of toner"), entries)
    assert matches == []
