from fastapi.testclient import TestClient

from main import Config, app, get_pipeline
from src.rq2.blockchain_client import BlockchainClient


def test_health_and_harmonize_endpoints(monkeypatch):
    monkeypatch.setenv("SHARED_SECRET_KEY", "public serving test key")
    get_pipeline.cache_clear()
    monkeypatch.setattr(Config, "API_ENABLE_BLOCKCHAIN_COMMIT", False)
    monkeypatch.setattr(BlockchainClient, "_initialize_connection", lambda self: None)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    invalid = client.post("/api/v1/harmonize", json={"record_id": "missing-fields"})
    assert invalid.status_code == 422

    response = client.post(
        "/api/v1/harmonize",
        json={
            "record_id": "API_TEST_1",
            "raw_description": "Didanosine 200mg tablets",
            "stakeholder_org": "Test_Org",
        },
    )
    assert response.status_code == 200
    assert response.json()["encoder_version"].startswith("composite-hmac-sha256-v1")
    assert response.json()["onchain_status"] == "NOT_COMMITTED"

    get_pipeline.cache_clear()
