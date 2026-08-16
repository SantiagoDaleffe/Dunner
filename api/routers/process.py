import os
import json
import uuid
import httpx
from fastapi import APIRouter, Request, Depends, HTTPException
from qstash import Receiver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from api.utils.dependencies import get_db
from api.utils.logger import logger, trace_id_var
from core.engine import DunningEngine
from core.rules import HardDeclineRule, MaxAttemptsRule, ExponentialBackoffRule
from core.models import PaymentEvent, ActionType

router = APIRouter()

qstash_receiver = Receiver(
    current_signing_key=os.environ["QSTASH_CURRENT_SIGNING_KEY"],
    next_signing_key=os.environ["QSTASH_NEXT_SIGNING_KEY"],
)


@router.post("/process", status_code=200)
async def process_event(request: Request, db: AsyncSession = Depends(get_db)):
    """Process incoming payment failure events from QStash.

    Verifies the QStash signature, loads tenant dunning rules from the database,
    evaluates the event with the DunningEngine and either schedules a retry
    (persisting it and publishing a delayed QStash job) or ignores the event.

    Args:
        request (Request): FastAPI request containing the QStash webhook payload
            and headers used for signature and tracing.
        db (AsyncSession, optional): Async SQLAlchemy session dependency.

    Raises:
        HTTPException: 401 if the QStash signature is missing or invalid.
        HTTPException: 500 for unexpected internal processing errors.

    Returns:
        dict: A simple status object describing the result (e.g. {"status": "processed"}
        or {"status": "ignored", "reason": "..."}).
    """
    signature = request.headers.get("Upstash-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Signature missing")

    body_bytes = await request.body()
    try:
        qstash_receiver.verify(body=body_bytes.decode("utf-8"), signature=signature)
    except Exception as e:
        logger.error(f"Invalid QStash signature: {e}")
        raise HTTPException(status_code=401, detail="Invalid QStash signature")

    trace_id = request.headers.get("Upstash-Trace-Id", trace_id_var.get())
    trace_id_var.set(trace_id)

    payload = await request.json()
    event_id = payload.get("event_id")
    tenant_id = payload.get("tenant_id")

    logger.info(
        f"[Trace: {trace_id}] Processing event {event_id}."
    )

    try:
        async with db.begin():
            result = await db.execute(
                text(
                    "SELECT dunning_rules FROM tenant_configs WHERE tenant_id = :tenant_id AND is_active = true"
                ),
                {"tenant_id": tenant_id},
            )
            config_row = result.first()

        if not config_row:
            logger.warning(
                f"[Trace: {trace_id}] Tenant {tenant_id} not active or found. Ignoring event."
            )
            return {"status": "ignored", "reason": "Tenant not active or found"}

        rules_json = config_row[0]

        dunning_engine = DunningEngine(
            rules=[
                HardDeclineRule(
                    fatal_errors=rules_json.get(
                        "hard_errors", ["card_stolen", "fraud_suspected"]
                    )
                ),
                MaxAttemptsRule(max_attempts=rules_json.get("max_attempts", 3)),
                ExponentialBackoffRule(base_hours=24, max_days=7),
            ]
        )

        event_data = payload.get("data", {})
        payment_event = PaymentEvent(
            event_id=event_id,
            tenant_id=tenant_id,
            error_code=event_data.get("error_code"),
            attempt_count=event_data.get("attempt_count"),
            amount=event_data.get("amount"),
            currency=event_data.get("currency", "USD"),
        )

        decision = dunning_engine.process(payment_event)
        logger.info(
            f"[Trace: {trace_id}] Decision: {decision.action_type.name} - {decision.reason}"
        )

        if decision.action_type == ActionType.RETRY and decision.scheduled_for:
            async with db.begin():
                await db.execute(
                    text("""
                        INSERT INTO scheduled_retries (id, tenant_id, event_id, execute_at, payment_data, status, created_at)
                        VALUES (:id, :tenant_id, :event_id, :execute_at, CAST(:payment_data AS JSONB), :status, NOW())
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": payment_event.tenant_id,
                        "event_id": payment_event.event_id,
                        "execute_at": decision.scheduled_for,
                        "payment_data": json.dumps(payload),
                        "status": "PENDING",
                    },
                )

            qstash_token = os.environ["QSTASH_TOKEN"]
            api_url = os.environ["PUBLIC_API_URL"].replace("https://", "").replace("http://", "")
            unix_timestamp = str(int(decision.scheduled_for.timestamp()))

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://us-east-1.qstash.upstash.io/v2/publish/{api_url}/webhook/execute-retry",
                    headers={
                        "Authorization": f"Bearer {qstash_token}",
                        "Content-Type": "application/json",
                        "Upstash-Not-Before": unix_timestamp,
                        "Upstash-Trace-Id": trace_id
                    },
                    json={"event_id": event_id, "tenant_id": payment_event.tenant_id}
                )
                if response.status_code >= 400:
                    logger.error(f"[Trace: {trace_id}] QStash API Error: {response.text}")

    except Exception as e:
        logger.error(f"[Trace: {trace_id}] Error processing: {e}")
        raise HTTPException(status_code=500, detail="Internal error processing event")

    return {"status": "processed"}
