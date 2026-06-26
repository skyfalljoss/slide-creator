from zipfile import BadZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from openpyxl.utils.exceptions import InvalidFileException

from app.config import settings
from app.dependencies import get_audit_service, get_dlp_service, get_generator_service, get_session_store
from app.errors import DlpViolationError
from app.middleware.rate_limit import limiter
from app.models.schemas import GenerateRequest, GenerateResponse, SlideData
from app.services.platform.auth import get_user_id
from app.services.generation.deck_normalizer import normalize_deck
from app.services.generation.gemini_api import MAX_SCRIPT_SLIDES, SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services.platform.session import SessionStore
from app.services.platform.dlp import DlpService
from app.services.generation.gemini import GeminiService
from app.services.presentation.slide_charts import SlideChartResolver
from app.services.media.slide_images import SlideImageResolver
from app.services.platform.uploads import UploadService

router = APIRouter()
uploads = UploadService()
chart_resolver = SlideChartResolver()
image_resolver = SlideImageResolver()


@router.post("/generate")
@limiter.limit(settings.rate_limit_generate)
async def generate(
    req: GenerateRequest,
    request: Request,
    dlp: DlpService = Depends(get_dlp_service),
    gemini: GeminiService = Depends(get_generator_service),
    session_store: SessionStore = Depends(get_session_store),
) -> GenerateResponse:
    violations = dlp.scan_prompt(req.prompt)
    if violations:
        raise DlpViolationError(terms=violations)

    rows: list[dict[str, str]] | None = None
    upload_summary: dict[str, object] | None = None
    if req.file_id:
        try:
            rows = uploads.get_rows(req.file_id)
            upload_summary = uploads.get_ai_summary(req.file_id)
        except (BadZipFile, FileNotFoundError, InvalidFileException, ValueError):
            raise HTTPException(status_code=400, detail="Invalid uploaded file") from None

    slides = await gemini.generate(req, chart_data=None, upload_summary=upload_summary)
    chart_resolver.attach(slides=slides, rows=rows, upload_summary=upload_summary)
    slides = normalize_deck(slides, max_count=_max_slide_count(req))

    await _resolve_slide_images(slides)

    flagged = dlp.scan_slides(slides)
    if flagged:
        terms = sorted({term for item in flagged for term in item["violations"]})
        raise DlpViolationError(terms=terms)

    session_id = session_store.create(slides, req.deck_type, req.theme, req.aspect_ratio)
    audit = get_audit_service()
    audit.record(
        action="generate",
        session_id=session_id,
        deck_type=req.deck_type or "unknown",
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return GenerateResponse(session_id=session_id, slides=slides)


def _max_slide_count(req: GenerateRequest) -> int:
    if req.source_type == "script":
        return MAX_SCRIPT_SLIDES
    if req.deck_type and req.deck_type in SLIDE_COUNTS:
        return SLIDE_COUNTS[req.deck_type] + SLIDE_COUNT_TOLERANCE
    return MAX_SCRIPT_SLIDES


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
