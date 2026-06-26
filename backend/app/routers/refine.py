from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.dependencies import get_audit_service, get_dlp_service, get_generator_service, get_session_store
from app.errors import DlpViolationError, SessionNotFoundError
from app.middleware.rate_limit import limiter
from app.models.schemas import RefineRequest, RefineResponse
from app.services.platform.auth import get_user_id
from app.services.platform.session import SessionStore
from app.services.platform.dlp import DlpService
from app.services.generation.gemini import GeminiService
from app.services.media.slide_images import SlideImageResolver

router = APIRouter()
image_resolver = SlideImageResolver()


@router.post("/refine")
@limiter.limit(settings.rate_limit_generate)
async def refine(
    req: RefineRequest,
    request: Request,
    dlp: DlpService = Depends(get_dlp_service),
    gemini: GeminiService = Depends(get_generator_service),
    session_store: SessionStore = Depends(get_session_store),
) -> RefineResponse:
    violations = dlp.scan_prompt(req.instruction)
    if violations:
        raise DlpViolationError(terms=violations)

    session = session_store.get(req.session_id)
    if session is None:
        raise SessionNotFoundError(req.session_id)

    current_slide = None
    for s in session["slides"]:
        if s.index == req.slide_index:
            current_slide = s
            break

    if current_slide is None:
        raise SessionNotFoundError(req.session_id)

    updated = await gemini.refine(req, current_slide)
    if updated.kicker is None:
        updated.kicker = current_slide.kicker
    if updated.subtitle is None:
        updated.subtitle = current_slide.subtitle
    if updated.variant is None:
        updated.variant = current_slide.variant
    if updated.blocks is None:
        updated.blocks = current_slide.blocks
    updated.chart_data = current_slide.chart_data
    updated.chart_audit = current_slide.chart_audit
    if updated.chart_recommendation is None:
        updated.chart_recommendation = current_slide.chart_recommendation
    if updated.image_prompt is None:
        updated.image_prompt = current_slide.image_prompt
    if updated.image_query is None:
        updated.image_query = current_slide.image_query
    if updated.image_b64 is None:
        updated.image_b64 = current_slide.image_b64

    if image_resolver.needs_image(updated):
        img_b64 = await image_resolver.resolve(updated)
        if img_b64:
            updated.image_b64 = img_b64

    slide_violations = dlp.scan_slide(updated)
    if slide_violations:
        raise DlpViolationError(terms=slide_violations)

    session_store.update_slide(req.session_id, updated)
    audit = get_audit_service()
    audit.record(
        action="refine",
        session_id=req.session_id,
        deck_type=session.get("deck_type") or "unknown",
        slide_count=len(session["slides"]),
        slide_index=req.slide_index,
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return RefineResponse(slide=updated)
