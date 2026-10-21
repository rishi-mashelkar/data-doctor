from data_doctor.changelog import alerts, detect_versions
from data_doctor.seed import load_seed


def test_detect_versions_from_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "apache-airflow==2.9.1\ndbt-core>=1.8.2\npyspark==3.5.0\nrequests==2.31.0\n")
    v = detect_versions(tmp_path)
    assert v["apache-airflow"] == "2.9.1"
    assert v["dbt-core"] == "1.8.2"
    assert v["pyspark"] == "3.5.0"


def test_detect_versions_from_dbt_project(tmp_path):
    (tmp_path / "dbt_project.yml").write_text(
        "name: shop\nrequire-dbt-version: '>=1.8.0'\n")
    v = detect_versions(tmp_path)
    assert v["dbt-core"] == "1.8.0"


def test_alerts_flags_dbt_18_breaking_change():
    entries = load_seed()
    found = alerts({"dbt-core": "1.8.2"}, entries)
    ids = {a.entry.id for a in found}
    assert "dbt-18-tests-renamed-data-tests" in ids


def test_alerts_quiet_on_old_versions():
    entries = load_seed()
    found = alerts({"dbt-core": "1.6.0", "pyspark": "2.4.0"}, entries)
    assert found == []


def test_alerts_flags_spark_3_timeparser():
    entries = load_seed()
    found = alerts({"pyspark": "3.5.0"}, entries)
    assert "spark-timeparser-upgrade" in {a.entry.id for a in found}
