"""T17: segredos mascarados e contexto nos logs."""

import json
import logging

from pulseops.logs import JsonFormatter, log_context, redact_text


def render(message: str, **extra: object) -> dict[str, object]:
    record = logging.LogRecord("pulseops.test", logging.INFO, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_query_string_and_userinfo_are_redacted() -> None:
    text = redact_text("GET https://user:secret@api.example.com/x?token=abc&b=2 failed")
    assert "secret" not in text and "token=abc" not in text
    assert "https://[redacted]@api.example.com/x?[redacted]" in text


def test_sensitive_extra_fields_are_masked() -> None:
    line = render("login", password="p", authorization="Bearer x", cookie="c", monitor_id=3)
    assert line["password"] == line["authorization"] == line["cookie"] == "[redacted]"
    assert line["monitor_id"] == 3


def test_context_is_added_to_every_line() -> None:
    with log_context(monitor_id=7, run_key="7:2026-01-15T12:00:00.000+00:00"):
        line = render("check saved")
    assert line["monitor_id"] == 7 and line["run_key"].startswith("7:")
    assert "monitor_id" not in render("outside the context")


def test_output_is_json_with_level_and_message() -> None:
    line = render("hello %s")
    assert (
        line["level"] == "INFO" and line["msg"] == "hello %s" and line["logger"] == "pulseops.test"
    )
