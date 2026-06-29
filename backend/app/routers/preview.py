from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dependencies import get_deck_repository, get_preview_service
from app.models.schemas import SlidePreviewResponse
from app.services.platform.auth import get_user_id
from app.services.platform.deck_repository import DeckRepository
from app.services.presentation.pptx_preview import PreviewRendererUnavailable, PptxPreviewService

router = APIRouter()


@router.get("/decks/{deck_id}/preview", response_model=SlidePreviewResponse)
async def get_deck_slide_preview(
    deck_id: str,
    request: Request,
    slide_index: int = Query(default=1, ge=1),
    repository: DeckRepository = Depends(get_deck_repository),
    preview_service: PptxPreviewService = Depends(get_preview_service),
) -> SlidePreviewResponse:
    deck = await repository.get(deck_id, get_user_id(request))
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")
    payload = deck.generation_payload
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        raise HTTPException(status_code=404, detail="Deck slides not found")

    try:
        return preview_service.render_deck_slide(
            deck_id=deck_id,
            slides=slides,
            deck_type=deck.deck_type,
            theme=deck.theme,
            aspect_ratio=deck.aspect_ratio,
            slide_index=slide_index,
            updated_at=deck.updated_at.isoformat(),
        )
    except IndexError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PreviewRendererUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
