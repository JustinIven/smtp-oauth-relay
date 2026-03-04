import asyncio

import pytest

import constants
import custom


@pytest.fixture
def loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def smtp(loop: asyncio.AbstractEventLoop) -> custom.CustomSMTP:
    return custom.CustomSMTP(handler=None, loop=loop, enable_SMTPUTF8=True)


def test_custom_smtp_auth_and_starttls(
    smtp: custom.CustomSMTP,
    loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    async def fake_super_auth(self, arg):
        captured["arg"] = arg
        return "ok"

    async def fake_super_starttls(self, arg):
        raise custom.TLSSetupException("boom")

    monkeypatch.setattr(custom.SMTP, "smtp_AUTH", fake_super_auth)
    monkeypatch.setattr(custom.SMTP, "smtp_STARTTLS", fake_super_starttls)

    assert loop.run_until_complete(smtp.smtp_AUTH("login foo")) == "ok"
    assert captured["arg"] == "LOGIN foo"

    assert loop.run_until_complete(smtp.smtp_STARTTLS("")) == constants.SMTP_TLS_NOT_AVAILABLE


def test_custom_session_login_data(loop: asyncio.AbstractEventLoop) -> None:
    session = custom.CustomSession(loop)
    session.login_data = "value"
    assert session.login_data == "value"


def test_custom_session_factory(smtp: custom.CustomSMTP) -> None:
    session = smtp._create_session()
    assert isinstance(session, custom.CustomSession)
