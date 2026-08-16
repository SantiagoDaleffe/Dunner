import os
import httpx
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from api.utils.dependencies import get_db
from api.utils.logger import logger, trace_id_var
from api.utils.schemas import WebhookIngestPayload
from api.utils.security import limiter

router = APIRouter()


@router.post("/ingest", status_code=202)
@limiter.limit("10/minute")
async def ingest_webhook(
    request: Request, payload: WebhookIngestPayload, db: AsyncSession = Depends(get_db)
):
    """Accept a webhook event and enqueue it for asynchronous processing.

    This endpoint validates the incoming webhook payload, checks whether the event
    has already been processed, and if not, forwards it to the QStash queue for
    downstream processing.

    Args:
        request (Request): FastAPI request instance.
        payload (WebhookIngestPayload): Incoming webhook payload to ingest.
        db (AsyncSession): Database session used to check for duplicate events.

    Returns:
        dict: A dictionary with the ingestion status and trace identifier.
            Returns "accepted" with the current trace ID, and includes a note when
            the event was already processed.
    """
    async with db.begin():
        result = await db.execute(
            text("SELECT 1 FROM scheduled_retries WHERE event_id = :event_id LIMIT 1"),
            {"event_id": payload.event_id},
        )
    if result.first():
        logger.warning(f"Event {payload.event_id} duplicated. Ignoring.")
        return {
            "status": "accepted",
            "trace_id": trace_id_var.get(),
            "note": "Already processed",
        }
        
    api_url = os.environ["PUBLIC_API_URL"]
    logger.info(f"Event {payload.event_id} accepted. Sending to QStash queue.")

    qstash_token = os.environ["QSTASH_TOKEN"]
    api_url = os.environ["PUBLIC_API_URL"]
    trace_id = trace_id_var.get()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://qstash-us-east-1.upstash.io/v2/publish/{api_url}/webhook/process",
            headers={
                "Authorization": f"Bearer {qstash_token}",
                "Content-Type": "application/json",
                "Upstash-Trace-Id": trace_id,
            },
            json=payload.model_dump(mode="json"),
        )
        if response.status_code >= 400:
            logger.error(f"[Trace: {trace_id}] QStash API Error: {response.text}")

    return {"status": "accepted", "trace_id": trace_id}
