from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class V2HealthResponse(BaseModel):
    status: str
    version: str
    api_version: str = "2.0"


@router.get("/health")
async def health_v2() -> V2HealthResponse:
    return V2HealthResponse(status="ok", version="1.0.0")
