import os
import logging
from contextvars import ContextVar

from fastapi import APIRouter, Request, Depends, HTTPException
from qstash import Receiver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.utils.logger import logger, trace_id_var
from api.utils.dependencies import get_db

router = APIRouter()
qstash_receiver = Receiver(
    current_signing_key=os.environ["QSTASH_CURRENT_SIGNING_KEY"],
    next_signing_key=os.environ["QSTASH_NEXT_SIGNING_KEY"],
)


@router.post("/execute-retry", status_code=200)
async def execute_retry(request: Request, db: AsyncSession = Depends(get_db)):
    """Execute a scheduled retry job for a tenant event.

    This endpoint validates the incoming QStash webhook signature, verifies the
    payload, marks the corresponding scheduled retry as executed, and returns
    success information for the retry.

    Args:
        request (Request): The incoming HTTP request containing the QStash
            payload and headers.
        db (AsyncSession, optional): The database session dependency used to
            update the retry status. Defaults to Depends(get_db).

    Raises:
        HTTPException: Raised with status 401 if the request does not include a
            valid Upstash signature or if the signature verification fails.

    Returns:
        dict: A confirmation payload containing the execution status, event ID,
        and a success message.
    """
    signature = request.headers.get("Upstash-Signature")
    if not signature:
        logger.warning("Missing Upstash signature in request headers.")
        raise HTTPException(status_code=401, detail="Signature missing")

    body_bytes = await request.body()
    try:
        qstash_receiver.verify(body=body_bytes.decode("utf-8"), signature=signature)
    except Exception as e:
        logger.error(f"Invalid QStash signature: {e}")
        raise HTTPException(status_code=401, detail="Invalid QStash signature")

    payload = await request.json()
    event_id = payload.get("event_id")
    tenant_id = payload.get("tenant_id")
    trace_id = trace_id_var.get()

    logger.info(f"[Trace: {trace_id}] Executing retry for event {event_id} (Tenant: {tenant_id})")

    async with db.begin():
        result = await db.execute(
            text("SELECT payment_data FROM scheduled_retries WHERE event_id = :event_id AND status = 'PENDING'"),
            {"event_id": event_id}
        )
        row = result.first()
        
        if not row:
            logger.warning(f"[Trace: {trace_id}] Retry for {event_id} not found or already executed.")
            return {"status": "skipped", "message": "Already executed or not found"}

        payment_data = row[0]
        customer_id = payment_data.get("data", {}).get("customer_id", "Unknown")
        amount = payment_data.get("data", {}).get("amount", 0)

        logger.info(f"[Trace: {trace_id}] Simulating charge for customer {customer_id} for amount {amount}")
        # stripe.Charge.create(...)
        
        await db.execute(
            text("UPDATE scheduled_retries SET status = 'EXECUTED' WHERE event_id = :event_id"),
            {"event_id": event_id},
        )
        
    return {"status": "success", "event_id": event_id, "message": "Retry executed"}
