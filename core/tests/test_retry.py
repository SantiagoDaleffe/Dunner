import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, HTTPException
from api.routers.retry import execute_retry
import os
from contextlib import asynccontextmanager

@pytest.mark.asyncio
@patch.dict(os.environ, {"QSTASH_CURRENT_SIGNING_KEY": "curr", "QSTASH_NEXT_SIGNING_KEY": "next"})
@patch("api.routers.retry.qstash_receiver")
async def test_execute_retry_success(mock_receiver):
    # Arrange
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.first.return_value = ({"data": {"customer_id": "cus_999", "amount": 100}},)
    mock_db.execute.return_value = mock_result
    
    @asynccontextmanager
    async def mock_begin():
        yield
    mock_db.begin = mock_begin
    mock_request = AsyncMock(spec=Request)
    
    mock_request.headers = {"Upstash-Signature": "valid_sig"}
    mock_request.body.return_value = b'{"event_id": "e123", "tenant_id": "org_1"}'
    mock_request.json.return_value = {"event_id": "e123", "tenant_id": "org_1"}
    
    mock_receiver.verify.return_value = True

    # Act
    response = await execute_retry(mock_request, db=mock_db)
    
    # Assert
    assert response["status"] == "success"
    assert response["event_id"] == "e123"
    
    assert mock_db.execute.call_count == 2