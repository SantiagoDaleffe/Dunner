import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import Request
from api.routers.process import process_event
import os
from fastapi import HTTPException
from contextlib import asynccontextmanager

# Mock environment variables
@pytest.mark.asyncio
@patch.dict(os.environ, {
    "QSTASH_CURRENT_SIGNING_KEY": "curr",
    "QSTASH_NEXT_SIGNING_KEY": "next",
    "QSTASH_TOKEN": "token",
    "PUBLIC_API_URL": "http://api.test"
})
@patch("api.routers.process.qstash_receiver")
@patch("api.routers.process.httpx.AsyncClient")
async def test_process_event_success(mock_httpx_client, mock_receiver):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_httpx_client.return_value.__aenter__.return_value.post.return_value = mock_response
    # Mocking DB and Request
    mock_db = AsyncMock()
    
    @asynccontextmanager
    async def mock_begin():
        yield
    mock_db.begin = mock_begin
    mock_request = AsyncMock(spec=Request)
    
    # Mock request body and headers
    mock_request.headers = {"Upstash-Signature": "sig", "Upstash-Trace-Id": "trace1"}
    mock_request.body.return_value = b'{"event_id": "e1", "tenant_id": "t1"}'
    mock_request.json.return_value = {"event_id": "e1", "tenant_id": "t1", "data": {"amount": 100, "error_code": "temp", "attempt_count": 1}}
    
    # Mock DB result
    mock_result = MagicMock()
    mock_result.first.return_value = ({"hard_errors": ["fraud"], "max_attempts": 3},)
    mock_db.execute.return_value = mock_result
    
    # Act
    response = await process_event(mock_request, db=mock_db)
    
    # Assert
    assert response == {"status": "processed"}
    mock_receiver.verify.assert_called_once()

@pytest.mark.asyncio
async def test_process_event_missing_signature():
    # Arrange
    mock_db = AsyncMock()
    mock_request = AsyncMock(spec=Request)
    mock_request.headers = {}

    # Act & Assert
    with pytest.raises(HTTPException) as excinfo:
        await process_event(mock_request, db=mock_db)
    
    assert excinfo.value.status_code == 401
    assert "Signature missing" in excinfo.value.detail

@pytest.mark.asyncio
@patch.dict(os.environ, {"QSTASH_CURRENT_SIGNING_KEY": "curr", "QSTASH_NEXT_SIGNING_KEY": "next"})
@patch("api.routers.process.qstash_receiver")
async def test_process_event_invalid_signature(mock_receiver):
    # Arrange
    mock_db = AsyncMock()
    mock_request = AsyncMock(spec=Request)
    mock_request.headers = {"Upstash-Signature": "bad_sig"}
    mock_request.body.return_value = b'{}'
    
    mock_receiver.verify.side_effect = Exception("Invalid signature mock")

    # Act & Assert
    with pytest.raises(HTTPException) as excinfo:
        await process_event(mock_request, db=mock_db)
    
    assert excinfo.value.status_code == 401
    assert "Invalid QStash signature" in excinfo.value.detail
