from data_doctor.logs import extract_errors, read_sources, split_errors

# A log with two distinct failures, INFO noise around them, and the first error
# repeated. A good split finds two failures, not six lines of noise.
SAMPLE = """\
2026-10-21 03:12:01,100 INFO  - starting task extract_orders
2026-10-21 03:12:02,200 INFO  - reading from warehouse
2026-10-21 03:12:05,500 ERROR - task failed
Traceback (most recent call last):
  File "/opt/airflow/dags/orders.py", line 42, in run
    df.select("amount")
pyspark.sql.utils.AnalysisException: cannot resolve column 'amount' given input columns
2026-10-21 03:12:06,000 INFO  - cleaning up
2026-10-21 03:12:07,000 INFO  - starting task extract_orders retry
2026-10-21 03:12:09,900 ERROR - task failed
Traceback (most recent call last):
  File "/opt/airflow/dags/orders.py", line 42, in run
    df.select("amount")
pyspark.sql.utils.AnalysisException: cannot resolve column 'amount' given input columns
2026-10-21 03:14:10,880 ERROR - compile step failed
dbt.exceptions.CompilationError: depends on a node named 'customers' which was not found
2026-10-21 03:14:11,000 INFO  - done
"""


def test_split_finds_the_error_blocks_not_the_info_lines():
    blocks = split_errors(SAMPLE)
    # Three ERROR anchors (two identical AnalysisException, one CompilationError).
    assert len(blocks) == 3
    assert all("INFO  - starting" not in b for b in blocks)
    assert any("AnalysisException" in b for b in blocks)
    assert any("CompilationError" in b for b in blocks)


def test_a_block_keeps_its_traceback():
    blocks = split_errors(SAMPLE)
    analysis = next(b for b in blocks if "AnalysisException" in b)
    assert "Traceback (most recent call last)" in analysis
    assert "orders.py" in analysis
    # The block stops at the next log record, it does not swallow the INFO line.
    assert "cleaning up" not in analysis


def test_extract_collapses_repeats_into_one_with_a_count():
    errors = extract_errors([("task.log", SAMPLE)])
    # Two distinct failures, the AnalysisException counted twice.
    assert len(errors) == 2
    analysis = next(e for e in errors if e.fingerprint.exception == "AnalysisException")
    assert analysis.count == 2


def test_read_sources_from_a_directory(tmp_path):
    (tmp_path / "a.log").write_text("SomeError: boom one")
    (tmp_path / "b.txt").write_text("OtherError: boom two")
    (tmp_path / "ignore.md").write_text("not a log")
    sources = read_sources(str(tmp_path))
    names = {name for name, _ in sources}
    assert names == {"a.log", "b.txt"}


def test_read_sources_from_stdin():
    sources = read_sources("-", stdin_text="RuntimeError: nope")
    assert sources == [("stdin", "RuntimeError: nope")]


def test_a_block_with_no_timestamps_still_splits():
    pasted = (
        "Traceback (most recent call last):\n"
        '  File "job.py", line 10, in <module>\n'
        "ValueError: bad input\n"
    )
    blocks = split_errors(pasted)
    assert len(blocks) == 1
    assert "ValueError" in blocks[0]
