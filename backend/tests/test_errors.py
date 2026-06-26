from app.config import Settings
from app.errors import (
    SlideForgeError,
    ConfigurationError,
    DlpViolationError,
    SessionNotFoundError,
    StorageError,
    GenerationError,
    StorageUploadError,
)


def test_base_error_has_code_and_message():
    err = SlideForgeError("SFE_000", "something broke")
    assert err.code == "SFE_000"
    assert err.message == "something broke"
    assert str(err) == "[SFE_000] something broke"


def test_configuration_error_code():
    err = ConfigurationError("missing API key")
    assert err.code == "CONFIG_ERROR"
    assert err.message == "missing API key"


def test_dlp_violation_error_code():
    err = DlpViolationError(terms=["guarantee returns", "risk-free"])
    assert err.code == "DLP_VIOLATION"
    assert "guarantee returns" in err.message
    assert "risk-free" in err.message


def test_session_not_found_error_code():
    err = SessionNotFoundError("abc-123")
    assert err.code == "SESSION_NOT_FOUND"
    assert "abc-123" in err.message


def test_storage_error_code():
    err = StorageError("disk full")
    assert err.code == "STORAGE_ERROR"
    assert err.message == "disk full"


def test_generation_error_code():
    err = GenerationError("model timeout")
    assert err.code == "GENERATION_ERROR"
    assert err.message == "model timeout"


def test_storage_upload_error_code():
    err = StorageUploadError("upload failed")
    assert err.code == "STORAGE_UPLOAD_ERROR"
    assert err.message == "upload failed"


def test_all_errors_inherit_from_base():
    assert issubclass(ConfigurationError, SlideForgeError)
    assert issubclass(DlpViolationError, SlideForgeError)
    assert issubclass(SessionNotFoundError, SlideForgeError)
    assert issubclass(StorageError, SlideForgeError)
    assert issubclass(GenerationError, SlideForgeError)
    assert issubclass(StorageUploadError, StorageError)


def test_dlp_violation_with_empty_terms():
    err = DlpViolationError(terms=[])
    assert err.code == "DLP_VIOLATION"
    assert err.message == "Prompt contains prohibited terms: "


def test_error_handler_returns_structured_json():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.middleware.error_handler import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/fail-dlp")
    def fail_dlp():
        raise DlpViolationError(terms=["risk-free"])

    @app.get("/fail-session")
    def fail_session():
        raise SessionNotFoundError("abc-123")

    @app.get("/fail-config")
    def fail_config():
        raise ConfigurationError("missing key")

    @app.get("/fail-generation")
    def fail_generation():
        raise GenerationError("model timeout")

    @app.get("/fail-generic")
    def fail_generic():
        raise RuntimeError("oops")

    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/fail-dlp")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "DLP_VIOLATION"
    assert "risk-free" in body["error"]["message"]

    resp = client.get("/fail-session")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SESSION_NOT_FOUND"

    resp = client.get("/fail-config")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "CONFIG_ERROR"

    resp = client.get("/fail-generation")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "GENERATION_ERROR"

    resp = client.get("/fail-generic")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"


def test_config_session_provider_defaults_to_local():
    s = Settings()
    assert s.session_provider == "local"


def test_config_rate_limit_defaults():
    s = Settings()
    assert s.rate_limit_generate == "10/minute"
    assert s.rate_limit_export == "30/minute"
    assert s.rate_limit_uploads == "60/minute"


def test_config_structlog_defaults():
    s = Settings()
    assert s.log_format == "console"
