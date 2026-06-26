from datetime import datetime, timezone, timedelta
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from pptx import Presentation

from app.config import settings
from app.dependencies import get_audit_service, get_session_store, get_storage_service
from app.errors import GenerationError, SessionNotFoundError
from app.middleware.rate_limit import limiter
from app.models.schemas import ExportRequest, ExportResponse
from app.services.platform.auth import get_user_id
from app.services.generation.deck_normalizer import normalize_deck
from app.services.generation.gemini_api import SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services.presentation.pptx_engine import PptxEngine
from app.services.platform.session import SessionStore
from app.services.platform.storage import StorageService

router = APIRouter()


def _validate_pptx_bytes(content: bytes) -> None:
    if not content.startswith(b"PK"):
        raise ValueError("PPTX export is not a ZIP/OpenXML package")
    try:
        with ZipFile(BytesIO(content)) as package:
            names = set(package.namelist())
            if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                raise ValueError("PPTX export is missing required OpenXML parts")
            if not any(name.startswith("ppt/slides/slide") and name.endswith(".xml") for name in names):
                raise ValueError("PPTX export contains no slide XML parts")
        Presentation(BytesIO(content))
    except (BadZipFile, KeyError) as exc:
        raise ValueError("PPTX export is not readable") from exc


@router.post("/export")
@limiter.limit(settings.rate_limit_export)
async def export_deck(
    req: ExportRequest,
    request: Request,
    session_store: SessionStore = Depends(get_session_store),
    storage: StorageService = Depends(get_storage_service),
) -> ExportResponse:
    slides: list
    deck_type = "unknown"
    theme = "minimalist"
    aspect_ratio = "16:9"
    export_session_id = ""

    if req.deck_id:
        from app.dependencies import get_deck_store
        deck_store = get_deck_store()
        deck = await deck_store.get(req.deck_id)
        if deck is None:
            raise HTTPException(status_code=404, detail="Deck not found")
        slides = deck["slides"]
        deck_type = deck["deck_type"]
        theme = deck["theme"]
        aspect_ratio = deck["aspect_ratio"]
        export_session_id = req.deck_id
    elif req.session_id:
        session = session_store.get(req.session_id)
        if session is None:
            raise SessionNotFoundError(req.session_id)
        slides = session["slides"]
        deck_type = session.get("deck_type", "unknown")
        theme = session.get("theme", "minimalist")
        aspect_ratio = session.get("aspect_ratio", "16:9")
        export_session_id = req.session_id
    else:
        raise HTTPException(status_code=422, detail="Either session_id or deck_id is required")

    engine = PptxEngine(
        template_path=settings.sample_template_path,
        theme=theme,
        aspect_ratio=aspect_ratio,
    )
    max_count = SLIDE_COUNTS.get(deck_type, len(slides) + 1) + SLIDE_COUNT_TOLERANCE
    slides = normalize_deck(slides, max_count=max_count)
    pptx_bytes = engine.render(slides)
    try:
        _validate_pptx_bytes(pptx_bytes)
    except ValueError as exc:
        raise GenerationError(str(exc)) from exc

    url = await storage.upload_pptx(export_session_id, pptx_bytes, base_url=str(request.base_url))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.signed_url_expiry_minutes)
    audit = get_audit_service()
    audit.record(
        action="export",
        session_id=export_session_id,
        deck_type=deck_type,
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return ExportResponse(download_url=url, expires_at=expires_at)
