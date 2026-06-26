from fastapi.testclient import TestClient
from app.main import app


def test_health_returns_enriched_fields():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["session_provider"] == "local"
    assert data["storage_provider"] == "local"
    assert data["ai_provider"] == "local"
