from fastapi.testclient import TestClient
from fira.main import app

client = TestClient(app)

def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "notice" in data
    assert "not tax advice" in data["notice"]

def test_readyz() -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "notice" in data

