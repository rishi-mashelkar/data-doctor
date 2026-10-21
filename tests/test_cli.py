from data_doctor.cli import main


def test_seed_then_diagnose_finds_the_fix(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "seed"]) == 0
    capsys.readouterr()
    err_file = tmp_path / "err.txt"
    err_file.write_text(
        "Compilation Error in model orders depends on a node named 'customers' "
        "which was not found")
    assert main(["--home", str(tmp_path), "diagnose", str(err_file)]) == 0
    out = capsys.readouterr().out
    assert "dbt-ref-node-not-found" in out
    assert "fix:" in out


def test_diagnose_json_shape(tmp_path, capsys):
    main(["--home", str(tmp_path), "seed"])
    capsys.readouterr()
    err_file = tmp_path / "e.txt"
    err_file.write_text("AnalysisException: cannot resolve column 'x' given input columns")
    assert main(["--home", str(tmp_path), "diagnose", str(err_file), "--json"]) == 0
    import json
    doc = json.loads(capsys.readouterr().out)
    assert doc["exception"] == "AnalysisException"
    assert doc["matches"][0]["id"] == "spark-analysisexception-cannot-resolve-column"


def test_feedback_updates_confidence(tmp_path, capsys):
    main(["--home", str(tmp_path), "seed"])
    capsys.readouterr()
    assert main(["--home", str(tmp_path), "feedback", "dbt-profile-not-found", "worked"]) == 0
    assert "confidence" in capsys.readouterr().out


def test_diagnose_empty_bank_warns(tmp_path, capsys):
    err_file = tmp_path / "e.txt"
    err_file.write_text("some error")
    assert main(["--home", str(tmp_path), "diagnose", str(err_file)]) == 1
    assert "empty" in capsys.readouterr().err


def test_add_public_entry_is_redacted(tmp_path, capsys):
    entry = tmp_path / "entry.yaml"
    entry.write_text(
        "id: leaky\nengine: spark\ntitle: t\n"
        "signature: 'failed connecting to postgres://u:p4ss@h/db'\nscope: public\n")
    assert main(["--home", str(tmp_path), "add", str(entry)]) == 0
    capsys.readouterr()
    from data_doctor.store import Bank
    with Bank(home=tmp_path) as bank:
        assert "p4ss" not in bank.get("leaky").signature
