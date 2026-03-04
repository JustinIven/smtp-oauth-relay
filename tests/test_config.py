import pytest

import config


@pytest.mark.parametrize(
    ("value", "expected", "raises"),
    [
        ("yes", "yes", None),
        ("bad", None, ValueError),
    ],
)
def test_load_env_validation(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    expected: str | None,
    raises: type[Exception] | None,
) -> None:
    monkeypatch.setenv("TEST_ENV", value)
    if raises:
        with pytest.raises(raises):
            config.load_env("TEST_ENV", valid_values=["good"], sanitize=str.lower)
    else:
        assert config.load_env("TEST_ENV", sanitize=str.lower) == expected


def test_load_env_convert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ENV_NUM", "5")
    assert config.load_env("TEST_ENV_NUM", convert=int) == 5
