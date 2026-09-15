from kira.redaction import redact


def test_email():
    out = redact("contact me at foo.bar@example.com please")
    assert "foo.bar@example.com" not in out
    assert "[REDACTED:EMAIL]" in out


def test_credit_card():
    out = redact("card 4111 1111 1111 1111 expires soon")
    assert "4111" not in out
    assert "[REDACTED:CREDIT_CARD]" in out


def test_jwt():
    out = redact(
        "token=eyJabcdefghij.eyJabcdefghij.signature_partabcdefghij"
    )
    assert "[REDACTED:JWT_TOKEN]" in out


def test_private_key_block():
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----"
    )
    out = redact(text)
    assert "[REDACTED:PRIVATE_KEY]" in out
    assert "MIIB" not in out


def test_leaves_normal_text():
    out = redact("hello world this is fine")
    assert out == "hello world this is fine"


def test_selective_patterns():
    out = redact("email me at x@y.com", enabled_patterns=["credit_card"])
    assert "x@y.com" in out
