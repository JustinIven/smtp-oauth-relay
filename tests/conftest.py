import asyncio
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _ensure_requests_stub() -> None:
    try:
        import requests  # noqa: F401
    except ModuleNotFoundError:
        stub = ModuleType("requests")

        class RequestException(Exception):
            pass

        def post(*_args, **_kwargs):
            raise RequestException("requests stub in tests")

        stub.RequestException = RequestException
        stub.post = post
        sys.modules["requests"] = stub


def _ensure_azure_stubs() -> None:
    try:
        import azure  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["azure"] = ModuleType("azure")

    if "azure.data" not in sys.modules:
        sys.modules["azure.data"] = ModuleType("azure.data")

    if "azure.data.tables" not in sys.modules:
        tables = ModuleType("azure.data.tables")

        class TableClient:
            @staticmethod
            def from_table_url(*_args, **_kwargs):
                raise RuntimeError("azure.data.tables stub in tests")

        tables.TableClient = TableClient
        sys.modules["azure.data.tables"] = tables

    if "azure.identity" not in sys.modules:
        identity = ModuleType("azure.identity")

        class DefaultAzureCredential:  # noqa: N801 - match Azure SDK naming
            pass

        identity.DefaultAzureCredential = DefaultAzureCredential
        sys.modules["azure.identity"] = identity

    if "azure.keyvault.secrets" not in sys.modules:
        secrets = ModuleType("azure.keyvault.secrets")

        class SecretClient:  # noqa: N801 - match Azure SDK naming
            def __init__(self, *args, **kwargs):
                pass

        secrets.SecretClient = SecretClient
        sys.modules["azure.keyvault.secrets"] = secrets


def _ensure_aiosmtpd_stub() -> None:
    try:
        import aiosmtpd  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["aiosmtpd"] = ModuleType("aiosmtpd")

    if "aiosmtpd.smtp" not in sys.modules:
        smtp = ModuleType("aiosmtpd.smtp")

        class TLSSetupException(Exception):
            pass

        class AuthResult:
            def __init__(self, success=False, handled=True, message=None, auth_data=None):
                self.success = success
                self.handled = handled
                self.message = message
                self.auth_data = auth_data

        class Session:
            def __init__(self, loop):
                self.loop = loop

        class SMTP:
            def __init__(self, handler=None, loop=None, **kwargs):
                self.handler = handler
                self.loop = loop
                self.tls_context = kwargs.get("tls_context")

            async def smtp_AUTH(self, arg):
                return None

            async def smtp_STARTTLS(self, arg):
                return None

        smtp.AuthResult = AuthResult
        smtp.Session = Session
        smtp.SMTP = SMTP
        smtp.TLSSetupException = TLSSetupException
        smtp.MISSING = object()
        sys.modules["aiosmtpd.smtp"] = smtp

    if "aiosmtpd.controller" not in sys.modules:
        controller = ModuleType("aiosmtpd.controller")

        class Controller:
            def __init__(self, handler, **kwargs):
                self.handler = handler
                self.SMTP_kwargs = kwargs

            def start(self):
                return None

            def stop(self):
                return None

        controller.Controller = Controller
        sys.modules["aiosmtpd.controller"] = controller


_ensure_requests_stub()
_ensure_azure_stubs()
_ensure_aiosmtpd_stub()


@pytest.fixture(autouse=True)
def reset_rate_limiter_registry():
    try:
        import rate_limiter
    except Exception:
        yield
        return
    rate_limiter._limiters.clear()
    yield
    rate_limiter._limiters.clear()


@pytest.fixture
def handler():
    import main

    return main.Handler()


@pytest.fixture
def token_session() -> types.SimpleNamespace:
    return types.SimpleNamespace(access_token="token", lookup_from_email=None)


@pytest.fixture
def envelope_factory():
    def _make(
        content: bytes,
        mail_from: str = "sender@example.com",
        rcpt_tos: list[str] | None = None,
    ) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            mail_from=mail_from,
            rcpt_tos=rcpt_tos or ["recipient@example.com"],
            content=content,
        )

    return _make


@pytest.fixture
def run_data():
    def _run(handler, session, envelope) -> str:
        return asyncio.run(handler.handle_DATA(None, session, envelope))

    return _run


@pytest.fixture
def patch_domain_context(monkeypatch: pytest.MonkeyPatch):
    import main

    def _patch(context):
        monkeypatch.setattr(
            main.config_resolver,
            "resolve_domain_context",
            lambda *args, **kwargs: context,
        )

    return _patch
