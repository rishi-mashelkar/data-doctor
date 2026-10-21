from data_doctor.models import Entry
from data_doctor.seed import load_seed
from data_doctor.store import Bank


def test_upsert_get_and_all(tmp_path):
    with Bank(home=tmp_path) as bank:
        bank.upsert(Entry(id="x1", engine="dbt", title="t", signature="sig"))
        assert bank.count() == 1
        got = bank.get("x1")
        assert got and got.engine == "dbt"
        assert bank.all(engine="dbt")[0].id == "x1"
        assert bank.all(engine="spark") == []


def test_feedback_moves_confidence_and_marks_verified(tmp_path):
    with Bank(home=tmp_path) as bank:
        bank.upsert(Entry(id="x1", title="t", signature="sig", confidence=0.5))
        e = bank.record_feedback("x1", worked=True)
        assert e.successes == 1 and e.last_verified
        assert e.confidence == round(2 / 3, 3)
        bank.record_feedback("x1", worked=False)
        again = bank.get("x1")
        assert again.successes == 1 and again.failures == 1


def test_seed_loads_and_stats(tmp_path):
    with Bank(home=tmp_path) as bank:
        n = bank.upsert_many(load_seed())
        assert n >= 16
        s = bank.stats()
        assert s["total"] == n
        assert set(s["by_engine"]) >= {"airflow", "dbt", "spark", "iceberg"}
        assert s["fix_worked_rate"] is None  # no feedback yet


def test_bank_persists_across_connections(tmp_path):
    with Bank(home=tmp_path) as bank:
        bank.upsert(Entry(id="keep", title="t", signature="s"))
    with Bank(home=tmp_path) as bank2:
        assert bank2.get("keep") is not None
