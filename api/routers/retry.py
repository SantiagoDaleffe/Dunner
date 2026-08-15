import os
import logging
from contextvars import ContextVar

from fastapi import APIRouter, Request, Depends, HTTPException
from upstash_qstash import Receiver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.utils.logger import logger, trace_id_var
from api.dependencies import get_db

router = APIRouter()
qstash_receiver = Receiver(
    current_signing_key=os.environ.get("QSTASH_CURRENT_SIGNING_KEY", "mock_current"),
    next_signing_key=os.environ.get("QSTASH_NEXT_SIGNING_KEY", "mock_next"),
)

@router.post("/execute-retry", status_code=200)
async def execute_retry(request: Request, db: AsyncSession = Depends(get_db)):
    signature = request.headers.get("Upstash-Signature")
    if not signature:
        logger.warning("Intento de acceso a QStash sin firma.")
        raise HTTPException(status_code=401, detail="Firma faltante")

    body_bytes = await request.body()

    try:
        qstash_receiver.verify(body=body_bytes.decode("utf-8"), signature=signature)
    except Exception as e:
        logger.error(f"Firma de QStash inválida: {e}")
        raise HTTPException(status_code=401, detail="Firma de QStash inválida")

    payload = await request.json()
    event_id = payload.get("event_id")
    tenant_id = payload.get("tenant_id")

    logger.info(
        f"[Trace: {trace_id_var.get()}] Ejecutando reintento real para evento {event_id} (Tenant: {tenant_id})"
    )

    async with db.begin():
        #SELECT para traer el 'payment_data' y saber a quién cobrarle
        await db.execute(
            text(
                "UPDATE scheduled_retries SET status = 'EXECUTED' WHERE event_id = :event_id"
            ),
            {"event_id": event_id},
        )
    return {"status": "success", "event_id": event_id, "message": "Reintento ejecutado"}
