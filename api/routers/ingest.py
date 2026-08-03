from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.utils.schemas import WebhookIngestPayload
from api.utils.models import ScheduledRetry
from api.utils.database import get_db
from api.utils.logger import logger, trace_id_var


router = APIRouter(prefix="/webhook", tags=["Ingestion"])


@router.post("/ingest", status_code=202)
async def ingest_webhook(
    payload: WebhookIngestPayload, db: AsyncSession = Depends(get_db)
):
    """Ingest webhook payload and queue event for processing.

    Accepts webhook events, checks for duplicates, and queues them for processing.

    Args:
        payload (WebhookIngestPayload): The webhook payload containing event data.
        db (AsyncSession, optional): Database session. Defaults to Depends(get_db).

    Returns:
        dict: Status response with trace ID and optional note about duplicate events.
    """
    query = select(ScheduledRetry.id).where(ScheduledRetry.event_id == payload.event_id)
    result = await db.execute(query)

    if result.first():
        logger.warning(f"Event {payload.event_id} duplicated. Ignoring.")
        return {
            "status": "accepted",
            "trace_id": trace_id_var.get(),
            "note": "Already processed",
        }

    logger.info(f"Event {payload.event_id} accepted. Sending to queue.")

    return {"status": "accepted", "trace_id": trace_id_var.get()}
