import types
from email import policy
from email.parser import BytesParser

import pytest

import graph_client


@pytest.fixture
def parsed_message() -> BytesParser:
    return BytesParser(policy=policy.SMTP).parsebytes(
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"Subject: Test\r\n"
        b"Message-ID: <id@example.com>\r\n\r\nBody"
    )


@pytest.fixture
def envelope() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        mail_from="sender@example.com",
        rcpt_tos=["recipient@example.com"],
    )


@pytest.mark.parametrize(
    ("status", "text", "expected"),
    [
        (202, "", (True, None, 202)),
        (400, "bad", (False, "Status code 400; response body: bad", 400)),
    ],
)
def test_send_email_statuses(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    text: str,
    expected: tuple[bool, str | None, int | None],
) -> None:
    class FakeResponse:
        def __init__(self, status_code: int, text_value: str) -> None:
            self.status_code = status_code
            self.text = text_value

    monkeypatch.setattr(
        graph_client.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(status, text),
    )
    assert graph_client.send_email("token", b"Body", "user@example.com") == expected


def test_send_email_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_client.requests, "post", raise_error)
    success, error_detail, status_code = graph_client.send_email("token", b"body", "user@x.com")
    assert success is False
    assert status_code is None
    assert "boom" in error_detail


def test_send_failure_notification(
    monkeypatch: pytest.MonkeyPatch,
    parsed_message,
    envelope,
) -> None:
    captured = {}

    def fake_send_email(access_token, body, from_email, log_context=None):
        captured["body"] = body
        captured["from_email"] = from_email
        captured["log_context"] = log_context
        return True, None, 202

    monkeypatch.setattr(graph_client, "send_email", fake_send_email)

    graph_client.send_failure_notification(
        access_token="token",
        from_email="notify@example.com",
        notification_address="alerts@example.com",
        parsed_message=parsed_message,
        envelope=envelope,
        error_detail="Boom"
    )

    message = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert message["Subject"].startswith("SMTP relay failure")
    assert message["To"] == "alerts@example.com"
    assert message["From"] == "notify@example.com"
    assert captured["log_context"] == "failure notification to alerts@example.com"


def test_send_failure_notification_logs_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    parsed_message,
    envelope,
) -> None:
    monkeypatch.setattr(graph_client, "send_email", lambda *args, **kwargs: (False, "oops", 500))
    with caplog.at_level("ERROR"):
        graph_client.send_failure_notification(
            access_token="token",
            from_email="notify@example.com",
            notification_address="alerts@example.com",
            parsed_message=parsed_message,
            envelope=envelope,
            error_detail="Boom"
        )
    assert "Failed to send failure notification" in caplog.text
