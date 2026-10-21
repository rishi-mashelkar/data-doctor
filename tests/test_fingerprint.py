from data_doctor.fingerprint import detect_engine, fingerprint


def test_scrubs_volatile_parts():
    raw = "Traceback at /opt/airflow/dags/my_dag.py line 42 at 2026-01-02T03:04:05Z id 0xdeadbeef"
    fp = fingerprint(raw)
    assert "/opt/airflow" not in fp.signature
    assert "2026-01-02" not in fp.signature
    assert "0xdeadbeef" not in fp.signature
    assert "<path>" in fp.signature and "<ts>" in fp.signature


def test_extracts_exception_class():
    fp = fingerprint("pyspark.sql.utils.AnalysisException: cannot resolve column 'x'")
    assert fp.exception == "AnalysisException"


def test_detects_engine():
    assert detect_engine("dbt Compilation Error in model orders ref()") == "dbt"
    assert detect_engine("org.apache.spark.SparkException executor lost") == "spark"
    assert detect_engine("NoSuchTableException iceberg catalog") == "iceberg"
    assert detect_engine("Broken DAG scheduler dagbag import") == "airflow"
    assert detect_engine("some unrelated text") == "other"
