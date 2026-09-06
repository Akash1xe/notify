from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_youtube_url_has_normalized_error() -> None:
    with TestClient(app) as client:
        response = client.post("/api/video/metadata", json={"url": "https://google.com"})
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "INVALID_YOUTUBE_URL"
