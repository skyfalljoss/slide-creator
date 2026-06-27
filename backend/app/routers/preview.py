from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_deck_store, get_preview_service
from app.models.schemas import SlidePreviewResponse
from app.services.platform.deck_store import DeckStore
from app.services.presentation.pptx_preview import PreviewRendererUnavailable, PptxPreviewService

router = APIRouter()


@router.get("/decks/{deck_id}/preview", response_model=SlidePreviewResponse)
async def get_deck_slide_preview(
    deck_id: str,
    slide_index: int = Query(default=1, ge=1),
    store: DeckStore = Depends(get_deck_store),
    preview_service: PptxPreviewService = Depends(get_preview_service),
) -> SlidePreviewResponse:
    deck = await store.get(deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    try:
        return preview_service.render_deck_slide(
            deck_id=deck_id,
            slides=deck["slides"],
            deck_type=deck["deck_type"],
            theme=deck["theme"],
            aspect_ratio=deck["aspect_ratio"],
            slide_index=slide_index,
            updated_at=deck.get("updated_at"),
        )
    except IndexError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PreviewRendererUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
