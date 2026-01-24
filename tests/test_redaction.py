from specguard.utils import redact


def test_redact_openai_key():
    txt = "hello sk-1234567890123456789012345 world"
    r = redact(txt)
    assert "[REDACTED]" in r.redacted_text
    assert r.redacted_count >= 1


def test_redact_kv_patterns():
    txt = "api_key=SUPERSECRET1234567890"
    r = redact(txt)
    assert "[REDACTED]" in r.redacted_text
