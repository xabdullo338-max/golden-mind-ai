from fastapi.testclient import TestClient
from app.api import app

def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_kill_switch_requires_admin_auth():
    client = TestClient(app)
    response = client.post("/kill-switch/stop")
    assert response.status_code == 401
