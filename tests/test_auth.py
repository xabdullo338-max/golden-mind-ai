import os
from fastapi.testclient import TestClient
from app.api import app
from app.auth import create_access_token

def test_token_round_trip(monkeypatch):
    monkeypatch.setenv("GMAI_JWT_SECRET", "test-secret")
    token = create_access_token("admin", ["read"])
    client = TestClient(app)
    response = client.get("/protected/ping", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_missing_token_is_rejected():
    client = TestClient(app)
    response = client.get("/protected/ping")
    assert response.status_code == 401
