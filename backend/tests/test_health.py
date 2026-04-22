from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["status"] in {"ok", "degraded"}
    assert "checks" in payload["data"]
    assert payload["data"]["checks"]["database"]["status"] == "ok"
