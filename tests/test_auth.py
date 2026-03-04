import base64
import types
import uuid

import pytest

import auth
import constants


def encode_uuid(value: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(value.bytes).decode().rstrip("=")


@pytest.fixture
def session() -> types.SimpleNamespace:
    return types.SimpleNamespace()


@pytest.fixture
def auth_data() -> types.SimpleNamespace:
    return types.SimpleNamespace(login=b"user", password=b"secret")


def test_decode_uuid_or_base64url_roundtrip() -> None:
    value = uuid.uuid4()
    encoded = encode_uuid(value)
    assert auth.decode_uuid_or_base64url(str(value)) == str(value)
    assert auth.decode_uuid_or_base64url(encoded) == str(value)


def test_decode_uuid_or_base64url_invalid() -> None:
    with pytest.raises(ValueError):
        auth.decode_uuid_or_base64url("not-base64")


def test_lookup_user_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "AZURE_TABLES_URL", "https://example.com/table")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query_entities(self, query_filter):
            return iter([
                {
                    "tenant_id": "tenant",
                    "client_id": "client",
                    "from_email": "sender@example.com",
                }
            ])

    monkeypatch.setattr(auth, "DefaultAzureCredential", lambda: object())
    monkeypatch.setattr(auth.TableClient, "from_table_url", lambda *args, **kwargs: FakeClient())

    tenant_id, client_id, from_email = auth.lookup_user("lookup")
    assert tenant_id == "tenant"
    assert client_id == "client"
    assert from_email == "sender@example.com"


@pytest.mark.parametrize(
    ("tables_url", "expected_exc"),
    [
        (None, ValueError),
        ("https://example.com/table", RuntimeError),
    ],
)
def test_lookup_user_errors(
    monkeypatch: pytest.MonkeyPatch,
    tables_url: str | None,
    expected_exc: type[Exception],
) -> None:
    monkeypatch.setattr(auth, "AZURE_TABLES_URL", tables_url)

    def raise_client(*_args, **_kwargs):
        raise RuntimeError("boom")

    if tables_url:
        monkeypatch.setattr(auth.TableClient, "from_table_url", raise_client)

    with pytest.raises(expected_exc):
        auth.lookup_user("missing")


@pytest.mark.parametrize(
    ("username", "expected"),
    [
        ("app@lookup", ("tenant", "client", "from@example.com")),
    ],
)
def test_parse_username_lookup(
    monkeypatch: pytest.MonkeyPatch,
    username: str,
    expected: tuple[str, str, str | None],
) -> None:
    monkeypatch.setattr(auth, "USERNAME_DELIMITER", "@")
    monkeypatch.setattr(auth, "lookup_user", lambda lookup_id: expected)
    assert auth.parse_username(username) == expected


def test_parse_username_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "USERNAME_DELIMITER", "@")
    tenant_uuid = uuid.uuid4()
    client_uuid = uuid.uuid4()
    tenant_b64 = encode_uuid(tenant_uuid)
    client_b64 = encode_uuid(client_uuid)
    tenant_id, client_id, from_email = auth.parse_username(f"{tenant_b64}@{client_b64}.local")
    assert tenant_id == str(tenant_uuid)
    assert client_id == str(client_uuid)
    assert from_email is None


@pytest.mark.parametrize("username", ["invalid", "too@many@parts"])
def test_parse_username_invalid(username: str) -> None:
    with pytest.raises(ValueError):
        auth.parse_username(username)


@pytest.mark.parametrize(
    ("payload", "expected", "raises"),
    [
        ({"access_token": "token"}, "token", None),
        ({}, None, ValueError),
    ],
)
def test_get_access_token_payloads(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict,
    expected: str | None,
    raises: type[Exception] | None,
) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: FakeResponse())
    if raises:
        with pytest.raises(raises):
            auth.get_access_token("tenant", "client", "secret")
    else:
        assert auth.get_access_token("tenant", "client", "secret") == expected


def test_get_access_token_request_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 500
        text = "nope"

    class FakeException(auth.requests.RequestException):
        def __init__(self):
            super().__init__("boom")
            self.response = FakeResponse()

    def raise_request(*_args, **_kwargs):
        raise FakeException()

    monkeypatch.setattr(auth.requests, "post", raise_request)
    with pytest.raises(auth.requests.RequestException):
        auth.get_access_token("tenant", "client", "secret")


@pytest.mark.parametrize("mechanism", ["LOGIN", "PLAIN"])
def test_authenticator_success(
    monkeypatch: pytest.MonkeyPatch,
    session: types.SimpleNamespace,
    auth_data: types.SimpleNamespace,
    mechanism: str,
) -> None:
    monkeypatch.setattr(auth, "parse_username", lambda _: ("tenant", "client", None))
    monkeypatch.setattr(auth, "get_access_token", lambda *args, **kwargs: "token")

    result = auth.Authenticator()(None, session, None, mechanism, auth_data)
    assert result.success is True
    assert session.access_token == "token"


def test_authenticator_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    authenticator = auth.Authenticator()
    session = types.SimpleNamespace()

    result = authenticator(
        None,
        session,
        None,
        "CRAM",
        types.SimpleNamespace(login=b"u", password=b"p")
    )
    assert result.message == constants.AUTH_UNSUPPORTED_MECHANISM

    result = authenticator(None, session, None, "LOGIN", None)
    assert result.message == constants.AUTH_CREDENTIALS_MISSING

    auth_data = types.SimpleNamespace(login=b"\xff", password=b"p")
    result = authenticator(None, session, None, "LOGIN", auth_data)
    assert result.message == constants.AUTH_INVALID_ENCODING

    def raise_value(_):
        raise ValueError("bad username")

    monkeypatch.setattr(auth, "parse_username", raise_value)
    auth_data = types.SimpleNamespace(login=b"u", password=b"p")
    result = authenticator(None, session, None, "LOGIN", auth_data)
    assert result.message == "535 5.7.8 bad username"

    def raise_runtime(_):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth, "parse_username", raise_runtime)
    result = authenticator(None, session, None, "LOGIN", auth_data)
    assert result.message == constants.AUTH_UNEXPECTED_ERROR

    monkeypatch.setattr(auth, "parse_username", lambda _: ("tenant", "client", None))

    def raise_token(*_args, **_kwargs):
        raise RuntimeError("no token")

    monkeypatch.setattr(auth, "get_access_token", raise_token)
    result = authenticator(None, session, None, "LOGIN", auth_data)
    assert result.message == constants.AUTH_FAILED
