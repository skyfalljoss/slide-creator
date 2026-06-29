from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode, urlsplit

import jwt

from app.models.schemas import OnlyOfficeEditorConfig
from app.services.platform.deck_repository import DeckRecord


TokenPurpose = Literal["content", "callback"]
_TOKEN_ALGORITHM = "HS256"
_TOKEN_CLAIMS = ("sub", "deck_id", "version_id", "purpose", "iat", "exp")


class OnlyOfficeTokenError(ValueError):
    """A scoped ONLYOFFICE token is invalid or does not match its resource."""


class OnlyOfficeConfigurationError(ValueError):
    """An ONLYOFFICE origin is missing or unsafe for signed configuration."""


def _validated_http_origin(value: str, label: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise OnlyOfficeConfigurationError(f"ONLYOFFICE {label} is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or any(character.isspace() for character in value)
    ):
        raise OnlyOfficeConfigurationError(f"ONLYOFFICE {label} is invalid")
    if port is not None and not 1 <= port <= 65535:
        raise OnlyOfficeConfigurationError(f"ONLYOFFICE {label} is invalid")
    return value.rstrip("/")


class OnlyOfficeService:
    def __init__(
        self,
        *,
        public_url: str,
        api_base_url: str,
        jwt_secret: str,
        file_token_ttl_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not jwt_secret:
            raise ValueError("ONLYOFFICE JWT secret must not be empty")
        if file_token_ttl_seconds <= 0:
            raise ValueError("ONLYOFFICE token lifetime must be positive")
        self._public_url = public_url
        self._api_base_url = api_base_url
        self._jwt_secret = jwt_secret
        self._file_token_ttl_seconds = file_token_ttl_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create_scoped_token(
        self,
        *,
        subject: str,
        deck_id: str,
        version_id: str,
        purpose: TokenPurpose,
    ) -> str:
        if purpose not in {"content", "callback"}:
            raise ValueError("Unsupported ONLYOFFICE token purpose")
        if not subject or not deck_id or not version_id:
            raise ValueError("ONLYOFFICE token identity must not be empty")
        issued_at = self._utc_now()
        payload = {
            "sub": subject,
            "deck_id": deck_id,
            "version_id": version_id,
            "purpose": purpose,
            "iat": int(issued_at.timestamp()),
            "exp": int(
                (issued_at + timedelta(seconds=self._file_token_ttl_seconds)).timestamp()
            ),
        }
        return jwt.encode(payload, self._jwt_secret, algorithm=_TOKEN_ALGORITHM)

    def decode_scoped_token(
        self,
        token: str,
        *,
        purpose: TokenPurpose,
        deck_id: str,
        version_id: str | None = None,
        subject: str | None = None,
    ) -> dict[str, str | int]:
        try:
            claims = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[_TOKEN_ALGORITHM],
                options={
                    "require": list(_TOKEN_CLAIMS),
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
        except jwt.InvalidTokenError as exc:
            raise OnlyOfficeTokenError("ONLYOFFICE token is invalid") from exc

        for claim in ("sub", "deck_id", "version_id", "purpose"):
            if not isinstance(claims.get(claim), str) or not claims[claim]:
                raise OnlyOfficeTokenError(f"ONLYOFFICE token {claim} is invalid")
        for claim in ("iat", "exp"):
            value = claims.get(claim)
            if not isinstance(value, int) or isinstance(value, bool):
                raise OnlyOfficeTokenError(f"ONLYOFFICE token {claim} is invalid")

        now_timestamp = int(self._utc_now().timestamp())
        if claims["exp"] <= now_timestamp:
            raise OnlyOfficeTokenError("ONLYOFFICE token has expired")
        if claims["iat"] > now_timestamp:
            raise OnlyOfficeTokenError("ONLYOFFICE token issued-at time is invalid")
        if claims["purpose"] != purpose:
            raise OnlyOfficeTokenError("ONLYOFFICE token purpose does not match")
        if claims["deck_id"] != deck_id:
            raise OnlyOfficeTokenError("ONLYOFFICE token deck does not match")
        if version_id is not None and claims["version_id"] != version_id:
            raise OnlyOfficeTokenError("ONLYOFFICE token version does not match")
        if subject is not None and claims["sub"] != subject:
            raise OnlyOfficeTokenError("ONLYOFFICE token subject does not match")
        return claims

    def build_editor_config(
        self,
        *,
        deck: DeckRecord,
        user_id: str,
        user_name: str,
    ) -> OnlyOfficeEditorConfig:
        version = deck.current_version
        if version is None or deck.current_version_id != version.id:
            raise ValueError("Deck does not have a current version")

        content_token = self.create_scoped_token(
            subject=user_id,
            deck_id=deck.id,
            version_id=version.id,
            purpose="content",
        )
        callback_token = self.create_scoped_token(
            subject=user_id,
            deck_id=deck.id,
            version_id=version.id,
            purpose="callback",
        )
        public_url = _validated_http_origin(self._public_url, "public URL")
        api_base_url = _validated_http_origin(self._api_base_url, "API URL")
        content_url = self._resource_url(
            api_base_url, deck.id, "content", content_token
        )
        callback_url = self._resource_url(
            api_base_url, deck.id, "callback", callback_token
        )
        config: dict[str, object] = {
            "document": {
                "fileType": "pptx",
                "key": f"{deck.id}-{version.id}",
                "title": f"{deck.name}.pptx",
                "url": content_url,
                "permissions": {"edit": True, "download": True, "print": True},
            },
            "documentType": "slide",
            "editorConfig": {
                "mode": "edit",
                "callbackUrl": callback_url,
                "user": {"id": user_id, "name": user_name},
                "customization": {"autosave": True, "forcesave": True},
            },
        }
        config["token"] = jwt.encode(
            config, self._jwt_secret, algorithm=_TOKEN_ALGORITHM
        )
        return OnlyOfficeEditorConfig(
            document_server_url=public_url,
            config=config,
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _resource_url(
        api_base_url: str, deck_id: str, action: str, token: str
    ) -> str:
        return (
            f"{api_base_url}/api/v1/decks/{deck_id}/{action}?"
            f"{urlencode({'token': token})}"
        )
