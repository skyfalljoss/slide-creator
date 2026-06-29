from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.services.platform.deck_repository import DeckRecord, DeckVersionRecord
from app.services.platform.onlyoffice import (
    OnlyOfficeConfigurationError,
    OnlyOfficeService,
    OnlyOfficeTokenError,
)


NOW = datetime(2030, 6, 26, 12, 0, tzinfo=timezone.utc)
SECRET = "test-secret-with-at-least-thirty-two-bytes"


def _deck() -> DeckRecord:
    version = DeckVersionRecord(
        id="version-1",
        deck_id="deck-1",
        version_number=1,
        storage_key="decks/deck-1/versions/version-1.pptx",
        sha256="a" * 64,
        size_bytes=123,
        source="generated",
        created_by="alice",
        created_at=NOW,
    )
    return DeckRecord(
        id="deck-1",
        owner_id="alice",
        name="Quarterly Review",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        generation_payload=None,
        current_version_id=version.id,
        created_at=NOW,
        updated_at=NOW,
        current_version=version,
    )


@pytest.fixture
def service() -> OnlyOfficeService:
    return OnlyOfficeService(
        public_url="http://localhost:8080/",
        api_base_url="http://api:8000/",
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        now=lambda: NOW,
    )


def test_editor_config_is_signed_for_current_version(service: OnlyOfficeService):
    result = service.build_editor_config(
        deck=_deck(), user_id="alice", user_name="Alice"
    )

    assert result.document_server_url == "http://localhost:8080"
    assert result.config["documentType"] == "slide"
    assert result.config["document"]["fileType"] == "pptx"
    assert result.config["document"]["key"] == "deck-1-version-1"
    assert result.config["document"]["title"] == "Quarterly Review.pptx"
    assert result.config["document"]["permissions"] == {
        "edit": True,
        "download": True,
        "print": True,
    }
    assert result.config["editorConfig"]["customization"] == {
        "autosave": True,
        "forcesave": True,
    }
    signed_config = jwt.decode(
        result.config["token"], SECRET, algorithms=["HS256"]
    )
    assert signed_config["documentType"] == "slide"
    assert signed_config["document"]["url"].startswith(
        "http://api:8000/api/v1/decks/deck-1/content?token="
    )
    assert signed_config["editorConfig"]["callbackUrl"].startswith(
        "http://api:8000/api/v1/decks/deck-1/callback?token="
    )


@pytest.mark.parametrize(
    "api_base_url",
    [
        "",
        "api:8000",
        "ftp://api:8000",
        "http://user:password@api:8000",
        "http://api:8000/prefix",
        "http://api:8000?redirect=evil",
        "http://api:8000#fragment",
    ],
)
def test_editor_config_rejects_missing_or_invalid_trusted_api_origin(
    api_base_url: str,
):
    invalid = OnlyOfficeService(
        public_url="http://localhost:8080",
        api_base_url=api_base_url,
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        now=lambda: NOW,
    )

    with pytest.raises(OnlyOfficeConfigurationError, match="API URL"):
        invalid.build_editor_config(deck=_deck(), user_id="alice", user_name="Alice")


@pytest.mark.parametrize("public_url", ["", "localhost:8080", "file:///tmp/api.js"])
def test_editor_config_rejects_invalid_document_server_origin(public_url: str):
    invalid = OnlyOfficeService(
        public_url=public_url,
        api_base_url="http://api:8000",
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        now=lambda: NOW,
    )

    with pytest.raises(OnlyOfficeConfigurationError, match="public URL"):
        invalid.build_editor_config(deck=_deck(), user_id="alice", user_name="Alice")


@pytest.mark.parametrize("purpose", ["content", "callback"])
def test_scoped_token_contains_required_identity_claims(
    service: OnlyOfficeService, purpose: str
):
    token = service.create_scoped_token(
        subject="alice",
        deck_id="deck-1",
        version_id="version-1",
        purpose=purpose,
    )
    claims = jwt.decode(
        token,
        SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )

    assert claims == {
        "sub": "alice",
        "deck_id": "deck-1",
        "version_id": "version-1",
        "purpose": purpose,
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(seconds=300)).timestamp()),
    }


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"purpose": "callback"}, "purpose"),
        ({"deck_id": "deck-2"}, "deck"),
        ({"version_id": "version-2"}, "version"),
        ({"sub": "bob"}, "subject"),
    ],
)
def test_scoped_token_rejects_wrong_identity(
    service: OnlyOfficeService, changed: dict[str, str], message: str
):
    claims = {
        "sub": "alice",
        "deck_id": "deck-1",
        "version_id": "version-1",
        "purpose": "content",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(seconds=300)).timestamp()),
        **changed,
    }
    token = jwt.encode(claims, SECRET, algorithm="HS256")

    with pytest.raises(OnlyOfficeTokenError, match=message):
        service.decode_scoped_token(
            token,
            purpose="content",
            deck_id="deck-1",
            version_id="version-1",
            subject="alice",
        )


def test_scoped_token_rejects_expired_token(service: OnlyOfficeService):
    claims = {
        "sub": "alice",
        "deck_id": "deck-1",
        "version_id": "version-1",
        "purpose": "content",
        "iat": int((NOW - timedelta(minutes=10)).timestamp()),
        "exp": int((NOW - timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(claims, SECRET, algorithm="HS256")

    with pytest.raises(OnlyOfficeTokenError, match="expired"):
        service.decode_scoped_token(
            token,
            purpose="content",
            deck_id="deck-1",
            version_id="version-1",
            subject="alice",
        )


def test_scoped_token_rejects_wrong_signature(service: OnlyOfficeService):
    token = jwt.encode(
        {
            "sub": "alice",
            "deck_id": "deck-1",
            "version_id": "version-1",
            "purpose": "content",
            "iat": int(NOW.timestamp()),
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        },
        "wrong-secret-with-at-least-thirty-two-bytes",
        algorithm="HS256",
    )

    with pytest.raises(OnlyOfficeTokenError, match="invalid"):
        service.decode_scoped_token(
            token,
            purpose="content",
            deck_id="deck-1",
            version_id="version-1",
            subject="alice",
        )


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sub", 123),
        ("deck_id", ["deck-1"]),
        ("version_id", {"id": "version-1"}),
        ("purpose", True),
        ("iat", "1898164800"),
        ("exp", False),
    ],
)
def test_scoped_token_rejects_malformed_claim_types(
    service: OnlyOfficeService, claim: str, value: object
):
    claims: dict[str, object] = {
        "sub": "alice",
        "deck_id": "deck-1",
        "version_id": "version-1",
        "purpose": "content",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=5)).timestamp()),
    }
    claims[claim] = value
    token = jwt.encode(claims, SECRET, algorithm="HS256")

    expected_message = "invalid" if claim == "sub" else claim
    with pytest.raises(OnlyOfficeTokenError, match=expected_message):
        service.decode_scoped_token(token, purpose="content", deck_id="deck-1")


def test_scoped_token_rejects_future_issued_at(service: OnlyOfficeService):
    token = jwt.encode(
        {
            "sub": "alice",
            "deck_id": "deck-1",
            "version_id": "version-1",
            "purpose": "content",
            "iat": int((NOW + timedelta(seconds=1)).timestamp()),
            "exp": int((NOW + timedelta(minutes=5)).timestamp()),
        },
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(OnlyOfficeTokenError, match="issued-at"):
        service.decode_scoped_token(token, purpose="content", deck_id="deck-1")
