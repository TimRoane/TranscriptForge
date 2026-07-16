"""API liveness contract tests."""

from httpx import ASGITransport, AsyncClient
from transcriptforge_api.main import app


async def test_health_contract() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "transcriptforge-api",
        "version": "0.1.0",
        "environment": "development",
    }


async def test_openapi_identifies_service() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "TranscriptForge API"
