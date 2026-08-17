from datetime import datetime
import os
import logging
from contextvars import ContextVar
import uuid

from fastapi import APIRouter, Request, Depends, HTTPException
from qstash import Receiver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.utils.logger import logger, trace_id_var
from api.utils.dependencies import get_db
import stripe
import httpx

router = APIRouter()
qstash_receiver = Receiver(
    current_signing_key=os.environ["QSTASH_CURRENT_SIGNING_KEY"],
    next_signing_key=os.environ["QSTASH_NEXT_SIGNING_KEY"],
)

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

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
        event_data = payment_data.get("data", {})
        customer_id = event_data.get("customer_id")
        payment_method_id = event_data.get("payment_method_id")
        amount = event_data.get("amount", 0)
        currency = event_data.get("currency", "usd")

        logger.info(f"[Trace: {trace_id}] Executing charge for customer {customer_id}")
        
        try:
            amount_in_cents = int(float(amount) * 100)
            intent = stripe.PaymentIntent.create(
                amount=amount_in_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                off_session=True,
                confirm=True,
                idempotency_key=event_id
            )
            logger.info(f"[Trace: {trace_id}] PaymentIntent created: {intent['id']} for event {event_id}")
            final_status = "SUCCESS"
        except stripe.error.CardError as e:
            logger.warning(f"[Trace: {trace_id}] Card error for event {event_id}: {e.user_message}")
            final_status = "FAILED_AGAIN"
            
            current_attempt = int(event_data.get("attempt_count", 1))
            api_url = os.environ.get("PUBLIC_API_URL")
            
            retry_payload = {
                "event_id": f"evt_retry_{uuid.uuid4().hex[:8]}",
                "tenant_id": tenant_id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data": {
                    "customer_id": customer_id,
                    "payment_method_id": payment_method_id,
                    "amount": amount,
                    "currency": currency,
                    "error_code": e.code or "card_declined",
                    "attempt_count": current_attempt + 1
                }
            }
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{api_url}/webhook/ingest",
                        json=retry_payload
                    )
                logger.info(f"[Trace: {trace_id}] New retry enqueued (Attempt {current_attempt + 1})")
            except Exception as loop_error:
                logger.error(f"[Trace: {trace_id}] Failed to enqueue next retry: {loop_error}")

        except Exception as e:
            logger.error(f"[Trace: {trace_id}] Error executing retry for event {event_id}: {str(e)}")
            final_status = "ERROR"
            
        await db.execute(
            text("UPDATE scheduled_retries SET status = :status WHERE event_id = :event_id"),
            {"status": final_status, "event_id": event_id},
        )
        
    return {"status": "success", "event_id": event_id, "message": "Retry executed"}
