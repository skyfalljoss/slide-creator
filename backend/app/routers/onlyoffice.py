from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.dependencies import (
    get_deck_file_storage,
    get_deck_repository,
    get_onlyoffice_service,
)
from app.models.schemas import OnlyOfficeEditorConfig
from app.services.platform.auth import get_user_id
from app.services.platform.deck_files import DeckFileStorage, PPTX_CONTENT_TYPE
from app.services.platform.deck_repository import DeckRepository
from app.services.platform.onlyoffice import OnlyOfficeService, OnlyOfficeTokenError


router = APIRouter()


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
        request_base_url=str(request.base_url),
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
        content = await storage.read(deck.current_version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Deck content not found") from exc

    async def stream_content() -> AsyncIterator[bytes]:
        yield content

    return StreamingResponse(
        stream_content(),
        media_type=PPTX_CONTENT_TYPE,
        headers={
            "Content-Disposition": "inline; filename=deck.pptx",
            "Cache-Control": "private, no-store",
        },
    )
