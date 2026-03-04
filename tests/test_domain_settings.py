import pytest

import domain_settings


def patch_table(monkeypatch: pytest.MonkeyPatch, entities: list[dict] | None) -> None:
    monkeypatch.setattr(domain_settings, "AZURE_TABLES_URL", "https://example.com/table")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def query_entities(self, query_filter):
            return iter(entities or [])

    monkeypatch.setattr(domain_settings, "DefaultAzureCredential", lambda: object())
    monkeypatch.setattr(
        domain_settings.TableClient,
        "from_table_url",
        lambda *args, **kwargs: FakeClient()
    )


def test_lookup_domain_settings_missing_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domain_settings, "AZURE_TABLES_URL", None)
    assert domain_settings.lookup_domain_settings("example.com") is None

    patch_table(monkeypatch, [])
    assert domain_settings.lookup_domain_settings("example.com") is None


def test_lookup_domain_settings_values(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_table(
        monkeypatch,
        [
            {
                "from_remap": "true",
                "from_remap_addresses": "a@example.com, B@example.com",
                "failure_notification": "ops@example.com",
            }
        ],
    )

    settings = domain_settings.lookup_domain_settings("example.com")
    assert settings is not None
    assert settings.from_remap is True
    assert settings.remap_addresses == {"a@example.com", "b@example.com"}
    assert settings.failure_notification == "ops@example.com"


def test_domain_settings_query_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(domain_settings, "AZURE_TABLES_URL", "https://example.com/table")

    def raise_client(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(domain_settings.TableClient, "from_table_url", raise_client)
    assert domain_settings.lookup_domain_settings("example.com") is None


def test_domain_settings_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_table(
        monkeypatch,
        [
            {
                "from_remap": "false",
                "from_remap_addresses": None,
                "failure_notification": "not-an-email",
            }
        ],
    )

    settings = domain_settings.lookup_domain_settings("example.com")
    assert settings is not None
    assert settings.from_remap is False
    assert settings.remap_addresses == set()
    assert settings.failure_notification is None
