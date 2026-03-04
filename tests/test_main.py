import asyncio
import types
from email import policy
from email.parser import BytesParser

import pytest

import main


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("invalid address", "553"),
        ("sender@example.com", main.MISSING),
    ],
)
def test_handle_mail_addresses(handler: main.Handler, address: str, expected: str) -> None:
    response = asyncio.run(handler.handle_MAIL(None, None, None, address, []))
    if expected is main.MISSING:
        assert response is main.MISSING
    else:
        assert response.startswith(expected)


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("<>", "553"),
        ("recipient@example.com", main.MISSING),
    ],
)
def test_handle_rcpt_addresses(handler: main.Handler, address: str, expected: str) -> None:
    response = asyncio.run(handler.handle_RCPT(None, None, None, address, []))
    if expected is main.MISSING:
        assert response is main.MISSING
    else:
        assert response.startswith(expected)


def test_handler_requires_auth_token(
    handler: main.Handler,
    envelope_factory,
    run_data,
) -> None:
    session = types.SimpleNamespace()
    envelope = envelope_factory(
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody"
    )
    response = run_data(handler, session, envelope)
    assert response.startswith("530")


def test_handler_sends_email(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main.graph_client, "send_email", lambda *args, **kwargs: (True, None, 202))

    envelope = envelope_factory(
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody"
    )
    response = run_data(handler, token_session, envelope)
    assert response == "250 OK"


def test_handler_inserts_reply_to_when_missing(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_send_email(access_token, body, from_email):
        captured["body"] = body
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", fake_send_email)
    envelope = envelope_factory(
        b"From: Sender Name <sender@example.com>\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody"
    )

    response = run_data(handler, token_session, envelope)
    assert response == "250 OK"

    parsed = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert parsed.get("Reply-To") == "Sender Name <sender@example.com>"


def test_handler_uses_from_header_with_return_path(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_send_email(access_token, body, from_email):
        captured["body"] = body
        captured["from_email"] = from_email
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", fake_send_email)
    envelope = envelope_factory(
        b"Return-Path: notifications@example.com\r\n"
        b"From: Sender Name <sender@example.com>\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody",
        mail_from="notifications@example.com",
    )

    response = run_data(handler, token_session, envelope)
    assert response == "250 OK"

    parsed = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert captured["from_email"] == "sender@example.com"
    assert parsed.get("Return-Path") == "notifications@example.com"


def test_handler_normalizes_invalid_x_sender(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_send_email(access_token, body, from_email):
        captured["body"] = body
        captured["from_email"] = from_email
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", fake_send_email)
    envelope = envelope_factory(
        b"x-sender: <>\r\n"
        b"From: sender@example.com\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"\r\nBody",
        mail_from="<>",
    )

    response = run_data(handler, token_session, envelope)
    assert response == "250 OK"

    parsed = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert parsed.get("X-Sender") == "sender@example.com"
