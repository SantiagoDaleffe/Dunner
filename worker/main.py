import asyncio
import httpx
import os
import json
import logging
import uuid
import aio_pika
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Importamos la lógica de negocio pura
from core.engine import DunningEngine
from core.rules import HardDeclineRule, MaxAttemptsRule, ExponentialBackoffRule, HighValueAlertRule
from core.models import PaymentEvent, ActionType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
QUEUE_NAME = os.environ["RABBITMQ_QUEUE_NAME"]
EXCHANGE_NAME = os.environ["RABBITMQ_EXCHANGE_NAME"]
ROUTING_KEY = os.environ["RABBITMQ_ROUTING_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

# Motor de base de datos exclusivo para el worker
db_engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    future=True,
    pool_size=10,          # Mantiene 10 conexiones vivas listas para usar
    max_overflow=20,       # Si hay un pico, permite abrir hasta 20 más temporalmente
    pool_pre_ping=True,    # Hace un "ping" a la BD antes de usar la conexión para asegurar que no se cayó
    pool_recycle=1800      # Recicla las conexiones cada 30 minutos (evita cierres forzados por Supabase)
)

# Inicializamos el motor de reglas (En un V2, estas configuraciones saldrían de la tabla tenant_configs)
dunning_engine = DunningEngine(rules=[
    HardDeclineRule(fatal_errors=["card_stolen", "fraud_suspected", "account_closed"]),
    MaxAttemptsRule(max_attempts=3),
    HighValueAlertRule(threshold_amount=1000.0),
    ExponentialBackoffRule(base_hours=24, max_days=7)
])

async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
    async with message.process(ignore_processed=True):
        payload = json.loads(message.body.decode())
        trace_id = message.headers.get("x-trace-id", "unknown")
        event_id = payload.get("event_id")
        
        logger.info(f"[Trace: {trace_id}] Procesando evento {event_id} para tenant {payload.get('tenant_id')}")

        try:
            # 1. Parseamos el JSON crudo al modelo de dominio (PaymentEvent)
            event_data = payload.get("data", {})
            payment_event = PaymentEvent(
                event_id=event_id,
                tenant_id=payload.get("tenant_id"),
                error_code=event_data.get("error_code"),
                attempt_count=event_data.get("attempt_count"),
                amount=event_data.get("amount"),
                currency=event_data.get("currency", "USD")
            )

            # 2. Pasamos el evento por la cadena de reglas matemáticas
            decision = dunning_engine.process(payment_event)
            logger.info(f"[Trace: {trace_id}] Decisión: {decision.action_type.name} - {decision.reason}")

            # 3. Ejecutamos la acción según lo que dictó el motor
            if decision.action_type == ActionType.RETRY and decision.scheduled_for:
                async with db_engine.begin() as conn:
                    await conn.execute(
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
                            "status": "PENDING"
                        }
                    )
                logger.info(f"[Trace: {trace_id}] Reintento agendado en BD para {decision.scheduled_for}")
                
                qstash_token = os.environ.get("QSTASH_TOKEN")
                
                api_url = os.environ.get("PUBLIC_API_URL")
                
                unix_timestamp = str(int(decision.scheduled_for.timestamp()))
                
                async with httpx.AsyncClient() as client:
                    qstash_res = await client.post(
                        f"https://qstash.upstash.io/v2/publish/{api_url}/webhook/execute-retry",
                        headers={
                            "Authorization": f"Bearer {qstash_token}",
                            "Content-Type": "application/json",
                            "Upstash-Not-Before": unix_timestamp # ¡La clave de la reactividad!
                        },
                        json={
                            "event_id": payment_event.event_id, 
                            "tenant_id": payment_event.tenant_id
                        }
                    )
                    
                if qstash_res.status_code in (200, 201, 202):
                    logger.info(f"[Trace: {trace_id}] Evento enviado a QStash para despertar el sistema a las {unix_timestamp}")
                else:
                    logger.error(f"[Trace: {trace_id}] Error en QStash: {qstash_res.text}")
                    
                    
            
            elif decision.action_type == ActionType.ALERT:
                # Acá a futuro integrarías la alerta manual (mail, webhook a ventas, Slack)
                logger.warning(f"[Trace: {trace_id}] ALERTA generada por monto crítico.")
            
            elif decision.action_type == ActionType.CANCEL:
                logger.info(f"[Trace: {trace_id}] Suscripción marcada para cancelación.")

            # Confirmamos a RabbitMQ que terminamos para que borre el mensaje de la cola
            await message.ack()

        except Exception as e:
            logger.error(f"[Trace: {trace_id}] Error procesando evento {event_id}: {str(e)}")
            # Si explota, lo rechazamos. 
            # Como pusimos requeue=False y no configuramos DLQ, se pierde. 
            # (Lo vamos a mandar a la DLQ en la próxima iteración).
            await message.reject(requeue=False)

async def main():
    logger.info("Worker starting up and connecting to RabbitMQ.")

    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
        )

        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(exchange, routing_key=ROUTING_KEY)

        logger.info(f"Worker listening on queue '{QUEUE_NAME}'.")

        await queue.consume(process_message)
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped manually.")