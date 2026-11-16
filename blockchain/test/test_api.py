from fastapi.testclient import TestClient

from main import app, get_pipeline


def test_health_and_harmonize_endpoints():
    get_pipeline.cache_clear()
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
    assert response.json()["onchain_status"] == "NOT_COMMITTED"

    get_pipeline.cache_clear()
