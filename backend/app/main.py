from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.routers import generate, refine, export, uploads
from app.services.storage import StorageService
from app.services.uploads import UploadService


@asynccontextmanager
async def lifespan(app: FastAPI):
    purge_local_temp_files()
    yield


app = FastAPI(
    title="SlideForge API",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api/v1", tags=["generate"])
app.include_router(refine.router, prefix="/api/v1", tags=["refine"])
app.include_router(export.router, prefix="/api/v1", tags=["export"])
app.include_router(uploads.router, prefix="/api/v1", tags=["uploads"])

def purge_local_temp_files() -> dict[str, int]:
    return {
        "exports": StorageService().purge_expired(settings.signed_url_expiry_minutes * 60),
        "uploads": UploadService().purge_expired(settings.session_ttl_minutes * 60),
    }


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/v1/download/{filename}")
async def download_export(filename: str):
    path = StorageService().get_local_path(filename, max_age_seconds=settings.signed_url_expiry_minutes * 60)
    if path is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="SlideForge-Presentation.pptx",
        content_disposition_type="attachment",
    )
