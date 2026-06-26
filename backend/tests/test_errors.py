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
