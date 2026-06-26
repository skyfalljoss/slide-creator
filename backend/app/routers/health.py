from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "ai_provider": settings.ai_provider,
        "session_provider": settings.session_provider,
        "storage_provider": settings.storage_provider,
    }
