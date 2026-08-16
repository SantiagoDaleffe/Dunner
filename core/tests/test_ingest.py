import os
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.utils.security import verify_api_key, verify_webhook_signature
from api.utils.dependencies import get_db
from contextlib import asynccontextmanager

app.dependency_overrides[verify_api_key] = lambda: "mock_api_key"
app.dependency_overrides[verify_webhook_signature] = lambda: True


async def mock_get_db():
    mock_session = AsyncMock()
    
    @asynccontextmanager
    async def mock_begin():
        yield
    mock_session.begin = mock_begin
    
    mock_result = MagicMock() 
    mock_result.first.return_value = None
    mock_session.execute.return_value = mock_result
    yield mock_session


app.dependency_overrides[get_db] = mock_get_db

client = TestClient(app)

@patch("api.routers.ingest.httpx.AsyncClient")
@patch.dict(os.environ, {"QSTASH_TOKEN": "mock", "PUBLIC_API_URL": "http://mock"})
def test_ingest_valid_payload(mock_httpx_client):
    """Verify that a valid webhook payload is accepted and QStash is called."""
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
    mock_httpx_client.return_value.__aenter__.return_value.post.assert_called_once()


def test_ingest_invalid_payload_negative_amount():
    """Verify that a negative invoice amount fails validation (Schema)."""
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
    assert response.json()["error"] == "validation_failed"
