from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Request
from openpyxl.utils.exceptions import InvalidFileException

from app.config import settings
from app.models.schemas import GenerateRequest, GenerateResponse, SlideData
from app.services.auth import get_user_id
from app.services.deck_normalizer import normalize_deck
from app.services.gemini_api import MAX_SCRIPT_SLIDES, SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services import providers
from app.services.session import create_session
from app.services.slide_charts import SlideChartResolver
from app.services.slide_images import SlideImageResolver
from app.services.uploads import UploadService

router = APIRouter()
uploads = UploadService()
chart_resolver = SlideChartResolver()
image_resolver = SlideImageResolver()


@router.post("/generate")
async def generate(req: GenerateRequest, request: Request) -> GenerateResponse:
    dlp = providers.get_dlp_service()
    violations = dlp.scan_prompt(req.prompt)
    if violations:
        raise HTTPException(
            status_code=400,
            detail=f"Prompt contains prohibited terms: {', '.join(violations)}",
        )

    rows: list[dict[str, str]] | None = None
    upload_summary: dict[str, object] | None = None
    if req.file_id:
        try:
            rows = uploads.get_rows(req.file_id)
            upload_summary = uploads.get_ai_summary(req.file_id)
        except (BadZipFile, FileNotFoundError, InvalidFileException, ValueError):
            raise HTTPException(status_code=400, detail="Invalid uploaded file") from None

    gemini = providers.get_generator_service()
    slides = await gemini.generate(req, chart_data=None, upload_summary=upload_summary)
    chart_resolver.attach(slides=slides, rows=rows, upload_summary=upload_summary)
    slides = normalize_deck(slides, max_count=_max_slide_count(req))

    await _resolve_slide_images(slides)

    flagged = dlp.scan_slides(slides)
    if flagged:
        terms = sorted({term for item in flagged for term in item["violations"]})
        raise HTTPException(
            status_code=400,
            detail=f"Generated content contains prohibited terms: {', '.join(terms)}",
        )
    session_id = create_session(slides, req.deck_type, req.theme, req.aspect_ratio)
    audit = providers.get_audit_service()
    audit.record(
        action="generate",
        session_id=session_id,
        deck_type=req.deck_type,
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return GenerateResponse(session_id=session_id, slides=slides)


def _max_slide_count(req: GenerateRequest) -> int:
    if req.source_type == "script":
        return MAX_SCRIPT_SLIDES
    return SLIDE_COUNTS[req.deck_type] + SLIDE_COUNT_TOLERANCE


async def _resolve_slide_images(slides: list[SlideData]) -> None:
    resolve_many = getattr(image_resolver, "resolve_many", None)
    if resolve_many is not None:
        await resolve_many(slides)
        return
    for slide in slides:
        if image_resolver.needs_image(slide):
            img_b64 = await image_resolver.resolve(slide)
            if img_b64:
                slide.image_b64 = img_b64
