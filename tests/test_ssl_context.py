import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

import sslContext


class FakeKey:
    def private_bytes(self, **_kwargs):
        return b"key"


class FakeCert:
    def public_bytes(self, *_args, **_kwargs):
        return b"cert"


def install_keyvault_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secret_value: str | None = "dGVzdA==",
    pkcs12_result=None,
    pkcs12_exc: Exception | None = None,
) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_secret(self, name):
            return types.SimpleNamespace(value=secret_value)

    if pkcs12_result is None and pkcs12_exc is None:
        pkcs12_result = (FakeKey(), FakeCert(), None)

    if pkcs12_exc is not None:
        def load_key_and_certificates(*_args, **_kwargs):
            raise pkcs12_exc
    else:
        def load_key_and_certificates(*_args, **_kwargs):
            return pkcs12_result

    fake_identity = ModuleType("azure.identity")
    fake_identity.DefaultAzureCredential = lambda: object()
    fake_secrets = ModuleType("azure.keyvault.secrets")
    fake_secrets.SecretClient = FakeClient
    fake_serialization = ModuleType("cryptography.hazmat.primitives.serialization")
    fake_serialization.Encoding = types.SimpleNamespace(PEM=b"pem")
    fake_serialization.NoEncryption = lambda: None
    fake_serialization.PrivateFormat = types.SimpleNamespace(TraditionalOpenSSL=object())
    fake_serialization.pkcs12 = types.SimpleNamespace(
        load_key_and_certificates=load_key_and_certificates
    )

    serialization_key = "cryptography.hazmat.primitives.serialization"
    monkeypatch.setitem(sys.modules, "azure.identity", fake_identity)
    monkeypatch.setitem(sys.modules, "azure.keyvault.secrets", fake_secrets)
    monkeypatch.setitem(sys.modules, serialization_key, fake_serialization)


def test_ssl_from_file_loads_cert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")

    class FakeContext:
        def __init__(self):
            self.loaded = None

        def load_cert_chain(self, certfile, keyfile):
            self.loaded = (certfile, keyfile)

    monkeypatch.setattr(
        sslContext.ssl,
        "create_default_context",
        lambda *_args, **_kwargs: FakeContext()
    )
    context = sslContext.from_file(str(cert_path), str(key_path))
    assert context.loaded == (str(cert_path), str(key_path))


@pytest.mark.parametrize(
    ("cert_path", "key_path", "expected"),
    [
        ("/nope/cert.pem", "/nope/key.pem", FileNotFoundError),
        ("cert_dir", "key.pem", FileNotFoundError),
    ],
)
def test_ssl_from_file_missing_or_not_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cert_path: str,
    key_path: str,
    expected: type[Exception],
) -> None:
    if cert_path == "cert_dir":
        path = tmp_path / cert_path
        path.mkdir()
        (tmp_path / key_path).write_text("key", encoding="utf-8")
        cert_path = str(path)
        key_path = str(tmp_path / key_path)
    with pytest.raises(expected):
        sslContext.from_file(str(cert_path), str(key_path))


def test_ssl_from_file_bad_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_text("cert", encoding="utf-8")
    key_path.write_text("key", encoding="utf-8")

    class FakeContext:
        def load_cert_chain(self, certfile, keyfile):
            raise sslContext.ssl.SSLError("bad")

    monkeypatch.setattr(
        sslContext.ssl,
        "create_default_context",
        lambda *_args, **_kwargs: FakeContext()
    )
    with pytest.raises(sslContext.ssl.SSLError):
        sslContext.from_file(str(cert_path), str(key_path))


def test_ssl_from_keyvault_success(monkeypatch: pytest.MonkeyPatch) -> None:
    install_keyvault_modules(monkeypatch)

    class FakeContext:
        def load_cert_chain(self, certfile, keyfile):
            pass

    monkeypatch.setattr(
        sslContext.ssl,
        "create_default_context",
        lambda *_args, **_kwargs: FakeContext()
    )
    sslContext.from_keyvault("https://vault", "cert")


@pytest.mark.parametrize(
    ("secret_value", "pkcs12_result", "pkcs12_exc"),
    [
        (None, None, None),
        ("dGVzdA==", (None, None, None), None),
        ("dGVzdA==", (None, FakeCert(), None), None),
        ("dGVzdA==", None, ValueError("bad")),
    ],
)
def test_ssl_from_keyvault_invalid_inputs(
    monkeypatch: pytest.MonkeyPatch,
    secret_value: str | None,
    pkcs12_result,
    pkcs12_exc,
) -> None:
    install_keyvault_modules(
        monkeypatch,
        secret_value=secret_value,
        pkcs12_result=pkcs12_result,
        pkcs12_exc=pkcs12_exc,
    )
    with pytest.raises(ValueError):
        sslContext.from_keyvault("https://vault", "cert")


def test_ssl_from_keyvault_cleanup_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    install_keyvault_modules(monkeypatch)

    class FakeContext:
        def load_cert_chain(self, certfile, keyfile):
            pass

    monkeypatch.setattr(
        sslContext.ssl,
        "create_default_context",
        lambda *_args, **_kwargs: FakeContext()
    )

    def fail_unlink(_path):
        raise OSError("nope")

    monkeypatch.setattr(sslContext.os, "unlink", fail_unlink)
    with caplog.at_level("WARNING"):
        sslContext.from_keyvault("https://vault", "cert")
    assert "Failed to remove temporary certificate file" in caplog.text


def test_ssl_logging_helpers() -> None:
    sslContext.log_loaded_certificate_from_file("cert.pem")
    sslContext.log_loaded_certificate_from_keyvault("cert")
    sslContext.log_invalid_tls_source("invalid")
    sslContext.log_missing_keyvault_config()
    sslContext.log_tls_cipher_suites("TLS_AES_128_GCM_SHA256")
