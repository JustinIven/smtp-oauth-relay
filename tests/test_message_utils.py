from email import policy
from email.parser import BytesParser

import pytest

import constants
import message_utils


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"Subject: Hi\r\n\r\nBody", (b"Subject: Hi", b"\r\n\r\n", b"Body")),
        (b"Subject: Hi\n\nBody", (b"Subject: Hi", b"\n\n", b"Body")),
        (b"Body only", (b"Body only", b"", b"")),
        (b"\r\nBody", (b"", b"\r\n", b"Body")),
        (b"\nBody", (b"", b"\n", b"Body")),
    ],
)
def test_split_raw_message_variants(raw: bytes, expected: tuple[bytes, bytes, bytes]) -> None:
    assert message_utils.split_raw_message(raw) == expected


@pytest.mark.parametrize(
    ("raw", "updates", "assertions", "absent"),
    [
        (
            b"From: old@example.com\r\nSubject: Test\r\n\r\nBody",
            {"From": "new@example.com", "X-Test": "yes"},
            [b"From: new@example.com", b"X-Test: yes"],
            [b"From: old@example.com"],
        ),
        (
            b"From: old@example.com\r\nSubject: Test\r\n\r\nBody",
            {"X-Test": "yes"},
            [b"X-Test: yes"],
            [],
        ),
        (b"Body", {"X-Test": "yes"}, [b"X-Test: yes"], []),
    ],
)
def test_update_raw_headers(
    raw: bytes,
    updates: dict[str, str],
    assertions: list[bytes],
    absent: list[bytes],
) -> None:
    updated = message_utils.update_raw_headers(raw, updates)
    for token in assertions:
        assert token in updated
    for token in absent:
        assert token not in updated


def test_update_raw_headers_appends_with_line_endings() -> None:
    raw = b"From: old@example.com\r\nSubject: Test\r\n\r\nBody"
    updated = message_utils.update_raw_headers(raw, {"X-Test": "yes"})
    parsed = BytesParser(policy=policy.SMTP).parsebytes(updated)
    assert parsed.get("Subject") == "Test"
    assert parsed.get("X-Test") == "yes"


def test_update_raw_headers_skips_folded_lines() -> None:
    raw = b"Subject: Test\r\n\tcontinued\r\nX-Test: yes\r\n\r\nBody"
    updated = message_utils.update_raw_headers(raw, {"Subject": "New"})
    parsed = BytesParser(policy=policy.SMTP).parsebytes(updated)
    assert parsed.get("Subject") == "New"


def test_update_raw_headers_no_separator_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        message_utils,
        "split_raw_message",
        lambda _raw: (b"Header: value", b"", b"Body"),
    )
    updated = message_utils.update_raw_headers(b"ignored", {"X-Test": "yes"})
    assert b"X-Test: yes" in updated
    assert b"\r\n\r\nBody" in updated or b"\n\nBody" in updated


def test_apply_header_updates_noop() -> None:
    raw = b"From: a@b.com\r\n\r\nBody"
    parsed = BytesParser(policy=policy.SMTP).parsebytes(raw)
    assert message_utils.apply_header_updates(raw, parsed, {}, []) == raw


def test_apply_header_updates_removes_header() -> None:
    raw = b"Subject: Test\r\nX-Remove: yes\r\n\r\nBody"
    parsed = BytesParser(policy=policy.SMTP).parsebytes(raw)
    updated = message_utils.apply_header_updates(raw, parsed, {"X-Remove": None}, ["test"])
    assert b"X-Remove" not in updated


def test_apply_header_updates_debug_logging(caplog: pytest.LogCaptureFixture) -> None:
    raw = b"Subject: Test\r\nX-Remove: yes\r\n\r\nBody"
    parsed = BytesParser(policy=policy.SMTP).parsebytes(raw)
    with caplog.at_level("DEBUG"):
        updated = message_utils.apply_header_updates(
            raw,
            parsed,
            {"X-Remove": None, "X-Add": "yes"},
            ["test"],
        )
    assert b"X-Remove" not in updated


@pytest.mark.parametrize(
    ("existing", "original", "expected"),
    [
        (
            "ops@example.com",
            "Group <group@example.com>",
            "ops@example.com, Group <group@example.com>",
        ),
        ("ops@example.com", "invalid <>", "ops@example.com"),
        ("ops@example.com", "ops@example.com", "ops@example.com"),
    ],
)
def test_build_reply_to_value(existing: str, original: str, expected: str) -> None:
    assert message_utils.build_reply_to_value(existing, original) == expected


@pytest.mark.parametrize(
    ("raw", "allow_invalid_from", "expected"),
    [
        (b"From: sender@example.com\r\n\r\nBody", False, constants.SMTP_MISSING_DATE),
        (b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody", False, constants.SMTP_MISSING_FROM),
        (b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody", True, None),
        (b"From: <>\r\nDate: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody", True, None),
        (b"From: a@b.com\n\nBody", False, constants.SMTP_BARE_LF),
        (b"From: a@b.com\r\n\r\nBody", False, constants.SMTP_MISSING_DATE),
        (b"From: a@b.com\r\nDate: nope\r\n\r\nBody", False, constants.SMTP_INVALID_DATE),
        (
            b"From: <>\r\nDate: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody",
            False,
            constants.SMTP_INVALID_FROM,
        ),
    ],
)
def test_validate_rfc5322_cases(
    raw: bytes,
    allow_invalid_from: bool,
    expected: str | None,
) -> None:
    assert (
        message_utils.validate_rfc5322_message(raw, allow_invalid_from=allow_invalid_from)
        == expected
    )


def test_validate_rfc5322_invalid_date_none(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_message = (
        b"From: sender@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody"
    )
    monkeypatch.setattr(message_utils, "parsedate_to_datetime", lambda _value: None)
    assert message_utils.validate_rfc5322_message(raw_message) == constants.SMTP_INVALID_DATE


def test_message_utils_logging_helpers() -> None:
    message_utils.log_recipient_header_remap()
    message_utils.log_envelope_recipient_remap()
    message_utils.log_failback_sender_used("example.com")
    message_utils.log_failback_sender_missing()
    message_utils.log_from_remap_applied("example.com", "sender@example.com")
    message_utils.log_from_remap_missing("example.com")
    message_utils.log_failure_notification_missing_sender("example.com")
    message_utils.log_rfc5322_validation_failed("error")
    message_utils.log_invalid_x_sender("bad", "sender@example.com", "return", "from")
    message_utils.log_invalid_x_sender("bad", None, "return", "from")
