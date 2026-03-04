import asyncio
import types
from email import policy
from email.parser import BytesParser

import pytest

import config_resolver
import constants
import main
import remap

BASE_MESSAGE = (
    b"From: sender@example.com\r\n"
    b"To: recipient@example.com\r\n"
    b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody"
)


def set_base_config(monkeypatch: pytest.MonkeyPatch, **overrides) -> None:
    base = {
        "TLS_SOURCE": "off",
        "REQUIRE_TLS": False,
        "SERVER_GREETING": "Test",
        "TLS_CIPHER_SUITE": None,
        "AZURE_KEY_VAULT_URL": None,
        "AZURE_KEY_VAULT_CERT_NAME": None,
    }
    base.update(overrides)
    for key, value in base.items():
        monkeypatch.setattr(main.config, key, value)


def patch_controller(monkeypatch: pytest.MonkeyPatch, *, start_error: bool = False) -> None:
    class FakeController:
        def __init__(self, *args, **kwargs):
            self.started = False

        def start(self):
            if start_error:
                raise RuntimeError("boom")
            self.started = True

        def stop(self):
            return None

    monkeypatch.setattr(main, "CustomController", FakeController)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(404, constants.SMTP_USER_NOT_LOCAL), (500, constants.SMTP_ACTION_ABORTED)],
)
def test_handle_data_send_email_failure(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    expected: str,
) -> None:
    envelope = envelope_factory(BASE_MESSAGE)
    monkeypatch.setattr(main.config, "GRAPH_FAILBACK_ON_404", False)
    patch_domain_context(config_resolver.DomainContext(None, None, None, None))

    def send_fail(*_args, **_kwargs):
        return False, "err", status

    monkeypatch.setattr(main.graph_client, "send_email", send_fail)
    response = run_data(handler, token_session, envelope)
    assert response == expected


def test_handle_data_retry_404_with_failback(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = envelope_factory(BASE_MESSAGE)
    context = config_resolver.DomainContext(
        domain="example.com",
        settings=None,
        failure_notification=None,
        failback_address="failback@example.com",
    )
    patch_domain_context(context)
    monkeypatch.setattr(main.config, "GRAPH_FAILBACK_ON_404", True)
    calls: list[tuple[bytes, str]] = []

    def send_fail_then_succeed(access_token, body, from_email):
        calls.append((body, from_email))
        if len(calls) == 1:
            return False, "err", 404
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", send_fail_then_succeed)
    response = run_data(handler, token_session, envelope)
    assert response == constants.SMTP_OK
    assert [from_email for _, from_email in calls] == [
        "sender@example.com",
        "failback@example.com",
    ]
    parsed = BytesParser(policy=policy.SMTP).parsebytes(calls[-1][0])
    assert parsed.get("From") == "failback@example.com"


def test_handle_data_rfc_validation_error(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
) -> None:
    envelope = envelope_factory(b"From: sender@example.com\r\n\r\nBody")
    patch_domain_context(config_resolver.DomainContext(None, None, None, None))
    response = run_data(handler, token_session, envelope)
    assert response == constants.SMTP_MISSING_DATE


def test_handle_data_failure_notification(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = envelope_factory(BASE_MESSAGE)
    context = config_resolver.DomainContext(
        domain="example.com",
        settings=None,
        failure_notification="ops@example.com",
        failback_address=None,
    )
    patch_domain_context(context)

    def send_fail(*_args, **_kwargs):
        return False, "err", 500

    monkeypatch.setattr(main.graph_client, "send_email", send_fail)
    captured = {}

    def fake_notify(**kwargs):
        captured["notification_address"] = kwargs["notification_address"]

    monkeypatch.setattr(main.graph_client, "send_failure_notification", fake_notify)
    response = run_data(handler, token_session, envelope)
    assert response == constants.SMTP_ACTION_ABORTED
    assert captured["notification_address"] == "ops@example.com"


def test_handle_data_exception(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = envelope_factory(BASE_MESSAGE)
    patch_domain_context(config_resolver.DomainContext(None, None, None, None))

    def raise_error(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main.graph_client, "send_email", raise_error)
    response = run_data(handler, token_session, envelope)
    assert response == constants.SMTP_TRANSACTION_FAILED


def test_handle_data_applies_failback_sender(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = envelope_factory(b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody", "<>")
    context = config_resolver.DomainContext(
        domain="example.com",
        settings=None,
        failure_notification=None,
        failback_address="failback@example.com",
    )
    patch_domain_context(context)
    captured = {}

    def fake_send_email(access_token, body, from_email):
        captured["body"] = body
        captured["from_email"] = from_email
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", fake_send_email)
    response = run_data(handler, token_session, envelope)
    assert response == constants.SMTP_OK
    parsed = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert parsed.get("From") == "failback@example.com"
    assert parsed.get("X-Sender") == "failback@example.com"


def test_handle_data_skips_reply_to_for_invalid_from(
    handler: main.Handler,
    token_session: types.SimpleNamespace,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = envelope_factory(
        b"From: <>\r\nDate: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody",
        "<>",
    )
    context = config_resolver.DomainContext(
        domain="example.com",
        settings=None,
        failure_notification=None,
        failback_address="failback@example.com",
    )
    patch_domain_context(context)
    captured = {}

    def fake_send_email(access_token, body, from_email):
        captured["body"] = body
        captured["from_email"] = from_email
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", fake_send_email)
    response = run_data(handler, token_session, envelope)
    assert response == constants.SMTP_OK
    parsed = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert parsed.get("From") == "failback@example.com"
    assert parsed.get("Reply-To") is None


def test_handle_data_remap_and_lookup(
    handler: main.Handler,
    envelope_factory,
    patch_domain_context,
    run_data,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = types.SimpleNamespace(access_token="token", lookup_from_email="lookup@example.com")
    envelope = envelope_factory(
        b"From: Sender <sender@example.com>\r\n"
        b"To: recipient@example.com\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n\r\nBody"
    )
    context = config_resolver.DomainContext(
        domain="example.com",
        settings=None,
        failure_notification=None,
        failback_address="failback@example.com",
    )
    patch_domain_context(context)

    def remap_enabled(*_args, **_kwargs):
        return True

    def remap_headers(*_args, **_kwargs):
        return {"To": "new@example.com"}

    def remap_list(*_args, **_kwargs):
        return ["new@example.com"]

    monkeypatch.setattr(remap, "is_remap_enabled", remap_enabled)
    monkeypatch.setattr(remap, "remap_recipient_headers", remap_headers)
    monkeypatch.setattr(remap, "remap_recipient_list", remap_list)

    captured = {}

    def fake_send_email(access_token, body, from_email):
        captured["body"] = body
        captured["from_email"] = from_email
        return True, None, 202

    monkeypatch.setattr(main.graph_client, "send_email", fake_send_email)
    response = run_data(handler, session, envelope)
    assert response == constants.SMTP_OK
    assert envelope.rcpt_tos == ["new@example.com"]
    parsed = BytesParser(policy=policy.SMTP).parsebytes(captured["body"])
    assert parsed.get("From") == "lookup@example.com"
    assert parsed.get("Reply-To") == "Sender <sender@example.com>"
    assert parsed.get("To") == "new@example.com"
    assert captured["from_email"] == "lookup@example.com"


def test_amain_tls_off(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_controller(monkeypatch)
    set_base_config(monkeypatch, TLS_SOURCE="off")
    asyncio.run(main.amain())


def test_amain_invalid_tls_source(monkeypatch: pytest.MonkeyPatch) -> None:
    set_base_config(monkeypatch, TLS_SOURCE="nope")
    with pytest.raises(ValueError):
        asyncio.run(main.amain())


def test_amain_keyvault_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    set_base_config(monkeypatch, TLS_SOURCE="keyvault")
    with pytest.raises(ValueError):
        asyncio.run(main.amain())


def test_amain_keyvault_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeContext:
        def get_ciphers(self):
            return [{"name": "TLS_AES_128_GCM_SHA256"}]

    patch_controller(monkeypatch)
    monkeypatch.setattr(main.sslContext, "from_keyvault", lambda *_args, **_kwargs: FakeContext())
    set_base_config(
        monkeypatch,
        TLS_SOURCE="keyvault",
        AZURE_KEY_VAULT_URL="https://vault",
        AZURE_KEY_VAULT_CERT_NAME="cert",
    )

    asyncio.run(main.amain())


def test_amain_tls_file_with_cipher(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeContext:
        def set_ciphers(self, _value):
            return None

        def get_ciphers(self):
            return [{"name": "TLS_AES_128_GCM_SHA256"}]

    patch_controller(monkeypatch)
    monkeypatch.setattr(main.sslContext, "from_file", lambda *_args, **_kwargs: FakeContext())
    set_base_config(monkeypatch, TLS_SOURCE="file", TLS_CIPHER_SUITE="TLS_AES_128_GCM_SHA256")

    asyncio.run(main.amain())


def test_amain_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_controller(monkeypatch, start_error=True)
    monkeypatch.setattr(main.sslContext, "from_file", lambda *_args, **_kwargs: None)
    set_base_config(monkeypatch, TLS_SOURCE="file")

    with pytest.raises(RuntimeError):
        asyncio.run(main.amain())
