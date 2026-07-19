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
        "deployment_mode": "single_user_local",
    }


async def test_openapi_identifies_service() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "TranscriptForge API"


async def test_readiness_metrics_and_request_correlation(client: AsyncClient) -> None:
    health = await client.get("/api/health", headers={"X-Request-ID": "portfolio-check-123"})
    assert health.headers["x-request-id"] == "portfolio-check-123"

    replaced = await client.get("/api/health", headers={"X-Request-ID": "short"})
    assert len(replaced.headers["x-request-id"]) == 32
    assert replaced.headers["x-request-id"] != "short"

    ready = await client.get("/api/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "database": "ok"}

    system = await client.get("/api/system")
    assert system.status_code == 200
    assert system.json() == {
        "deployment_mode": "single_user_local",
        "authentication_enabled": False,
        "max_upload_bytes": 25 * 1024**3,
        "project_upload_quota_bytes": 100 * 1024**3,
    }

    metrics = await client.get("/api/metrics")
    assert metrics.status_code == 200
    assert "transcriptforge_api_requests_total" in metrics.text
    assert 'status_class="2xx"' in metrics.text
