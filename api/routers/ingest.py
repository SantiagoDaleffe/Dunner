import os
import httpx
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from api.utils.dependencies import get_db
from api.utils.logger import logger, trace_id_var
from api.utils.schemas import WebhookIngestPayload
from api.utils.security import limiter
import stripe
from datetime import datetime, timezone

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


@router.post("/stripe", status_code=200)
async def stripe_webhook_adapter(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except Exception as e:
        logger.error(f"Invalid Stripe signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] in ["invoice.payment_failed", "payment_intent.payment_failed"]:
        obj = event["data"]["object"]

        customer_id = getattr(obj, "customer", None)
        amount_due = getattr(obj, "amount_due", getattr(obj, "amount", 0))
        amount = float(amount_due) / 100.0 if amount_due else 0.0
        
        dunning_payload = {
            "event_id": f"evt_strp_{event['id']}",
            "tenant_id": "org_12345",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "customer_id": customer_id or "cus_V5NPywL4pItSVc",
                "payment_method_id": "pm_1U5Cf5AyrAR3v1XKLssw8QZy", 
                "invoice_id": getattr(obj, "id", "inv_desc"),
                "amount": amount if amount > 0 else 15.50,
                "currency": getattr(obj, "currency", "usd"),
                "error_code": "stripe_declined",
                "attempt_count": 1
            }
        }

        api_url = os.environ["PUBLIC_API_URL"]
        qstash_token = os.environ["QSTASH_TOKEN"]
        
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://qstash-us-east-1.upstash.io/v2/publish/{api_url}/webhook/process",
                headers={
                    "Authorization": f"Bearer {qstash_token}",
                    "Content-Type": "application/json",
                },
                json=dunning_payload
            )
        logger.info(f"Stripe event processed: {event['id']}")

    return {"status": "success"}