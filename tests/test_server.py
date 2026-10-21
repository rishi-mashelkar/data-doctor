import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from data_doctor.seed import load_seed
from data_doctor.server import build_app
from data_doctor.store import Bank


@pytest.fixture
def client(tmp_path):
    with Bank(home=tmp_path) as bank:
        bank.upsert_many(load_seed())
    return TestClient(build_app(home=tmp_path))


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200 and "data-doctor" in r.text


def test_diagnose_endpoint(client):
    r = client.post("/api/diagnose", json={
        "text": "pyspark.sql.utils.AnalysisException: cannot resolve column 'x'"})
    assert r.status_code == 200
    body = r.json()
    assert body["exception"] == "AnalysisException"
    assert body["matches"][0]["id"] == "spark-analysisexception-cannot-resolve-column"


def test_diagnose_empty_is_400(client):
    assert client.post("/api/diagnose", json={"text": "   "}).status_code == 400


def test_bank_list_and_search(client):
    assert len(client.get("/api/bank").json()["entries"]) >= 22
    hits = client.get("/api/bank", params={"q": "cannot resolve column", "engine": "spark"}).json()
    assert any(e["id"] == "spark-analysisexception-cannot-resolve-column"
               for e in hits["entries"])


def test_feedback_endpoint_updates_confidence(client):
    r = client.post("/api/feedback", json={"id": "dbt-profile-not-found", "worked": True})
    assert r.status_code == 200 and r.json()["successes"] == 1
    assert client.post("/api/feedback", json={"id": "nope", "worked": True}).status_code == 404


def test_stats_endpoint(client):
    s = client.get("/api/stats").json()
    assert s["total"] >= 22 and set(s["by_engine"]) >= {"airflow", "dbt", "spark", "iceberg"}
