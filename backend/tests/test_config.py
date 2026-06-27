import pytest

from app.config import Settings, validate_settings
from app.errors import ConfigurationError


def test_database_and_onlyoffice_defaults():
    configured = Settings(_env_file=None)

    assert configured.database_url.startswith("sqlite+aiosqlite:///.data/deck_versions.db")
    assert configured.onlyoffice_public_url == "http://localhost:8080"
    assert configured.onlyoffice_internal_url == "http://onlyoffice"
    assert configured.onlyoffice_max_file_bytes == 50_000_000


def test_onlyoffice_requires_jwt_secret_when_enabled():
    configured = Settings(
        _env_file=None,
        onlyoffice_enabled=True,
        onlyoffice_jwt_secret="",
    )

    with pytest.raises(ConfigurationError, match="ONLYOFFICE_JWT_SECRET"):
        validate_settings(configured)
