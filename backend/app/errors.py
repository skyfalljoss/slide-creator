class SlideForgeError(Exception):
    code: str = "SFE_000"
    message: str = ""

    def __init__(self, code: str | None = None, message: str = "") -> None:
        if code is not None:
            self.code = code
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigurationError(SlideForgeError):
    code = "CONFIG_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class DlpViolationError(SlideForgeError):
    code = "DLP_VIOLATION"

    def __init__(self, terms: list[str]) -> None:
        message = f"Prompt contains prohibited terms: {', '.join(terms)}"
        super().__init__(message=message)


class SessionNotFoundError(SlideForgeError):
    code = "SESSION_NOT_FOUND"

    def __init__(self, session_id: str) -> None:
        message = f"Session not found or expired: {session_id}"
        super().__init__(message=message)


class StorageError(SlideForgeError):
    code = "STORAGE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class StorageUploadError(StorageError):
    code = "STORAGE_UPLOAD_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)


class GenerationError(SlideForgeError):
    code = "GENERATION_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message=message)
