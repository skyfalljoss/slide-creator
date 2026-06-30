import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dependencies import (
    get_deck_file_storage,
    get_deck_repository,
    get_deck_version_service,
)
from app.models.schemas import (
    DeckDetail,
    DeleteDeckResponse,
    ListDecksResponse,
    RenameDeckRequest,
    SaveDeckRequest,
    SaveDeckResponse,
    UpdateDeckRequest,
    UpdateDeckResponse,
)
from app.services.platform.auth import get_user_id
from app.services.platform.deck_files import DeckFileStorage, await_destructive
from app.services.platform.deck_repository import DeckRecord, DeckRepository
from app.services.platform.deck_versions import DeckNotFoundError, DeckVersionService


router = APIRouter()
logger = structlog.get_logger(__name__)


def _slides(deck: DeckRecord) -> list[dict]:
    payload = deck.generation_payload
    slides = payload.get("slides") if isinstance(payload, dict) else None
    return slides if isinstance(slides, list) else []


def _detail(deck: DeckRecord) -> DeckDetail:
    return DeckDetail(
        id=deck.id,
        name=deck.name,
        deck_type=deck.deck_type,
        theme=deck.theme,
        aspect_ratio=deck.aspect_ratio,
        slides=_slides(deck),
        created_at=deck.created_at.isoformat(),
        updated_at=deck.updated_at.isoformat(),
    )


@router.get("/decks", response_model=ListDecksResponse)
async def list_decks(
    request: Request,
    q: str = Query(default="", max_length=200),
    deck_type: str = Query(default=""),
    sort: str = Query(default="newest", pattern="^(newest|oldest|name)$"),
    repository: DeckRepository = Depends(get_deck_repository),
) -> ListDecksResponse:
    rows = await repository.list_all(
        get_user_id(request), search=q, deck_type=deck_type, sort=sort
    )
    return ListDecksResponse(
        decks=[
            {
                "id": row.id,
                "name": row.name,
                "deck_type": row.deck_type,
                "slide_count": row.slide_count,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]
    )


@router.get("/decks/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: str,
    request: Request,
    repository: DeckRepository = Depends(get_deck_repository),
) -> DeckDetail:
    deck = await repository.get(deck_id, get_user_id(request))
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return _detail(deck)


@router.post("/decks", response_model=SaveDeckResponse, status_code=200)
async def save_deck(
    req: SaveDeckRequest,
    request: Request,
    versions: DeckVersionService = Depends(get_deck_version_service),
) -> SaveDeckResponse:
    deck = await versions.create_generated_deck(
        owner_id=get_user_id(request),
        name=req.name,
        deck_type=req.deck_type,
        theme=req.theme,
        aspect_ratio=req.aspect_ratio,
        slides=req.slides,
    )
    return SaveDeckResponse(
        id=deck.id,
        name=deck.name,
        created_at=deck.created_at.isoformat(),
    )


@router.put("/decks/{deck_id}", response_model=UpdateDeckResponse)
async def update_deck(
    deck_id: str,
    req: UpdateDeckRequest,
    request: Request,
    repository: DeckRepository = Depends(get_deck_repository),
    versions: DeckVersionService = Depends(get_deck_version_service),
) -> UpdateDeckResponse:
    if req.name is None and req.slides is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of name or slides must be provided",
        )
    owner_id = get_user_id(request)
    deck = await repository.get(deck_id, owner_id)
    if deck is None or deck.current_version is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    if req.slides is not None:
        try:
            await versions.save_slides_as_version(
                deck_id=deck_id,
                owner_id=owner_id,
                slides=req.slides,
                theme=deck.theme,
                aspect_ratio=deck.aspect_ratio,
                created_by=owner_id,
                name=req.name,
            )
        except DeckNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Deck not found") from exc
    if req.name is not None and req.slides is None:
        if not await repository.rename(deck_id, owner_id, req.name):
            raise HTTPException(status_code=404, detail="Deck not found")

    updated = await repository.get(deck_id, owner_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return UpdateDeckResponse(updated_at=updated.updated_at.isoformat())


@router.patch("/decks/{deck_id}", response_model=DeckDetail)
async def rename_deck(
    deck_id: str,
    body: RenameDeckRequest,
    request: Request,
    repository: DeckRepository = Depends(get_deck_repository),
) -> DeckDetail:
    owner_id = get_user_id(request)
    if not await repository.rename(deck_id, owner_id, body.name):
        raise HTTPException(status_code=404, detail="Deck not found")
    deck = await repository.get(deck_id, owner_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return _detail(deck)


@router.delete("/decks/{deck_id}", response_model=DeleteDeckResponse)
async def delete_deck(
    deck_id: str,
    request: Request,
    repository: DeckRepository = Depends(get_deck_repository),
    storage: DeckFileStorage = Depends(get_deck_file_storage),
) -> DeleteDeckResponse:
    owner_id = get_user_id(request)
    if await repository.get(deck_id, owner_id) is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    keys = await repository.delete(deck_id, owner_id)
    if not keys:
        raise HTTPException(status_code=404, detail="Deck not found")

    for key in keys:
        try:
            async with repository.storage_key_guard(key) as guard_session:
                if await repository.storage_key_referenced(
                    key, session=guard_session
                ):
                    continue
                await await_destructive(storage.delete(key))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await logger.aerror(
                "deck_object_cleanup_failed",
                deck_id=deck_id,
                storage_key=key,
                failure_type=type(exc).__name__,
            )
    return DeleteDeckResponse(ok=True)
