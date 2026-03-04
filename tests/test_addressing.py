import pytest

import addressing
import domain_settings


@pytest.fixture
def domain_settings_fixture() -> domain_settings.DomainSettings:
    return domain_settings.DomainSettings(
        from_remap=False,
        remap_addresses=set(),
        failure_notification="ops@example.com",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", None),
        ("<>", None),
        ("not-an-email", None),
        ("User <user@example.com>", "user@example.com"),
    ],
)
def test_parse_email_address(value: str, expected: str | None) -> None:
    assert addressing.parse_email_address(value) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("from <user@example.com>",), "example.com"),
        ((None, "nope"), None),
        (("User <USER@EXAMPLE.COM>",), "example.com"),
        ((None, "not an address"), None),
    ],
)
def test_extract_domain_hint(values: tuple[str | None, ...], expected: str | None) -> None:
    assert addressing.extract_domain_hint(*values) == expected


def test_failback_env_var_name() -> None:
    assert addressing.failback_env_var_name("example.com") == "EXAMPLE_COM_FROM_FAILBACK"


def test_lookup_failback_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_COM_FROM_FAILBACK", "noreply@example.com")
    assert addressing.lookup_failback_address("example.com") == "noreply@example.com"
    assert addressing.lookup_failback_address(None) is None


def test_failure_notification_env_var_name() -> None:
    assert (
        addressing.failure_notification_env_var_name("example.com")
        == "EXAMPLE_COM_FAILURE_NOTIFICATION"
    )


def test_lookup_failure_notification_address(monkeypatch: pytest.MonkeyPatch) -> None:
    domain = "example.com"
    monkeypatch.setenv("EXAMPLE_COM_FAILURE_NOTIFICATION", "alert@example.com")
    assert addressing.lookup_failure_notification_address(domain, None) == "alert@example.com"


def test_lookup_failure_notification_address_fallback(
    monkeypatch: pytest.MonkeyPatch,
    domain_settings_fixture: domain_settings.DomainSettings,
) -> None:
    assert (
        addressing.lookup_failure_notification_address("example.com", domain_settings_fixture)
        == "ops@example.com"
    )
    monkeypatch.setenv("EXAMPLE_COM_FAILURE_NOTIFICATION", "env@example.com")
    assert (
        addressing.lookup_failure_notification_address("example.com", domain_settings_fixture)
        == "env@example.com"
    )


def test_to_failback_env_var_name() -> None:
    assert addressing.to_failback_env_var_name("example.com") == "EXAMPLE_COM_TO_FAILBACK"


def test_lookup_to_failback_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_COM_TO_FAILBACK", "postmaster@example.com")
    assert addressing.lookup_to_failback_address("example.com") == "postmaster@example.com"
    assert addressing.lookup_to_failback_address(None) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (None, None),
        (" yes ", True),
        ("0", False),
        ("maybe", None),
    ],
)
def test_normalize_bool_variants(value: object, expected: bool | None) -> None:
    assert addressing.normalize_bool(value) is expected


@pytest.mark.parametrize(
    ("address", "allow_null", "expected"),
    [
        ("<>", True, True),
        ("user@example.com", True, True),
        ("user@[127.0.0.1]", False, True),
        ("not-an-email", False, False),
        ("user@@example.com", False, False),
        ("user<@example.com", False, False),
        ("a" * 65 + "@example.com", False, False),
        ("user@" + ("b" * 64) + ".com", False, False),
    ],
)
def test_is_valid_smtp_mailbox_variants(
    address: str,
    allow_null: bool,
    expected: bool,
) -> None:
    assert addressing.is_valid_smtp_mailbox(address, allow_null=allow_null) is expected
