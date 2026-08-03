from fastapi.testclient import TestClient
from api.main import app
import uuid
import datetime

client = TestClient(app)


def test_ingest_valid_payload():
    """Verify that a valid webhook payload is accepted."""
    valid_payload = {
        "event_id": f"evt_{uuid.uuid4()}",
        "tenant_id": "org_12345",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data": {
            "customer_id": "cus_999",
            "invoice_id": "in_555",
            "amount": 1500.50,
            "currency": "ARS",
            "error_code": "insufficient_funds",
            "attempt_count": 1,
        },
    }

    response = client.post("/webhook/ingest", json=valid_payload)

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert "X-Trace-ID" in response.headers


def test_ingest_invalid_payload_negative_amount():
    """Verify that a negative invoice amount fails validation."""
    invalid_payload = {
        "event_id": f"evt_{uuid.uuid4()}",
        "tenant_id": "org_12345",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data": {
            "customer_id": "cus_999",
            "invoice_id": "in_555",
            "amount": -500.00,
            "currency": "ARS",
            "error_code": "insufficient_funds",
            "attempt_count": 1,
        },
    }

    response = client.post("/webhook/ingest", json=invalid_payload)

    assert response.status_code == 422
    response_data = response.json()

    assert response_data["error"] == "validation_failed"
    assert "trace_id" in response_data
    assert response_data["details"][0]["field"] == "data -> amount"
