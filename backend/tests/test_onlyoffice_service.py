import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
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
        "forcesave": False,
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


@pytest.mark.asyncio
async def test_force_save_sends_signed_command_for_active_editor_key():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"error": 0, "key": "deck-1-version-1"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = OnlyOfficeService(
        public_url="http://localhost:8080",
        api_base_url="http://api:8000",
        internal_url="http://onlyoffice:80",
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        download_client=client,
        now=lambda: NOW,
    )

    await service.force_save(
        document_key="deck-1-version-1",
        userdata="save-request-1",
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/command"
    assert request.url.params["shardkey"] == "deck-1-version-1"
    command = json.loads(request.content)
    assert command["c"] == "forcesave"
    assert command["key"] == "deck-1-version-1"
    assert command["userdata"] == "save-request-1"
    assert jwt.decode(command["token"], SECRET, algorithms=["HS256"]) == {
        "c": "forcesave",
        "key": "deck-1-version-1",
        "userdata": "save-request-1",
    }
    await client.aclose()


def test_editor_config_uses_separate_content_and_callback_lifetimes():
    current_time = NOW
    service = OnlyOfficeService(
        public_url="http://localhost:8080",
        api_base_url="http://api:8000",
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        callback_token_ttl_seconds=604_800,
        now=lambda: current_time,
    )
    result = service.build_editor_config(
        deck=_deck(), user_id="alice", user_name="Alice"
    )
    content_token = parse_qs(urlsplit(result.config["document"]["url"]).query)[
        "token"
    ][0]
    callback_token = parse_qs(
        urlsplit(result.config["editorConfig"]["callbackUrl"]).query
    )["token"][0]

    current_time = NOW + timedelta(minutes=6)
    with pytest.raises(OnlyOfficeTokenError, match="expired"):
        service.decode_scoped_token(
            content_token,
            purpose="content",
            deck_id="deck-1",
            version_id="version-1",
            subject="alice",
        )
    service.decode_scoped_token(
        callback_token,
        purpose="callback",
        deck_id="deck-1",
        version_id="version-1",
        subject="alice",
    )

    current_time = NOW + timedelta(days=7)
    with pytest.raises(OnlyOfficeTokenError, match="expired"):
        service.decode_scoped_token(
            callback_token,
            purpose="callback",
            deck_id="deck-1",
            version_id="version-1",
            subject="alice",
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


def test_editor_config_preserves_normalized_document_server_proxy_path():
    proxied = OnlyOfficeService(
        public_url="https://slides.internal.example/onlyoffice/",
        api_base_url="http://api:8000",
        jwt_secret=SECRET,
        file_token_ttl_seconds=300,
        now=lambda: NOW,
    )

    config = proxied.build_editor_config(
        deck=_deck(), user_id="alice", user_name="Alice"
    )

    assert config.document_server_url == (
        "https://slides.internal.example/onlyoffice"
    )


@pytest.mark.parametrize(
    "public_url",
    [
        "https://slides.internal.example/onlyoffice?next=evil",
        "https://slides.internal.example/onlyoffice#fragment",
        "https://user:password@slides.internal.example/onlyoffice",
        "https://slides.internal.example/onlyoffice/../admin",
        "https://slides.internal.example/onlyoffice%2f..%2fadmin",
        "https://slides.internal.example/onlyoffice%252f..%252fadmin",
    ],
)
def test_editor_config_rejects_unsafe_document_server_proxy_paths(public_url: str):
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
    expected_ttl = 604_800 if purpose == "callback" else 300

    assert claims == {
        "sub": "alice",
        "deck_id": "deck-1",
        "version_id": "version-1",
        "purpose": purpose,
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(seconds=expected_ttl)).timestamp()),
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
