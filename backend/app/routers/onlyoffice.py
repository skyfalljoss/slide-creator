import asyncio

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.dependencies import (
    get_deck_file_storage,
    get_deck_repository,
    get_deck_version_service,
    get_onlyoffice_service,
)
from app.models.schemas import OnlyOfficeCallback, OnlyOfficeEditorConfig
from app.services.platform.auth import get_user_id
from app.services.platform.deck_files import (
    DECK_STREAM_CHUNK_SIZE,
    DeckFileStream,
    DeckFileStorage,
    PPTX_CONTENT_TYPE,
)
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.deck_versions import DeckVersionService
from app.services.platform.onlyoffice import (
    OnlyOfficeAuthorizationError,
    OnlyOfficeService,
    OnlyOfficeTokenError,
)


router = APIRouter()
logger = structlog.get_logger(__name__)


class _DeckStreamingResponse(StreamingResponse):
    def __init__(self, *args, deck_stream: DeckFileStream, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._deck_stream = deck_stream

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._deck_stream.aclose()


@router.get(
    "/decks/{deck_id}/editor-config", response_model=OnlyOfficeEditorConfig
)
async def get_editor_config(
    deck_id: str,
    request: Request,
    repository: DeckRepository = Depends(get_deck_repository),
    onlyoffice: OnlyOfficeService = Depends(get_onlyoffice_service),
) -> OnlyOfficeEditorConfig:
    user_id = get_user_id(request)
    deck = await repository.get(deck_id, user_id)
    if deck is None or deck.current_version is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    user_name = request.headers.get("x-user-name", "").strip() or user_id
    return onlyoffice.build_editor_config(
        deck=deck,
        user_id=user_id,
        user_name=user_name,
    )


@router.get("/decks/{deck_id}/content")
async def get_deck_content(
    deck_id: str,
    token: str = Query(min_length=1),
    repository: DeckRepository = Depends(get_deck_repository),
    storage: DeckFileStorage = Depends(get_deck_file_storage),
    onlyoffice: OnlyOfficeService = Depends(get_onlyoffice_service),
) -> StreamingResponse:
    try:
        claims = onlyoffice.decode_scoped_token(
            token,
            purpose="content",
            deck_id=deck_id,
        )
        subject = str(claims["sub"])
        deck = await repository.get(deck_id, subject)
        if deck is None or deck.current_version is None:
            raise HTTPException(status_code=404, detail="Deck not found")
        onlyoffice.decode_scoped_token(
            token,
            purpose="content",
            deck_id=deck_id,
            version_id=deck.current_version.id,
            subject=deck.owner_id,
        )
    except OnlyOfficeTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid content token") from exc

    try:
        stream = await storage.open_stream(
            deck.current_version.storage_key,
            chunk_size=DECK_STREAM_CHUNK_SIZE,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Deck content not found") from exc

    async def stream_content():
        async for chunk in stream:
            yield chunk

    return _DeckStreamingResponse(
        stream_content(),
        deck_stream=stream,
        media_type=PPTX_CONTENT_TYPE,
        headers={
            "Content-Disposition": "inline; filename=deck.pptx",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/decks/{deck_id}/callback")
async def handle_onlyoffice_callback(
    deck_id: str,
    body: OnlyOfficeCallback,
    token: str = Query(min_length=1),
    authorization: str | None = Header(default=None),
    onlyoffice: OnlyOfficeService = Depends(get_onlyoffice_service),
    versions: DeckVersionService = Depends(get_deck_version_service),
) -> dict[str, int]:
    try:
        claims = onlyoffice.decode_scoped_token(
            token,
            purpose="callback",
            deck_id=deck_id,
        )
        onlyoffice.validate_callback_authorization(authorization, body)
    except (OnlyOfficeTokenError, OnlyOfficeAuthorizationError) as exc:
        raise HTTPException(status_code=401, detail="Invalid callback authentication") from exc

    if body.status in {1, 4}:
        return {"error": 0}
    if body.status in {3, 7}:
        return {"error": 1}
    if body.status not in {2, 6} or body.url is None:
        return {"error": 1}

    owner_id = str(claims["sub"])
    base_version_id = str(claims["version_id"])
    try:
        content = await onlyoffice.download_callback_file(body.url)
        await versions.save_edited_version(
            deck_id=deck_id,
            owner_id=owner_id,
            content=content,
            base_version_id=base_version_id,
            callback_key=f"{body.key}:{body.status}:{body.userdata or ''}",
            created_by=owner_id,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await logger.aerror(
            "onlyoffice_callback_failed",
            deck_id=deck_id,
            status=body.status,
            failure_type=type(exc).__name__,
        )
        return {"error": 1}
    return {"error": 0}
