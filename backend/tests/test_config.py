import pytest

from app.config import Settings, validate_settings
from app.errors import ConfigurationError


def test_database_and_onlyoffice_defaults(monkeypatch):
    for variable in (
        "DATABASE_URL",
        "ONLYOFFICE_ENABLED",
        "ONLYOFFICE_PUBLIC_URL",
        "ONLYOFFICE_INTERNAL_URL",
        "ONLYOFFICE_API_URL",
        "ONLYOFFICE_JWT_SECRET",
        "ONLYOFFICE_FILE_TOKEN_TTL_SECONDS",
        "ONLYOFFICE_CALLBACK_TOKEN_TTL_SECONDS",
        "ONLYOFFICE_MAX_FILE_BYTES",
        "LOCAL_DECK_FILE_DIR",
    ):
        monkeypatch.delenv(variable, raising=False)

    configured = Settings(_env_file=None)

    assert configured.database_url.startswith("sqlite+aiosqlite:///.data/deck_versions.db")
    assert configured.onlyoffice_public_url == "http://localhost:8080"
    assert configured.onlyoffice_internal_url == "http://onlyoffice"
    assert configured.onlyoffice_api_url == "http://host.docker.internal:8000"
    assert configured.onlyoffice_max_file_bytes == 50_000_000
    assert configured.onlyoffice_callback_token_ttl_seconds == 604_800
    assert configured.local_deck_file_dir == ".data/deck-files"


def test_onlyoffice_requires_jwt_secret_when_enabled(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ONLYOFFICE_ENABLED", raising=False)
    monkeypatch.delenv("ONLYOFFICE_JWT_SECRET", raising=False)

    configured = Settings(
        _env_file=None,
        onlyoffice_enabled=True,
        onlyoffice_jwt_secret="",
    )

    with pytest.raises(ConfigurationError, match="ONLYOFFICE_JWT_SECRET"):
        validate_settings(configured)


def test_onlyoffice_public_url_preserves_virtual_proxy_path():
    configured = Settings(
        _env_file=None,
        onlyoffice_public_url="https://slides.internal.example/onlyoffice",
    )

    assert configured.onlyoffice_public_url.endswith("/onlyoffice")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("storage_provider", "typo"),
        ("deck_version_retention", 0),
        ("deck_version_retention", 101),
        ("onlyoffice_max_file_bytes", 0),
        ("onlyoffice_file_token_ttl_seconds", 0),
        ("onlyoffice_callback_token_ttl_seconds", 0),
    ],
)
def test_deck_version_settings_reject_invalid_values(field, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})
