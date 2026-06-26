from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.rate_limit import limiter, register_rate_limiter


def test_rate_limit_returns_429_on_exceed():
    app = FastAPI()
    register_rate_limiter(app)

    @app.get("/limited")
    @limiter.limit("2/minute")
    def limited_endpoint(request: Request):
        return {"ok": True}

    client = TestClient(app)
    client.get("/limited", headers={"X-Forwarded-For": "1.2.3.4"})
    client.get("/limited", headers={"X-Forwarded-For": "1.2.3.4"})
    resp = client.get("/limited", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.status_code == 429


def test_rate_limit_exceeded_returns_structured_json():
    app = FastAPI()
    register_rate_limiter(app)

    @app.get("/limited")
    @limiter.limit("1/minute")
    def limited_endpoint(request: Request):
        return {"ok": True}

    client = TestClient(app)
    client.get("/limited", headers={"X-Forwarded-For": "5.6.7.8"})
    resp = client.get("/limited", headers={"X-Forwarded-For": "5.6.7.8"})
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "RATE_LIMITED"
