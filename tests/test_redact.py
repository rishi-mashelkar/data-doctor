from data_doctor.redact import redact


def test_redacts_connection_string_password():
    out, n = redact("postgres://user:s3cr3t@db.host:5432/mydb")
    assert "s3cr3t" not in out and n >= 1


def test_redacts_aws_key_and_token_and_email():
    out, n = redact("key AKIAIOSFODNN7EXAMPLE token=abcdef1234567890 me@example.com")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "abcdef1234567890" not in out
    assert "me@example.com" not in out
    assert n >= 3


def test_leaves_clean_text_untouched():
    text = "AnalysisException cannot resolve column amount"
    out, n = redact(text)
    assert out == text and n == 0
