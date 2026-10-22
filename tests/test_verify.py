import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from data_doctor.cli import main
from data_doctor.seed import load_seed
from data_doctor.verify import run_repro

_EXAMPLES = Path(__file__).parent.parent / "examples"


def _example_entry(name: str) -> dict:
    rows = yaml.safe_load((_EXAMPLES / "entries" / name).read_text())
    return rows[0]


def test_duckdb_repro_passes_when_error_reproduces_and_fix_runs():
    r = run_repro({
        "verifier": "duckdb_sql",
        "setup": ["CREATE TABLE t (id INTEGER, amount DOUBLE)"],
        "failing": "SELECT amt FROM t",
        "expect_error": "not found",
        "fixed": "SELECT amount FROM t",
    })
    assert r.status == "passed"


def test_duckdb_repro_fails_if_failing_sql_does_not_raise():
    r = run_repro({
        "verifier": "duckdb_sql",
        "setup": ["CREATE TABLE t (id INTEGER)"],
        "failing": "SELECT id FROM t",  # this does NOT raise
        "fixed": "SELECT id FROM t",
    })
    assert r.status == "failed" and "did not raise" in r.detail


def test_duckdb_sandbox_blocks_filesystem():
    # External access is off, so reading a file must raise. That raise IS the
    # reproduction, so the repro "passes" — proving the sandbox denied the read.
    r = run_repro({
        "verifier": "duckdb_sql",
        "failing": "SELECT * FROM read_csv_auto('/etc/hosts')",
    })
    assert r.status == "passed"


def test_command_verifier_off_by_default():
    r = run_repro({"verifier": "command", "tool": "python3", "args": ["-c", "pass"]})
    assert r.status == "skipped" and "allow-commands" in r.detail


def test_command_verifier_runs_allowlisted_tool_when_opted_in():
    r = run_repro(
        {"verifier": "command", "tool": "python3", "args": ["-c", "import sys; sys.exit(0)"]},
        allow_commands=True)
    assert r.status == "passed"


def test_command_verifier_skips_unknown_tool():
    r = run_repro({"verifier": "command", "tool": "definitely-not-a-real-tool"},
                  allow_commands=True)
    assert r.status == "skipped"


def test_command_reproduce_then_fix_passes():
    r = run_repro({
        "verifier": "command", "tool": "python3",
        "failing": ["-c", "import sys; sys.exit(2)"],  # must fail
        "args": ["-c", "import sys; sys.exit(0)"],      # fix runs clean
    }, allow_commands=True)
    assert r.status == "passed" and "reproduced" in r.detail


def test_command_reproduce_then_fix_needs_the_failing_to_fail():
    r = run_repro({
        "verifier": "command", "tool": "python3",
        "failing": ["-c", "import sys; sys.exit(0)"],  # does NOT fail
        "args": ["-c", "import sys; sys.exit(0)"],
    }, allow_commands=True)
    assert r.status == "failed" and "did not fail" in r.detail


def test_dbt_example_repro_reproduces_and_fixes():
    if shutil.which("dbt") is None:
        pytest.skip("dbt is not on PATH")
    repro = _example_entry("dbt-ref-demo.yaml")["repro"]
    r = run_repro(repro, project=_EXAMPLES / "dbt_demo", allow_commands=True)
    assert r.status == "passed", r.detail


def test_spark_example_repro_skips_without_spark():
    if shutil.which("spark-submit") is not None:
        pytest.skip("spark-submit is on PATH; the skip path is not exercised")
    repro = _example_entry("spark-job-demo.yaml")["repro"]
    r = run_repro(repro, project=_EXAMPLES / "spark_demo", allow_commands=True)
    assert r.status == "skipped" and "spark-submit" in r.detail


def test_iceberg_example_repro_reproduces_and_fixes():
    # The recovery reads the table with pyarrow and fastavro. The repro shells out
    # to python3 on PATH, so skip unless that interpreter has both readers.
    probe = subprocess.run(["python3", "-c", "import pyarrow, fastavro"],
                           check=False, capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("python3 on PATH lacks pyarrow and fastavro")
    repro = _example_entry("iceberg-asof-demo.yaml")["repro"]
    r = run_repro(repro, project=_EXAMPLES / "iceberg_asof", allow_commands=True)
    assert r.status == "passed", r.detail


def test_seed_duckdb_entries_all_verify():
    for entry in load_seed():
        if entry.engine == "duckdb" and entry.repro:
            assert run_repro(entry.repro).status == "passed", entry.id


def test_cli_verify_marks_entry_verified(tmp_path, capsys):
    main(["--home", str(tmp_path), "seed"])
    capsys.readouterr()
    assert main(["--home", str(tmp_path), "verify", "duckdb-binder-column-not-found"]) == 0
    assert "✓" in capsys.readouterr().out
    from data_doctor.store import Bank
    with Bank(home=tmp_path) as bank:
        e = bank.get("duckdb-binder-column-not-found")
        assert e.status == "verified" and e.last_verified and e.confidence >= 0.8


def test_cli_verify_all(tmp_path, capsys):
    main(["--home", str(tmp_path), "seed"])
    capsys.readouterr()
    rc = main(["--home", str(tmp_path), "verify", "--all"])
    out = capsys.readouterr().out
    assert rc == 0 and "Verified 3" in out  # the three duckdb entries pass
