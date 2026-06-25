from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.schemas import RefineRequest, RefineResponse
from app.services.auth import get_user_id
from app.services import providers
from app.services.session import get_session, update_slide
from app.services.slide_images import SlideImageResolver

router = APIRouter()
image_resolver = SlideImageResolver()


@router.post("/refine")
async def refine(req: RefineRequest, request: Request) -> RefineResponse:
    dlp = providers.get_dlp_service()
    violations = dlp.scan_prompt(req.instruction)
    if violations:
        raise HTTPException(
            status_code=400,
            detail=f"Instruction contains prohibited terms: {', '.join(violations)}",
        )

    session = get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    current_slide = None
    for s in session["slides"]:
        if s.index == req.slide_index:
            current_slide = s
            break

    if current_slide is None:
        raise HTTPException(status_code=404, detail="Slide not found")

    gemini = providers.get_generator_service()
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
        raise HTTPException(
            status_code=400,
            detail=f"Refined content contains prohibited terms: {', '.join(slide_violations)}",
        )
    update_slide(req.session_id, updated)
    audit = providers.get_audit_service()
    audit.record(
        action="refine",
        session_id=req.session_id,
        deck_type=session["deck_type"],
        slide_count=len(session["slides"]),
        slide_index=req.slide_index,
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return RefineResponse(slide=updated)
