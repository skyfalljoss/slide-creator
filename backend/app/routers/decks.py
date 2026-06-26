from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_deck_store
from app.models.schemas import (
    DeckDetail,
    DeleteDeckResponse,
    ListDecksResponse,
    SaveDeckRequest,
    SaveDeckResponse,
    UpdateDeckRequest,
    UpdateDeckResponse,
)
from app.services.platform.deck_store import DeckStore

router = APIRouter()


@router.get("/decks", response_model=ListDecksResponse)
async def list_decks(
    q: str = Query(default="", max_length=200),
    deck_type: str = Query(default=""),
    sort: str = Query(default="newest", pattern="^(newest|oldest|name)$"),
    store: DeckStore = Depends(get_deck_store),
):
    rows = await store.list_all(search=q, deck_type=deck_type, sort=sort)
    summaries = [
        {**r, "deck_type": r.get("deck_type", "unknown")} for r in rows
    ]
    return ListDecksResponse(decks=summaries)


@router.get("/decks/{deck_id}", response_model=DeckDetail)
async def get_deck(
    deck_id: str,
    store: DeckStore = Depends(get_deck_store),
):
    deck = await store.get(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckDetail(**deck)


@router.post("/decks", response_model=SaveDeckResponse, status_code=200)
async def save_deck(
    req: SaveDeckRequest,
    store: DeckStore = Depends(get_deck_store),
):
    deck_id = await store.create(
        name=req.name,
        deck_type=req.deck_type,
        theme=req.theme,
        aspect_ratio=req.aspect_ratio,
        slides=req.slides,
        thumbnail_b64=req.thumbnail_b64,
    )
    deck = await store.get(deck_id)
    return SaveDeckResponse(
        id=deck_id,
        name=req.name,
        created_at=deck["created_at"] if deck else "",
    )


@router.put("/decks/{deck_id}", response_model=UpdateDeckResponse)
async def update_deck(
    deck_id: str,
    req: UpdateDeckRequest,
    store: DeckStore = Depends(get_deck_store),
):
    if req.name is None and req.slides is None:
        raise HTTPException(status_code=400, detail="At least one of name or slides must be provided")

    success = await store.update(
        deck_id=deck_id,
        name=req.name,
        slides=req.slides,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Deck not found")

    deck = await store.get(deck_id)
    return UpdateDeckResponse(
        updated_at=deck["updated_at"] if deck else "",
    )


@router.delete("/decks/{deck_id}", response_model=DeleteDeckResponse)
async def delete_deck(
    deck_id: str,
    store: DeckStore = Depends(get_deck_store),
):
    success = await store.delete(deck_id)
    if not success:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeleteDeckResponse(ok=True)
