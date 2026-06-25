from datetime import datetime, timezone, timedelta
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from fastapi import APIRouter, HTTPException, Request
from pptx import Presentation

from app.config import settings
from app.models.schemas import ExportRequest, ExportResponse
from app.services.auth import get_user_id
from app.services.deck_normalizer import normalize_deck
from app.services.gemini_api import SLIDE_COUNTS, SLIDE_COUNT_TOLERANCE
from app.services.pptx_engine import PptxEngine
from app.services import providers
from app.services.session import get_session

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
async def export_deck(req: ExportRequest, request: Request) -> ExportResponse:
    session = get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    engine = PptxEngine(
        template_path=settings.sample_template_path,
        theme=session.get("theme", "minimalist"),
        aspect_ratio=session.get("aspect_ratio", "16:9"),
    )
    max_count = SLIDE_COUNTS.get(session["deck_type"], len(session["slides"]) + 1) + SLIDE_COUNT_TOLERANCE
    slides = normalize_deck(session["slides"], max_count=max_count)
    session["slides"] = slides
    pptx_bytes = engine.render(slides)
    try:
        _validate_pptx_bytes(pptx_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    storage = providers.get_storage_service()
    url = await storage.upload_pptx(req.session_id, pptx_bytes, base_url=str(request.base_url))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.signed_url_expiry_minutes)
    audit = providers.get_audit_service()
    audit.record(
        action="export",
        session_id=req.session_id,
        deck_type=session["deck_type"],
        slide_count=len(slides),
        user_id=get_user_id(request),
        model=settings.gemini_model,
    )

    return ExportResponse(download_url=url, expires_at=expires_at)
